import os
import mimetypes
import requests
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from dotenv import load_dotenv
import random

load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

UPLOAD_FOLDER = "uploads"
text_file = ".txt"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def parse_quiz_data(raw_content):
    structured_questions = []
    blocks = raw_content.split("<start>")

    for block in blocks:
        if not block.strip():
            continue

        cleaned_block = block.split("<end>")[0]
        tokens = cleaned_block.split("$%/")

        tokens = [t.strip() for t in tokens if t.strip()]

        if not tokens:
            continue

        q_type = None
        for t in tokens:
            if t in ["mcq", "trueorfalse", "numerical", "matching"]:
                q_type = t
                break

        if not q_type:
            continue

        type_idx = tokens.index(q_type)
        data_tokens = tokens[type_idx + 1:]

        if q_type == "mcq" and len(data_tokens) >= 6:
            structured_questions.append({
                "type": "mcq",
                "question": data_tokens[0],
                "options": data_tokens[1:5],
                "answer": data_tokens[5]
            })
        elif q_type == "trueorfalse" and len(data_tokens) >= 2:
            structured_questions.append({
                "type": "trueorfalse",
                "question": data_tokens[0],
                "answer": data_tokens[1]
            })
        elif q_type == "numerical" and len(data_tokens) >= 2:
            structured_questions.append({
                "type": "numerical",
                "question": data_tokens[0],
                "answer": data_tokens[1]
            })
        elif q_type == "matching":
            pairs = data_tokens[1:-1]
            answer_mapping = data_tokens[-1] if len(data_tokens) > 1 else ""

            formatted_pairs = []
            for i in range(0, len(pairs) - 1, 2):
                formatted_pairs.append({
                    "left": pairs[i],
                    "right": pairs[i+1]
                })

            structured_questions.append({
                "type": "matching",
                "question": data_tokens[0],
                "pairs": formatted_pairs,
                "answer": answer_mapping
            })

    print(f"DEBUG: Successfully parsed {len(structured_questions)} questions.")
    return structured_questions


@app.template_filter('shuffle')
def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except:
        return seq

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/quiz")
def quiz():
    questions = session.get("quiz_questions", [])
    print(f"DEBUG: /quiz route accessed. Questions in session: {len(questions)}")
    return render_template("quiz.html", questions=questions)

@app.route("/upload", methods=["POST"])
def upload_file():
    if "fileInput" not in request.files:
        return jsonify({"error": "No file part"}), 400

    files = request.files.getlist("fileInput")

    if not files or files[0].filename == "":
        return jsonify({"error": "No selected file"}), 400

    for file in files:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        file_mime, _ = mimetypes.guess_type(file.filename)
        file_extension = os.path.splitext(file.filename)[1].lower()
        print("-" * 30)
        print(f"File Name: {file.filename}")
        print(f"MIME Type: {file_mime}")
        print(f"Extension: {file_extension}")
        print("-" * 30)

        if file_extension == text_file:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                file_content = f.read()

            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }

            system_prompt = (
                "You should only respond in ONE very long line NO formatting except what I provide. "
                "Do not include any newline characters anywhere NEVER in the response. "
                "Generate questions across 3 strict difficulty tiers: easy, medium, and hard. "
                "Start each entry with the difficulty tier, then the question type. "
                "Formats: "
                "<start>easy$%/mcq$%/question$%/optiona$%/optionb$%/optionc$%/optiond$%/answer<end> "
                "<start>medium$%/matching$%/question$%/loc11$%/loc21$%/loc12$%/loc22$%/answer<end> "
                "<start>hard$%/trueorfalse$%/question$%/answer<end> "
                "<start>hard$%/numerical$%/question$%/answer<end>"
            )

            payload = {
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate quiz questions based on the following text:\n\n{file_content}"}
                ]
            }

            api_response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload
            )

            print(f"Groq API Status Code: {api_response.status_code}")

            if api_response.status_code == 200:
                res_json = api_response.json()
                raw_content = res_json["choices"][0]["message"]["content"]

                parsed_questions = parse_quiz_data(raw_content)
                session["quiz_questions"] = parsed_questions
                session.modified = True

                return jsonify({"redirect": url_for("quiz")}), 200
            else:
                print(f"Groq API Response: {api_response.text}")
                return jsonify({"error": "Failed to fetch completion from Groq."}), 500

    return jsonify({"success": "Files uploaded successfully"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True)