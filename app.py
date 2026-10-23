import json
import os
import random
import re
import secrets
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# A missing SECRET_KEY must not silently fall back to a publicly known string
# (anyone could forge session cookies). Generate a random one instead.
_secret = os.getenv("SECRET_KEY")
if not _secret:
    print("WARNING: SECRET_KEY not set in .env - using a random key (sessions reset on restart).")
    _secret = secrets.token_hex(32)
app.secret_key = _secret

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # matches the 10MB limit in index.js

QUIZ_FOLDER = "quizzes"  # parsed quizzes live on disk: Flask's cookie session caps out at ~4KB
os.makedirs(QUIZ_FOLDER, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
MAX_CHARS = 60000  # keep the prompt inside the model's context window

TIERS = ["easy", "medium", "hard"]
TYPES = ["mcq", "trueorfalse", "numerical", "matching"]

MIN_Q = 3                   # smallest total the user can ask for (one per level at least)
                            # there is no upper limit: ask for as many as you like. If the passage cannot
                            # support that many, the model answers with code "2" (see AI_CODES below).
DEFAULT_HINT = "Re-read the part of the chapter this question is about."
DEFAULT_TOPIC = "General"

# Replies the model may send INSTEAD of a quiz. The prompt tells it to answer with just the digit.
AI_CODES = {
    "1": "This passage may be too short to generate more questions.",
    "2": ("The passage may not contain enough information for the requested number of questions. "
          "Try reducing the number of questions or adding more text."),
    "3": "Please enter a textbook passage before generating questions.",
}


def tier_targets(raw):
    """'max' -> (None, True): as many as the text supports.
    A number -> that many in total, split over the levels, no upper limit."""
    raw = (raw or "max").strip().lower()
    if raw == "max":
        return {t: None for t in TIERS}, True
    n = max(MIN_Q, int(raw))                  # int() raises ValueError for junk, handled by the route
    base, rem = divmod(n, 3)
    return {"easy": base + (rem >= 1), "medium": base + (rem >= 2), "hard": base}, False


def completion_budget(targets, is_max):
    """Output tokens to allow. Every question carries 3 hints, an explanation and a topic, so ~300 tokens each."""
    if is_max:
        return 24000
    return min(32000, 1500 + 300 * sum(targets.values()))


def build_prompt(targets, is_max):
    if is_max:
        amount = ("For each tier write as many good, non-repetitive questions as the text supports, "
                  "at least 3 per tier. Never pad or repeat questions. ")
        too_many = ""
    else:
        total = sum(targets.values())
        amount = (f"Write exactly {targets['easy']} easy, {targets['medium']} medium and {targets['hard']} hard "
                  f"questions ({total} in total). ")
        too_many = ("If the passage is long enough for a quiz but clearly does not contain enough information "
                    f"for {total} distinct questions, reply with ONLY the digit 2. ")
    return (
        "You write quizzes from study material. "
        # --- special replies: a single digit instead of a quiz -------------------------------------------
        "FIRST check the passage. If it is empty or only whitespace, reply with ONLY the digit 3. "
        "If it is too short or too thin to build a worthwhile quiz at all (for example one or two sentences), "
        "reply with ONLY the digit 1. "
        + too_many +
        "When you reply with a digit, output that single digit and nothing else: no words, no punctuation. "
        # --- normal quiz output --------------------------------------------------------------------------
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


# ---------------------------------------------------------------- parsing helpers
def _normalize_mcq(answer, options):
    """Return 'a'-'d' or None. Accepts 'b', 'B)', 'b) Paris' or the option's full text."""
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
    """extras = tokens after the fixed fields -> (hints, explanation, topic) or None.

    Expected: hint1, hint2, hint3, explanation, topic. Shorter replies are tolerated so one sloppy line
    from the model does not throw the whole question away.
    """
    n = len(extras)
    if n >= 5:
        return extras[0:3], extras[3], extras[4]
    if n == 4:                              # three hints and an explanation, no topic
        return extras[0:3], extras[3], DEFAULT_TOPIC
    if n == 3:                              # hint, explanation, topic
        return [extras[0]], extras[1], extras[2]
    if n == 2:                              # hint, explanation
        return [extras[0]], extras[1], DEFAULT_TOPIC
    if n == 1:                              # explanation only
        return [DEFAULT_HINT], extras[0], DEFAULT_TOPIC
    return None


def parse_quiz_data(raw_content):
    """Parse the LLM line into {'easy': [...], 'medium': [...], 'hard': [...]}."""
    quiz = {tier: [] for tier in TIERS}
    skipped = 0

    for block in raw_content.split("<start>")[1:]:
        if "<end>" not in block:
            skipped += 1  # truncated output - the last question is incomplete
            continue
        tokens = [t.strip() for t in block.split("<end>")[0].split("$%/")]
        tokens = [t for t in tokens if t]

        # leading tokens: tier and type, in whichever order the model wrote them
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
        elif q_type == "matching" and len(data) >= 10:   # question + 2 pairs + 3 hints + explanation + topic
            # variable length, so read hint1-3, explanation and topic from the end
            hints, explanation, topic = data[-5:-2], data[-2], data[-1]
            rest = data[1:-5]
            if len(rest) % 2 == 1:                      # model added an 'answer' field anyway - ignore it
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


# ---------------------------------------------------------------- storage
def save_quiz(quiz, topic):
    quiz_id = uuid.uuid4().hex
    with open(os.path.join(QUIZ_FOLDER, f"{quiz_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": topic, "tiers": quiz}, f)
    session["quiz_id"] = quiz_id


def load_quiz():
    """Return (tiers_dict, topic); ({}, '') when nothing valid is stored."""
    quiz_id = session.get("quiz_id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", quiz_id):
        return {}, ""
    try:
        with open(os.path.join(QUIZ_FOLDER, f"{quiz_id}.json"), encoding="utf-8") as f:
            data = json.load(f)
        tiers = data.get("tiers", {})
        for questions in tiers.values():
            for q in questions:
                if "hints" not in q:                 # quizzes saved before progressive hints existed
                    q["hints"] = [q.get("hint") or DEFAULT_HINT]
                q.setdefault("topic", DEFAULT_TOPIC)
        return tiers, data.get("topic", "Chapter Quiz")
    except (OSError, ValueError):
        return {}, ""


def topic_from_filenames(names):
    """'climate_change-notes.txt' -> 'climate change notes' (+N more for several files)."""
    stem = os.path.splitext(secure_filename(names[0]))[0]
    stem = re.sub(r"[_\-]+", " ", stem).strip()[:60] or "Chapter Quiz"
    return stem if len(names) == 1 else f"{stem} +{len(names) - 1} more"


# ---------------------------------------------------------------- routes
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
    if not any(questions.get(t) for t in TIERS):
        return redirect(url_for("index"))
    return render_template("quiz.html", questions=questions, topic=topic)


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "Upload too large (max 10MB)."}), 413


