import atexit
import io
import json
import os
import random
import re
import secrets
import time
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pypdf import PdfReader
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

_secret = os.getenv("SECRET_KEY")
if not _secret:
    print("WARNING: SECRET_KEY not set in .env - using a random key (sessions reset on restart).")
    _secret = secrets.token_hex(32)
app.secret_key = _secret

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_FILE_BYTES + 64 * 1024

QUIZ_FOLDER = "quizzes"
QUIZ_MAX_AGE = 3600
os.makedirs(QUIZ_FOLDER, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
MAX_PDF_PAGES = 200
MAX_CHARS = 60000

TIERS = ["easy", "medium", "hard"]
TYPES = ["mcq", "trueorfalse", "numerical", "matching"]

MIN_Q = 3
WORDS_PER_QUESTION = 40
MAX_AUTO_Q = 90
DEFAULT_HINT = "Re-read the part of the chapter this question is about."
DEFAULT_TOPIC = "General"

AI_CODES = {
    "1": "This passage is too short to generate a worthwhile quiz.",
    "2": ("The passage may not contain enough information for the requested number of questions. "
          "Try reducing the number of questions or adding more text."),
    "3": "No readable text was found. Please upload a .txt file or a PDF that contains selectable text.",
}


class ExtractionError(Exception):
    pass


def purge_folder(path, max_age=None):
    if not os.path.isdir(path):
        return
    now = time.time()
    for entry in os.scandir(path):
        if not entry.is_file(follow_symlinks=False):
            continue
        if max_age is None or now - entry.stat().st_mtime > max_age:
            try:
                os.remove(entry.path)
            except OSError:
                pass


def purge_all():
    purge_folder(QUIZ_FOLDER)


purge_all()
atexit.register(purge_all)


def pdf_to_text(data):
    texts = []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("This PDF is password protected.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"This PDF has more than {MAX_PDF_PAGES} pages.")
        for page in reader.pages:
            try:
                texts.append((page.extract_text() or "").strip())
            except Exception:
                texts.append("")
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("Could not read this PDF.")

    return "\n".join(t for t in texts if t)


def extract_text(filename, data):
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".txt":
        return data.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        if b"%PDF" not in data[:1024]:
            raise ExtractionError(f"'{filename}' is not a valid PDF.")
        return pdf_to_text(data)
    raise ExtractionError(f"'{filename}' is not supported - upload .txt or .pdf files.")


def split_total(n):
    base, rem = divmod(n, 3)
    return {"easy": base + (rem >= 1), "medium": base + (rem >= 2), "hard": base}


def tier_targets(raw):
    raw = (raw or "max").strip().lower()
    if raw == "max":
        return None
    return split_total(max(MIN_Q, int(raw)))


def auto_targets(text):
    words = len(text.split())
    return split_total(min(MAX_AUTO_Q, max(MIN_Q, words // WORDS_PER_QUESTION)))


def completion_budget(targets):
    return min(32000, 1500 + 300 * sum(targets.values()))


def build_prompt(targets):
    total = sum(targets.values())
    amount = (f"Write exactly {targets['easy']} easy, {targets['medium']} medium and {targets['hard']} hard "
              f"questions ({total} in total). ")
    too_many = ("If the passage is long enough for a quiz but clearly does not contain enough information "
                f"for {total} distinct questions, reply with ONLY the digit 2. ")
    return (
        "You write quizzes from study material. "
        "FIRST check the passage. If it is empty or only whitespace, reply with ONLY the digit 3. "
        "If it is too short or too thin to build a worthwhile quiz at all (for example one or two sentences), "
        "reply with ONLY the digit 1. "
        + too_many +
        "When you reply with a digit, output that single digit and nothing else: no words, no punctuation. "
        "Otherwise respond with ONE single line and NO newline characters. "
        "No markdown, no commentary, no text outside the formats below. "
        + amount +
        "Any question type may appear in any tier. "
        "Every question starts with <start>, ends with <end>, and its fields are separated by $%/ . "
        "Formats: "
        "<start>TIER$%/mcq$%/question$%/optionA$%/optionB$%/optionC$%/optionD$%/answerletter$%/hint1$%/hint2$%/hint3$%/explanation$%/topic<end> "
        "<start>TIER$%/trueorfalse$%/statement$%/true or false$%/hint1$%/hint2$%/hint3$%/explanation$%/topic<end> "
        "<start>TIER$%/numerical$%/question$%/number only, no units$%/hint1$%/hint2$%/hint3$%/explanation$%/topic<end> "
        "<start>TIER$%/matching$%/instruction$%/term1$%/definition1$%/term2$%/definition2$%/term3$%/definition3$%/hint1$%/hint2$%/hint3$%/explanation$%/topic<end> "
        "TIER is exactly one of: easy, medium, hard. "
        "For mcq the answer is ONLY the letter a, b, c or d (do not put 'a)' in front of the options). "
        "For matching, give 3 to 5 term/definition pairs where definitionN is the correct match for termN, "
        "and do NOT add an answer field. "
        "EVERY question must end with hint1, hint2, hint3, an explanation and a topic, in that order. "
        "The three hints get progressively more helpful and NONE of them states the answer outright: "
        "hint1 is a gentle nudge pointing to the right part of the chapter; "
        "hint2 is more specific and narrows the possibilities; "
        "hint3 is a strong clue that almost gives the answer away. "
        "The explanation is 1-3 sentences saying why the correct answer is right"
        " (for mcq also why the other options are wrong), based on the text. "
        "The topic is a short label of 1 to 4 words naming the chapter concept the question tests; "
        "reuse exactly the same label for questions about the same concept and use no more than 8 different labels."
    )


def _normalize_mcq(answer, options):
    a = answer.strip().lower()
    if a in ("a", "b", "c", "d"):
        return a
    m = re.match(r"^\(?([a-d])[\)\.\:]", a)
    if m:
        return m.group(1)
    for letter, opt in zip("abcd", options):
        if a == opt.strip().lower():
            return letter
    return None


def _normalize_tf(answer):
    a = answer.strip().lower().rstrip(".")
    if a in ("true", "t", "yes", "1"):
        return "true"
    if a in ("false", "f", "no", "0"):
        return "false"
    return None


def _tail(extras):
    n = len(extras)
    if n >= 5:
        return extras[0:3], extras[3], extras[4]
    if n == 4:
        return extras[0:3], extras[3], DEFAULT_TOPIC
    if n == 3:
        return [extras[0]], extras[1], extras[2]
    if n == 2:
        return [extras[0]], extras[1], DEFAULT_TOPIC
    if n == 1:
        return [DEFAULT_HINT], extras[0], DEFAULT_TOPIC
    return None


def parse_quiz_data(raw_content):
    quiz = {tier: [] for tier in TIERS}
    skipped = 0

    for block in raw_content.split("<start>")[1:]:
        if "<end>" not in block:
            skipped += 1
            continue
        tokens = [t.strip() for t in block.split("<end>")[0].split("$%/")]
        tokens = [t for t in tokens if t]

        tier = q_type = None
        i = 0
        while i < len(tokens) and i < 2:
            low = tokens[i].lower()
            if low in TIERS and tier is None:
                tier = low
            elif low in TYPES and q_type is None:
                q_type = low
            else:
                break
            i += 1
        if not q_type:
            skipped += 1
            continue
        tier = tier or "easy"
        data = tokens[i:]

        item = None
        if q_type == "mcq" and len(data) >= 7:
            options = [re.sub(r"^[a-d][\)\.]\s+", "", o, flags=re.I) for o in data[1:5]]
            letter = _normalize_mcq(data[5], options)
            tail = _tail(data[6:])
            if letter and tail:
                item = {"type": "mcq", "question": data[0], "options": options, "answer": letter,
                        "hints": tail[0], "explanation": tail[1], "topic": tail[2]}
        elif q_type == "trueorfalse" and len(data) >= 3:
            ans = _normalize_tf(data[1])
            tail = _tail(data[2:])
            if ans and tail:
                item = {"type": "trueorfalse", "question": data[0], "answer": ans,
                        "hints": tail[0], "explanation": tail[1], "topic": tail[2]}
        elif q_type == "numerical" and len(data) >= 3:
            tail = _tail(data[2:])
            if tail:
                item = {"type": "numerical", "question": data[0], "answer": data[1],
                        "hints": tail[0], "explanation": tail[1], "topic": tail[2]}
        elif q_type == "matching" and len(data) >= 10:
            hints, explanation, topic = data[-5:-2], data[-2], data[-1]
            rest = data[1:-5]
            if len(rest) % 2 == 1:
                rest = rest[:-1]
            pairs = [{"left": rest[k], "right": rest[k + 1]} for k in range(0, len(rest), 2)]
            if len(pairs) >= 2:
                item = {"type": "matching", "question": data[0], "pairs": pairs, "answer": "",
                        "hints": hints, "explanation": explanation, "topic": topic}

        if item:
            quiz[tier].append(item)
        else:
            skipped += 1

    total = sum(len(v) for v in quiz.values())
    print(f"DEBUG: parsed {total} questions, skipped {skipped} malformed.")
    return quiz


def save_quiz(quiz, topic):
    delete_quiz()
    quiz_id = uuid.uuid4().hex
    with open(os.path.join(QUIZ_FOLDER, f"{quiz_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": topic, "tiers": quiz}, f)
    session["quiz_id"] = quiz_id


def load_quiz():
    quiz_id = session.get("quiz_id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", quiz_id):
        return {}, ""
    try:
        with open(os.path.join(QUIZ_FOLDER, f"{quiz_id}.json"), encoding="utf-8") as f:
            data = json.load(f)
        tiers = data.get("tiers", {})
        for questions in tiers.values():
            for q in questions:
                if "hints" not in q:
                    q["hints"] = [q.get("hint") or DEFAULT_HINT]
                q.setdefault("topic", DEFAULT_TOPIC)
        return tiers, data.get("topic", "Chapter Quiz")
    except (OSError, ValueError):
        return {}, ""


def delete_quiz():
    quiz_id = session.pop("quiz_id", "")
    if re.fullmatch(r"[0-9a-f]{32}", quiz_id):
        try:
            os.remove(os.path.join(QUIZ_FOLDER, f"{quiz_id}.json"))
        except OSError:
            pass


def topic_from_filenames(names):
    stem = os.path.splitext(secure_filename(names[0]))[0]
    stem = re.sub(r"[_\-]+", " ", stem).strip()[:60] or "Chapter Quiz"
    return stem if len(names) == 1 else f"{stem} +{len(names) - 1} more"


@app.template_filter("shuffle")
def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except Exception:
        return seq


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/quiz")
def quiz():
    questions, topic = load_quiz()
    delete_quiz()
    if not any(questions.get(t) for t in TIERS):
        return redirect(url_for("index"))
    return render_template("quiz.html", questions=questions, topic=topic)


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "Upload too large (max 10MB per file and 5 files)."}), 413


@app.route("/upload", methods=["POST"])
def upload_file():
    files = [f for f in request.files.getlist("fileInput") if f and f.filename]
    if not files:
        return jsonify({"error": "No file selected."}), 400
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY is missing from the server's .env file."}), 500

    try:
        targets = tier_targets(request.form.get("count"))
    except ValueError:
        return jsonify({"error": "Number of questions must be a whole number or 'maximum'."}), 400

    if len(files) > MAX_FILES:
        return jsonify({"error": f"Upload at most {MAX_FILES} files at a time."}), 400

    purge_folder(QUIZ_FOLDER, QUIZ_MAX_AGE)

    texts = []
    for file in files:
        data = file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return jsonify({"error": f"'{file.filename}' is larger than 10MB."}), 400
        try:
            texts.append(extract_text(file.filename, data))
        except ExtractionError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            del data

    file_content = "\n\n".join(texts).strip()
    if not file_content:
        return jsonify({"error": AI_CODES["3"], "code": 3}), 422
    file_content = file_content[:MAX_CHARS]
    if targets is None:
        targets = auto_targets(file_content)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": build_prompt(targets)},
            {"role": "user", "content": f"Generate quiz questions based on the following text:\n\n{file_content}"},
        ],
        "temperature": 0.4,
        "max_completion_tokens": completion_budget(targets),
        "reasoning_effort": "low",
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
    except requests.RequestException as exc:
        print(f"Groq request failed: {exc}")
        return jsonify({"error": "Could not reach Groq (network error or timeout)."}), 502

    print(f"Groq API Status Code: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Groq API Response: {resp.text}")
        return jsonify({"error": "Groq returned an error. Check the server console."}), 502

    try:
        raw_content = resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError):
        return jsonify({"error": "Unexpected response from Groq."}), 502

    code = re.fullmatch(r"\W*([123])\W*", raw_content.strip())
    if code:
        return jsonify({"error": AI_CODES[code.group(1)], "code": int(code.group(1))}), 422

    quiz_data = parse_quiz_data(raw_content)
    for tier in TIERS:
        quiz_data[tier] = quiz_data[tier][:targets[tier]]
    if not any(quiz_data[t] for t in TIERS):
        return jsonify({"error": "The model's reply couldn't be parsed. Please try again."}), 502

    save_quiz(quiz_data, topic_from_filenames([f.filename for f in files]))
    return jsonify({"redirect": url_for("quiz")}), 200


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )