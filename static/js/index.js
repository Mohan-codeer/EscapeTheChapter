const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const fileNameDisplay = document.getElementById("fileName");
const generateQuizBtn = document.getElementById("generateQuizBtn");
const stepFile = document.getElementById("stepFile");
const stepCount = document.getElementById("stepCount");
const countInput = document.getElementById("countInput");
const countHelp = document.getElementById("countHelp");
const startBtn = document.getElementById("startBtn");
const backBtn = document.getElementById("backBtn");
const statusEl = document.getElementById("status");

const MIN_Q = 3;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 5;
const ALLOWED_EXT = [".txt", ".pdf"];

function setStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? "#dc3545" : "inherit";
}

function countMode() {
    return document.querySelector('input[name="countMode"]:checked').value;
}

uploadBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
    setStatus("", false);
    if (fileInput.files.length === 0) {
        fileNameDisplay.textContent = "No file selected";
        generateQuizBtn.hidden = true;
        return;
    }

    const files = Array.from(fileInput.files);
    let problem = "";
    if (files.length > MAX_FILES) {
        problem = `Select at most ${MAX_FILES} files.`;
    } else if (files.some(f => f.size > MAX_FILE_BYTES)) {
        problem = "One or more files are too large. Max size is 10MB per file.";
    } else if (files.some(f => !ALLOWED_EXT.some(ext => f.name.toLowerCase().endsWith(ext)))) {
        problem = "Only .txt and .pdf files are supported.";
    }
    if (problem) {
        alert(problem);
        fileInput.value = "";
        fileNameDisplay.textContent = "No file selected";
        generateQuizBtn.hidden = true;
        return;
    }

    fileNameDisplay.textContent = fileInput.files.length === 1
        ? `Selected: ${fileInput.files[0].name}`
        : `Selected: ${fileInput.files.length} files`;
    generateQuizBtn.hidden = false;
});

generateQuizBtn.addEventListener("click", () => {
    setStatus("", false);
    stepFile.hidden = true;
    stepCount.hidden = false;
    if (countMode() === "number") countInput.focus();
});

backBtn.addEventListener("click", () => {
    setStatus("", false);
    stepCount.hidden = true;
    stepFile.hidden = false;
});

document.querySelectorAll('input[name="countMode"]').forEach(radio => {
    radio.addEventListener("change", () => {
        const isMax = countMode() === "max";
        countInput.disabled = isMax;
        countHelp.textContent = isMax
            ? "About one question per 40 words of the chapter, up to 90 in total."
            : `At least ${MIN_Q} questions, split across Easy, Medium and Hard. There is no upper limit.`;
    });
});

countInput.addEventListener("keydown", e => { if (e.key === "Enter") startBtn.click(); });

startBtn.addEventListener("click", async () => {
    let count = "max";
    if (countMode() === "number") {
        const n = Number(countInput.value);
        if (!Number.isInteger(n) || n < MIN_Q) {
            setStatus(`Enter a whole number of at least ${MIN_Q}.`, true);
            return;
        }
        count = String(n);
    }

    const formData = new FormData();
    for (const file of fileInput.files) formData.append("fileInput", file);
    formData.append("count", count);

    startBtn.disabled = true;
    backBtn.disabled = true;
    setStatus("Generating quiz... this can take up to a minute.", false);

    try {
        const response = await fetch("/upload", { method: "POST", body: formData });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.redirect) {
            window.location.href = data.redirect;
            return;
        }
        setStatus(data.error || `Server returned status ${response.status}`, true);
    } catch (err) {
        console.error("Fetch failed with error:", err);
        setStatus("Could not reach the server.", true);
    }
    startBtn.disabled = false;
    backBtn.disabled = false;
});