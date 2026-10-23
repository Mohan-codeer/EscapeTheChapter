const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const fileNameDisplay = document.getElementById("fileName");
const generateQuizBtn = document.getElementById("generateQuizBtn");

uploadBtn.addEventListener("click", () => {
    fileInput.click();
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        let oversized = false;
        for (let i = 0; i < fileInput.files.length; i++) {
            if (fileInput.files[i].size > 10 * 1024 * 1024) {
                oversized = true;
                break;
            }
        }

        if (oversized) {
            alert("One or more files are too large. Max size is 10MB.");
            fileInput.value = "";
            fileNameDisplay.textContent = "No file selected";
            generateQuizBtn.style.display = "none";
            return;
        }

        if (fileInput.files.length === 1) {
            fileNameDisplay.textContent = `Selected: ${fileInput.files[0].name}`;
        } else {
            fileNameDisplay.textContent = `Selected: ${fileInput.files.length} files`;
        }
        generateQuizBtn.style.display = "block";
    } else {
        fileNameDisplay.textContent = "No file selected";
        generateQuizBtn.style.display = "none";
    }
});

generateQuizBtn.addEventListener("click", () => {
    const formData = new FormData();
    for (let i = 0; i < fileInput.files.length; i++) {
        formData.append("fileInput", fileInput.files[i]);
    }

    fetch("/upload", {
        method: "POST",
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Server returned status ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.redirect) {
            window.location.href = data.redirect;
        } else {
            console.error("No redirect URL provided in response.");
        }
    })
    .catch(error => {
        console.error("Fetch failed with error:", error);
    });
});