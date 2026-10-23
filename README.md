# Chapter Escape

Chapter Escape turns study material into an escape-room style quiz game. A student uploads a chapter, an AI model writes a graded quiz from it, and the student unlocks a Key, a Gate and finally the Exit by clearing the Easy, Medium and Hard levels.

## The problem

Re-reading a chapter is passive and most students cannot tell what they actually remember. Chapter Escape makes revision active: it generates questions directly from the student's own material, gives immediate feedback, and shows exactly which topics need more work.

## Method

1. **Input.** The student uploads up to 5 `.txt` or text-based `.pdf` files (10MB each). Text is extracted with `pypdf` for PDFs and decoded directly for text files. Files are validated for type, size, page count and password protection, and nothing is stored after processing.
2. **Question count.** The student chooses a number (minimum 3) or "Maximum", which scales with the chapter length at roughly one question per 40 words, capped at 90. The total is split evenly across Easy, Medium and Hard.
3. **Generation.** The text is sent to a large language model (`openai/gpt-oss-120b` through the Groq API) with a strict system prompt. The prompt demands exact counts per difficulty, four question types (multiple choice, true or false, numerical, matching), three progressive hints per question, a short explanation and a topic label. If the passage is empty, too short or too thin, the model returns a single status digit instead of a quiz, and the app turns that into a clear message.
4. **Parsing.** The model answers in a delimiter format (`<start>`, `<end>`, `$%/`) that is easy to validate. The parser normalises answers, tolerates missing hint or topic fields, drops malformed questions and trims each level to the requested count, so one bad question never breaks the quiz.
5. **Play.** The quiz is stored briefly on the server, shown once, then deleted. Questions are answered one at a time.
6. **Scoring.** Each question allows up to 4 attempts. A wrong attempt unlocks the next hint and reduces the marks available (1, 0.6, 0.3, 0.1, then 0). True or false earns nothing after a wrong guess. A level needs 60% to pass.
7. **Game loop.** Passing Easy earns the Key, Medium opens the Gate, Hard reaches the Exit. A failed level can be reviewed and retried.
8. **Feedback.** The final screen awards 1 to 5 stars based on the overall score, adds them to a running star total kept in the browser, and lists the topics where marks were lost so the student knows what to revise.

## Why it works

- Questions come only from the student's own text, so practice matches what they are studying.
- Progressive hints keep students trying instead of giving up, and the mark penalty keeps the score honest.
- Topic labels turn a score into a revision plan.
- The strict output format and defensive parser make AI output reliable enough for a live app.
- Privacy by design: uploads are processed in memory and quizzes are deleted after being viewed.

## Tech stack

- Python and Flask for the backend
- Groq API for question generation
- `pypdf` for PDF text extraction
- Vanilla HTML, CSS and JavaScript for the interface

## Project structure

```
app.py              Flask app, text extraction, prompt, parser, routes
templates/          index.html (upload) and quiz.html (game)
static/css/         Styles for each page
static/js/          index.js (upload flow), quiz.js (game logic), stars.js (star counter)
quizzes/            Temporary generated quizzes, cleared automatically
requirements.txt    Python dependencies
```

## Setup

1. Install Python 3.9 or newer.
2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project folder:

   ```
   GROQ_API_KEY=your_groq_key
   SECRET_KEY=any_long_random_string
   ```

   Optional: `HOST`, `PORT` and `FLASK_DEBUG=1`.

4. Run the app:

   ```
   python app.py
   ```

5. Open http://127.0.0.1:5000

## Limits

- Supported files: `.txt` and PDFs that contain selectable text
- Maximum 5 files, 10MB each, PDFs up to 200 pages
- At most 60,000 characters of text are used per quiz

Youtube Link: https://www.youtube.com/watch?v=0w3T13zY40U
