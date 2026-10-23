let currentTier = 'easy';
const tiers = ['easy', 'medium', 'hard'];

function getActiveCards() {
    const activeSection = document.getElementById(`tier-${currentTier}`);
    return activeSection ? activeSection.querySelectorAll('.question-card') : [];
}

function updateNavButtons() {
    const activeSection = document.getElementById(`tier-${currentTier}`);
    if (!activeSection) return;

    const cards = activeSection.querySelectorAll('.question-card');
    const activeIndex = Array.from(cards).findIndex(card => card.classList.contains('active'));

    const prevBtn = activeSection.querySelector('.prevBtn');
    const nextBtn = activeSection.querySelector('.nextBtn');
    const submitBtn = activeSection.querySelector('.submitBtn');

    if (prevBtn) prevBtn.disabled = activeIndex === 0;

    if (activeIndex === cards.length - 1) {
        if (nextBtn) nextBtn.style.display = 'none';
        if (submitBtn) submitBtn.style.display = 'block';
    } else {
        if (nextBtn) nextBtn.style.display = 'block';
        if (submitBtn) submitBtn.style.display = 'none';
    }
}

function changeCard(btn, direction) {
    const activeSection = btn.closest('.tier-section');
    const cards = activeSection.querySelectorAll('.question-card');
    let activeIndex = Array.from(cards).findIndex(card => card.classList.contains('active'));

    cards[activeIndex].classList.remove('active');
    activeIndex += direction;
    if (activeIndex < 0) activeIndex = 0;
    if (activeIndex >= cards.length) activeIndex = cards.length - 1;
    cards[activeIndex].classList.add('active');
    updateNavButtons();
}

document.addEventListener('click', function(e) {
    if (e.target.type === 'radio') {
        if (e.target.dataset.wasChecked === 'true') {
            e.target.checked = false;
            e.target.dataset.wasChecked = 'false';
        } else {
            document.querySelectorAll(`input[name="${e.target.name}"]`).forEach(r => r.dataset.wasChecked = 'false');
            e.target.checked = true;
            e.target.dataset.wasChecked = 'true';
        }
    }
});

function allowDrop(ev) {
    ev.preventDefault();
}

function drag(ev) {
    ev.dataTransfer.setData("text/plain", ev.target.dataset.text);
    window.draggedElement = ev.target;
}

function drop(ev, dropZone) {
    ev.preventDefault();
    const text = ev.dataTransfer.getData("text/plain");
    const existingText = dropZone.dataset.assigned;
    const pool = dropZone.closest('.matching-container').querySelector('.draggable-pool');

    if (existingText) {
        const returnItem = document.createElement('div');
        returnItem.className = 'drag-item';
        returnItem.draggable = true;
        returnItem.dataset.text = existingText;
        returnItem.textContent = existingText;
        returnItem.ondragstart = drag;
        pool.appendChild(returnItem);
    }

    dropZone.textContent = text;
    dropZone.dataset.assigned = text;

    if (window.draggedElement) {
        window.draggedElement.remove();
    }
}

function dropToPool(ev) {
    ev.preventDefault();
    if (window.draggedElement && window.draggedElement.classList.contains('drag-item')) {
        ev.currentTarget.appendChild(window.draggedElement);
    }
}

function gradeTier(event, tier) {
    event.preventDefault();
    const activeSection = document.getElementById(`tier-${tier}`);
    const cards = activeSection.querySelectorAll('.question-card');
    let score = 0;
    let total = cards.length;

    cards.forEach((card, index) => {
        const type = card.dataset.type;
        const correctAnswer = card.dataset.answer.trim().toLowerCase();
        const feedbackDiv = card.querySelector('.feedback');
        let userAnswer = "";

        if (type === 'mcq') {
            const selected = card.querySelector(`input[name="q_${tier}_${index}"]:checked`);
            if (selected) {
                const selectedVal = selected.value.trim().toLowerCase();
                const labelText = selected.closest('label').textContent.trim().toLowerCase();
                const optionText = labelText.substring(2).trim();
                userAnswer = (selectedVal === correctAnswer || optionText === correctAnswer) ? correctAnswer : selectedVal;
            }
        } else if (type === 'trueorfalse') {
            const selected = card.querySelector(`input[name="q_${tier}_${index}"]:checked`);
            if (selected) {
                const rawVal = selected.value.trim();
                userAnswer = rawVal;
            }
        } else if (type === 'numerical') {
            const inputField = card.querySelector(`input[name="q_${tier}_${index}"]`);
            if (inputField) userAnswer = inputField.value.trim().toLowerCase();
        }

        if (type !== 'matching') {
            if (userAnswer === correctAnswer ||
                (type === 'trueorfalse' && ((userAnswer === '1' && correctAnswer === 'true') || (userAnswer === '0' && correctAnswer === 'false')))) {
                score++;
                feedbackDiv.innerHTML = `<span class="correct">Correct!</span>`;
            } else {
                feedbackDiv.innerHTML = `<span class="incorrect">Incorrect. Correct answer was: ${card.dataset.answer}</span>`;
            }
        } else {
            score++;
            feedbackDiv.innerHTML = `<span class="correct">Matching reviewed.</span>`;
        }
    });

    const percentage = total > 0 ? (score / total) * 100 : 100;
    const scoreDisplay = document.getElementById('score-display');
    scoreDisplay.innerHTML = `${tier.toUpperCase()} Score: ${score} / ${total} (${percentage.toFixed(1)}%)`;

    if (percentage >= 80) {
        scoreDisplay.innerHTML += ` <span class="correct">- Passed! Unlocking next level...</span>`;
        setTimeout(() => unlockNextTier(tier), 2000);
    } else {
        scoreDisplay.innerHTML += ` <span class="incorrect">- Need at least 80% to advance. Try again!</span>`;
    }

    cards.forEach(card => card.classList.add('active'));
    activeSection.querySelector('.nav-buttons').style.display = 'none';
}

function unlockNextTier(currentTierName) {
    const currentIndex = tiers.indexOf(currentTierName);
    if (currentIndex < tiers.length - 1) {
        const nextTierName = tiers[currentIndex + 1];
        document.getElementById(`tier-${currentTierName}`).style.display = 'none';
        document.getElementById(`tier-${nextTierName}`).style.display = 'block';
        currentTier = nextTierName;
        document.getElementById('current-tier-title').textContent = `${nextTierName.charAt(0).toUpperCase() + nextTierName.slice(1)} Level`;
        document.getElementById('score-display').textContent = "";
        updateNavButtons();
    } else {
        document.getElementById('score-display').textContent = "Congratulations! You have completed all difficulty tiers!";
    }
}

updateNavButtons();