@app.route("/upload", methods=["POST"])
def upload_file():
    files = [f for f in request.files.getlist("fileInput") if f and f.filename]
    if not files:
        return jsonify({"error": "No file selected."}), 400
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY is missing from the server's .env file."}), 500

    try:
        targets, is_max = tier_targets(request.form.get("count"))
    except ValueError:
        return jsonify({"error": "Number of questions must be a whole number or 'maximum'."}), 400

    # Read every file (the old loop returned after the first .txt and silently
    # ignored everything else, including unsupported types).
    texts = []
    for file in files:
        name = secure_filename(file.filename)
        if os.path.splitext(name)[1].lower() != ".txt":
            return jsonify({"error": f"'{file.filename}' is not supported yet - upload .txt files."}), 400
        texts.append(file.read().decode("utf-8", errors="ignore"))

    file_content = "\n\n".join(texts).strip()
    if not file_content:                     # code 3, answered locally so no Groq call is wasted
        return jsonify({"error": AI_CODES["3"], "code": 3}), 422
    file_content = file_content[:MAX_CHARS]

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": build_prompt(targets, is_max)},
            {"role": "user", "content": f"Generate quiz questions based on the following text:\n\n{file_content}"},
        ],
        "temperature": 0.4,
        "max_completion_tokens": completion_budget(targets, is_max),   # grows with the number of questions
        "reasoning_effort": "low",       # gpt-oss: less hidden reasoning, faster reply
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

    # The model answers with a lone digit instead of a quiz when the passage cannot support one.
    code = re.fullmatch(r"\W*([123])\W*", raw_content.strip())
    if code:
        return jsonify({"error": AI_CODES[code.group(1)], "code": int(code.group(1))}), 422

    quiz_data = parse_quiz_data(raw_content)
    for tier in TIERS:                       # the model sometimes writes more than asked for
        if targets[tier] is not None:
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