const tiers = ['easy', 'medium', 'hard'];
const PASS_PERCENT = 60;
const MARKS = [1, 0.6, 0.3, 0.1, 0];
const MAX_WRONG = 4;
const STAR_STEPS = [70, 85, 95, 100];
let currentTier = 'easy';
let starsAwarded = false;

const earned = { key: false, gate: false, exit: false };
const cleared = { easy: false, medium: false, hard: false };

const REWARDS = {
    easy:   { item: 'key',  icon: 'i-key',  name: 'Key found',
              title: 'Key Found!',
              msg: 'You cleared Easy and picked up the Key. It opens the way to Medium.',
              btn: 'Use the Key' },
    medium: { item: 'gate', icon: 'i-gate', name: 'Gate unlocked',
              title: 'Gate Unlocked!',
              msg: 'You cleared Medium and the Gate swings open. Hard is waiting beyond it.',
              btn: 'Open the Gate' },
    hard:   { item: 'exit', icon: 'i-door', name: 'Chapter escaped',
              title: 'You Escaped the Chapter!',
              msg: 'You cleared Easy, Medium and Hard and walked out of the chapter.',
              btn: 'Play Again' }
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const sectionOf = tier => document.getElementById(`tier-${tier}`);
const cardsOf = sec => $$('.question-card', sec);
const activeIndex = sec => cardsOf(sec).findIndex(c => c.classList.contains('active'));

function updateTracker() {
    $$('.p-node').forEach(node => {
        const t = node.dataset.tier;
        const unlocked = t === 'easy' || cleared[tiers[tiers.indexOf(t) - 1]];
        node.dataset.state = cleared[t] ? 'done' : (t === currentTier ? 'active' : (unlocked ? 'open' : 'locked'));
    });
    $$('.p-item').forEach(item => { item.dataset.state = earned[item.dataset.item] ? 'earned' : 'locked'; });
}

function isAnswered(card) {
    const type = card.dataset.type;
    if (type === 'mcq' || type === 'trueorfalse') return !!$('input[type="radio"]:checked', card);
    if (type === 'numerical') return $('.num-input', card).value.trim() !== '';
    if (type === 'matching') return $$('.drop-zone', card).every(z => z.querySelector('.drag-item'));
    return false;
}

function updateControls() {
    const sec = sectionOf(currentTier);
    if (!sec) return;
    const cards = cardsOf(sec);
    if (!cards.length) return;

    const i = activeIndex(sec);
    const card = cards[i];
    const submitted = card.classList.contains('locked');
    const last = i === cards.length - 1;
    const act = $('.actionBtn', sec);

    $('.prevBtn', sec).disabled = i <= 0;
    if (!submitted) {
        act.textContent = 'Submit';
        act.disabled = !isAnswered(card);
    } else {
        act.textContent = last ? 'See results' : 'Next';
        act.disabled = false;
    }
    $('.q-num', sec).textContent = i + 1;
    $$('.dot', sec).forEach((d, k) => d.classList.toggle('current', k === i));
}

function showCard(sec, index) {
    cardsOf(sec).forEach((c, k) => c.classList.toggle('active', k === index));
    updateControls();
}

function stepCard(btn, direction) {
    const sec = btn.closest('.tier-section');
    const n = cardsOf(sec).length;
    showCard(sec, Math.max(0, Math.min(n - 1, activeIndex(sec) + direction)));
}

function primaryAction(tier) {
    const sec = sectionOf(tier);
    const cards = cardsOf(sec);
    const i = activeIndex(sec);
    const card = cards[i];

    if (!card.classList.contains('locked')) {
        if (!isAnswered(card)) return;
        gradeCard(card, tier, i);
        updateControls();
    } else if (i < cards.length - 1) {
        showCard(sec, i + 1);
    } else {
        showResult(tier);
    }
}

function syncOptions(card) {
    $$('.option', card).forEach(o => o.classList.toggle('selected', $('input', o).checked));
}

document.addEventListener('click', function (e) {
    const radio = e.target;
    if (radio.type !== 'radio' || radio.closest('.locked')) return;
    if (radio.dataset.wasChecked === 'true') {
        radio.checked = false;
        radio.dataset.wasChecked = 'false';
    } else {
        $$(`input[name="${radio.name}"]`).forEach(r => r.dataset.wasChecked = 'false');
        radio.dataset.wasChecked = 'true';
    }
    syncOptions(radio.closest('.question-card'));
    updateControls();
});

document.addEventListener('input', e => {
    if (!e.target.matches('.num-input')) return;
    e.target.classList.remove('is-wrong');
    updateControls();
});

document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.matches('.num-input')) {
        e.preventDefault();
        primaryAction(currentTier);
    }
});

let draggedChip = null;
let selectedChip = null;

function refreshZones(container) {
    $$('.drop-zone', container).forEach(zone => {
        const ph = $('.placeholder', zone);
        if (ph) ph.style.display = $('.drag-item', zone) ? 'none' : '';
    });
    updateControls();
}

function placeChip(chip, zone) {
    const container = zone.closest('.matching-container');
    if (chip.closest('.matching-container') !== container) return;
    if (zone.classList.contains('zone-correct') || chip.closest('.zone-correct')) return;
    const pool = $('.draggable-pool', container);
    const existing = $('.drag-item', zone);
    if (existing && existing !== chip) pool.appendChild(existing);
    zone.appendChild(chip);
    refreshZones(container);
}

function returnChip(chip, pool) {
    const container = pool.closest('.matching-container');
    if (chip.closest('.matching-container') !== container) return;
    pool.appendChild(chip);
    refreshZones(container);
}

function clearSelection() {
    if (selectedChip) selectedChip.classList.remove('selected');
    selectedChip = null;
}

function allowDrop(ev) { ev.preventDefault(); }

function drag(ev) {
    draggedChip = ev.target.closest('.drag-item');
    ev.dataTransfer.setData('text/plain', draggedChip ? draggedChip.dataset.text : '');
}

function drop(ev, zone) {
    ev.preventDefault();
    if (zone.closest('.locked') || !draggedChip) return;
    placeChip(draggedChip, zone);
    draggedChip = null;
    clearSelection();
}

function dropToPool(ev) {
    ev.preventDefault();
    const pool = ev.currentTarget;
    if (pool.closest('.locked') || !draggedChip) return;
    returnChip(draggedChip, pool);
    draggedChip = null;
    clearSelection();
}

document.addEventListener('click', function (e) {
    const container = e.target.closest('.matching-container');
    if (!container || container.closest('.locked')) return;
    const chip = e.target.closest('.drag-item');
    const zone = e.target.closest('.drop-zone');
    const pool = e.target.closest('.draggable-pool');

    if (selectedChip && selectedChip.closest('.matching-container') !== container) clearSelection();

    if (zone && selectedChip && selectedChip !== chip) {
        placeChip(selectedChip, zone);
        clearSelection();
    } else if (chip) {
        const wasSelected = chip === selectedChip;
        clearSelection();
        if (!wasSelected) { selectedChip = chip; chip.classList.add('selected'); }
    } else if (pool && selectedChip) {
        returnChip(selectedChip, pool);
        clearSelection();
    }
});

function firstNumber(str) {
    const m = String(str).replace(/,/g, '').match(/-?\d*\.?\d+(?:e[-+]?\d+)?/i);
    return m ? parseFloat(m[0]) : NaN;
}

function marksFor(type, wrong) {
    if (type === 'trueorfalse' && wrong > 0) return 0;
    return MARKS[Math.min(wrong, MARKS.length - 1)];
}

function checkAnswer(card) {
    const type = card.dataset.type;
    const correct = card.dataset.answer.trim().toLowerCase();

    if (type === 'mcq' || type === 'trueorfalse') {
        const sel = $('input[type="radio"]:checked', card);
        return { ok: !!sel && sel.value === correct, sel };
    }

    if (type === 'numerical') {
        const raw = $('.num-input', card).value.trim();
        const want = firstNumber(correct);
        let ok;
        if (Number.isNaN(want)) {
            ok = raw.toLowerCase() === correct;
        } else {
            const got = firstNumber(raw);
            ok = raw !== '' && !Number.isNaN(got) && Math.abs(got - want) <= Math.max(1e-6, Math.abs(want) * 0.001);
        }
        return { ok };
    }

    const rows = $$('.match-row', card);
    const results = rows.map(row => {
        const chip = $('.drag-item', $('.drop-zone', row));
        return { row, ok: !!chip && chip.dataset.text === row.dataset.correct };
    });
    return { ok: results.every(r => r.ok), results };
}

function setHintTitle(card, shown, total) {
    $('.hint-title', card).textContent = total > 1 ? `Hints (${shown} of ${total})` : 'Hint';
}

function revealHint(card, wrong) {
    const hints = $$('.hint-src span', card).map(h => h.textContent);
    if (!hints.length || wrong > hints.length) return false;
    const box = $('details.hint', card);
    const list = $('.hint-list', box);
    const li = document.createElement('li');
    li.textContent = hints[wrong - 1];
    li.className = 'fresh';
    $$('li', list).forEach(x => x.classList.remove('fresh'));
    list.appendChild(li);
    setHintTitle(card, wrong, hints.length);
    box.hidden = false;
    box.open = true;
    return true;
}

function setVerdict(card, kind, text) {
    const fb = $('.feedback', card);
    fb.hidden = false;
    const verdict = $('.verdict', fb);
    verdict.className = 'verdict ' + kind;
    verdict.textContent = text;
}

function wrongAttempt(card, check) {
    const type = card.dataset.type;
    const wrong = (parseInt(card.dataset.wrong, 10) || 0) + 1;
    card.dataset.wrong = String(wrong);

    if (type === 'mcq' || type === 'trueorfalse') {
        const opt = check.sel.closest('.option');
        opt.classList.remove('selected');
        opt.classList.add('is-wrong', 'eliminated');
        check.sel.checked = false;
        check.sel.dataset.wasChecked = 'false';
        check.sel.disabled = true;
    } else if (type === 'numerical') {
        const field = $('.num-input', card);
        field.classList.add('is-wrong');
        field.value = '';
        field.focus();
    } else if (type === 'matching') {
        const pool = $('.draggable-pool', card);
        check.results.forEach(r => {
            const zone = $('.drop-zone', r.row);
            const chip = $('.drag-item', zone);
            if (r.ok) {
                zone.classList.add('zone-correct');
            } else if (chip) {
                pool.appendChild(chip);
            }
        });
        refreshZones(card);
    }

    const left = MAX_WRONG - wrong;
    const gotHint = revealHint(card, wrong);
    let text = 'Not quite.';
    if (type === 'matching') {
        const right = check.results.filter(r => r.ok).length;
        text += ` ${right} of ${check.results.length} matched correctly.`;
    }
    text += gotHint ? ` Hint ${wrong} unlocked.` : '';
    text += ` ${left} ${left === 1 ? 'try' : 'tries'} left.`;
    setVerdict(card, 'retry', text);
}

function finishCard(card, tier, index, check, revealed) {
    const type = card.dataset.type;
    const correct = card.dataset.answer.trim().toLowerCase();
    const wrong = parseInt(card.dataset.wrong, 10) || 0;
    let detail = '';

    if (type === 'mcq' || type === 'trueorfalse') {
        $$('.option', card).forEach(opt => {
            const v = $('input', opt).value;
            opt.classList.remove('selected');
            if (v === correct) { opt.classList.remove('is-wrong', 'eliminated'); opt.classList.add('is-correct'); }
        });
        if (revealed && check.sel) check.sel.closest('.option').classList.add('is-wrong');
        if (revealed) {
            const right = $(`input[value="${correct}"]`, card);
            if (right) detail = 'Correct answer: ' + right.closest('.option').textContent.trim().replace(/\s+/g, ' ');
        }

    } else if (type === 'numerical') {
        const field = $('.num-input', card);
        field.readOnly = true;
        field.classList.remove('is-wrong');
        if (revealed) {
            field.classList.add('is-wrong');
            detail = `Correct answer: ${card.dataset.answer}`;
        } else {
            field.classList.add('is-correct');
        }

    } else if (type === 'matching') {
        check.results.forEach(r => {
            const zone = $('.drop-zone', r.row);
            zone.classList.remove('zone-wrong');
            if (r.ok) { zone.classList.add('zone-correct'); return; }
            zone.classList.add('zone-wrong');
            const note = document.createElement('div');
            note.className = 'correct-note';
            note.textContent = 'Correct: ' + r.row.dataset.correct;
            r.row.appendChild(note);
        });
        if (revealed) {
            const right = check.results.filter(r => r.ok).length;
            detail = `${right} of ${check.results.length} matched correctly.`;
        }
    }

    const marks = revealed ? 0 : marksFor(type, wrong);
    card.classList.add('locked');
    card.dataset.marks = String(marks);
    card.dataset.revealed = revealed ? '1' : '0';

    let kind, text;
    if (revealed)        { kind = 'incorrect'; text = 'Out of tries. ' + detail; }
    else if (wrong === 0) { kind = 'correct';   text = 'Correct!'; }
    else                  { kind = 'partial';   text = `Correct, with ${wrong} ${wrong === 1 ? 'hint' : 'hints'} used.`; }
    setVerdict(card, kind, text.trim());
    $('.explanation', card).hidden = false;

    const dot = $$('.dot', sectionOf(tier))[index];
    dot.classList.remove('ok', 'partial', 'bad');
    dot.classList.add(revealed ? 'bad' : (wrong === 0 ? 'ok' : 'partial'));
}

function gradeCard(card, tier, index) {
    const check = checkAnswer(card);
    if (check.ok) {
        finishCard(card, tier, index, check, false);
        return;
    }
    const wrong = (parseInt(card.dataset.wrong, 10) || 0) + 1;
    if (wrong >= MAX_WRONG) {
        card.dataset.wrong = String(wrong);
        finishCard(card, tier, index, check, true);
    } else {
        wrongAttempt(card, check);
    }
}

function cardMarks(card) {
    return parseFloat(card.dataset.marks) || 0;
}

function cardWrong(card) {
    return parseInt(card.dataset.wrong, 10) || 0;
}

function starsFor(pct) {
    return 1 + STAR_STEPS.filter(step => pct >= step).length;
}

function runStats() {
    const cards = $$('.question-card').filter(c => c.dataset.marks !== undefined);
    const total = cards.length;
    const marks = cards.reduce((sum, c) => sum + cardMarks(c), 0);
    const pct = total ? (marks / total) * 100 : 100;

    const byTopic = new Map();
    cards.forEach(c => {
        const topic = c.dataset.topic || 'General';
        const row = byTopic.get(topic) || { topic, questions: 0, lost: 0, missed: 0 };
        row.questions += 1;
        const lost = 1 - cardMarks(c);
        if (lost > 0.0001) { row.lost += lost; row.missed += 1; }
        byTopic.set(topic, row);
    });
    const weak = Array.from(byTopic.values()).filter(r => r.lost > 0).sort((a, b) => b.lost - a.lost);
    return { pct, weak, stars: starsFor(pct) };
}

function renderFinal(res) {
    const stats = runStats();
    const extra = $('.final-extra', res);
    if (!extra) return;

    $$('.star-big', extra).forEach((star, i) => star.classList.toggle('on', i < stats.stars));
    $('.earned-count', extra).textContent = stats.stars;
    $('.earned-word', extra).textContent = stats.stars === 1 ? 'star' : 'stars';

    const list = $('.weak-list', extra);
    list.textContent = '';
    stats.weak.forEach(row => {
        const li = document.createElement('li');

        const name = document.createElement('span');
        name.className = 'weak-name';
        name.textContent = row.topic;

        const info = document.createElement('span');
        info.className = 'weak-info';
        info.textContent = `${row.missed} of ${row.questions} ${row.questions === 1 ? 'question' : 'questions'} cost you marks (-${row.lost.toFixed(1)})`;

        const bar = document.createElement('span');
        bar.className = 'weak-bar';
        const fill = document.createElement('span');
        fill.style.width = Math.min(100, (row.lost / row.questions) * 100).toFixed(0) + '%';
        bar.appendChild(fill);

        li.append(name, info, bar);
        list.appendChild(li);
    });
    $('.weak-none', extra).hidden = stats.weak.length > 0;
    list.hidden = stats.weak.length === 0;
    extra.hidden = false;

    if (!starsAwarded) {
        starsAwarded = true;
        window.Stars.add(stats.stars);
    }
}

function showResult(tier) {
    const sec = sectionOf(tier);
    const cards = cardsOf(sec);
    const total = cards.length;
    const marks = cards.reduce((sum, c) => sum + cardMarks(c), 0);
    const hintsUsed = cards.reduce((sum, c) => sum + Math.min(cardWrong(c), MAX_WRONG - 1), 0);
    const pct = total ? (marks / total) * 100 : 100;
    const passed = pct >= PASS_PERCENT;
    const isLast = tier === tiers[tiers.length - 1];
    const reward = REWARDS[tier];

    const res = $('.result', sec);
    res.classList.toggle('failed', !passed);
    res.dataset.passed = passed ? '1' : '0';
    $('.ring', res).style.setProperty('--pct', pct.toFixed(1));
    $('.ring-value', res).textContent = Math.round(pct) + '%';
    $('.res-correct', res).textContent = `${Number.isInteger(marks) ? marks : marks.toFixed(1)} / ${total}`;
    $('.res-hints', res).textContent = hintsUsed;

    const rewardBox = $('.reward', res);
    const final = $('.final-extra', res);
    if (final) final.hidden = true;

    if (passed) {
        cleared[tier] = true;
        earned[reward.item] = true;
        $('.res-title', res).textContent = reward.title;
        $('.res-msg', res).textContent = reward.msg;
        $('.resPrimary', res).textContent = reward.btn;
        $('use', rewardBox).setAttribute('href', '#' + reward.icon);
        $('.reward-name', rewardBox).textContent = reward.name;
        rewardBox.hidden = false;
        if (isLast) renderFinal(res);
    } else {
        rewardBox.hidden = true;
        $('.res-title', res).textContent = 'Not quite yet';
        $('.res-msg', res).textContent = `You need at least ${PASS_PERCENT}% of the marks to ${isLast ? 'escape' : 'get the ' + REWARDS[tier].item}. Review your answers, then try again.`;
        $('.resPrimary', res).textContent = 'Retry Level';
    }
    updateTracker();

    $('.quiz-shell', sec).hidden = true;
    res.hidden = false;
    window.scrollTo(0, 0);
}

function resultPrimary(tier) {
    const res = $('.result', sectionOf(tier));
    if (res.dataset.passed === '1') {
        if (tier === tiers[tiers.length - 1]) playAgain();
        else unlockNextTier(tier);
    } else {
        retryTier(tier);
    }
}

function reviewTier(tier) {
    const sec = sectionOf(tier);
    $('.result', sec).hidden = true;
    $('.quiz-shell', sec).hidden = false;
    showCard(sec, 0);
}

function retryTier(tier) {
    const sec = sectionOf(tier);
    clearSelection();

    $$('.question-card', sec).forEach(card => {
        card.classList.remove('locked');
        delete card.dataset.marks;
        delete card.dataset.wrong;
        delete card.dataset.revealed;
        const fb = $('.feedback', card);
        fb.hidden = true;
        $('.explanation', fb).hidden = true;
        $$('.option', card).forEach(o => o.classList.remove('selected', 'is-correct', 'is-wrong', 'eliminated'));
        $$('input[type="radio"]', card).forEach(r => { r.checked = false; r.disabled = false; r.dataset.wasChecked = 'false'; });
        $$('.num-input', card).forEach(t => { t.value = ''; t.readOnly = false; t.classList.remove('is-correct', 'is-wrong'); });
        $$('.correct-note', card).forEach(n => n.remove());

        const hint = $('details.hint', card);
        hint.open = false;
        hint.hidden = true;
        $('.hint-list', hint).textContent = '';

        $$('.matching-container', card).forEach(container => {
            const pool = $('.draggable-pool', container);
            $$('.drag-item', container).sort(() => Math.random() - 0.5).forEach(chip => pool.appendChild(chip));
            $$('.drop-zone', container).forEach(z => z.classList.remove('zone-correct', 'zone-wrong'));
            refreshZones(container);
        });
    });
    $$('.dot', sec).forEach(d => d.classList.remove('ok', 'partial', 'bad'));

    $('.result', sec).hidden = true;
    $('.quiz-shell', sec).hidden = false;
    showCard(sec, 0);
    window.scrollTo(0, 0);
}

function playAgain() {
    tiers.forEach(t => {
        const sec = sectionOf(t);
        if ($('.quiz-shell', sec)) retryTier(t);
        sec.classList.remove('active-tier');
        cleared[t] = false;
    });
    earned.key = false;
    earned.gate = false;
    earned.exit = false;
    starsAwarded = false;
    currentTier = 'easy';
    sectionOf('easy').classList.add('active-tier');
    updateTracker();
    updateControls();
    window.scrollTo(0, 0);
}

function unlockNextTier(tier) {
    const i = tiers.indexOf(tier);
    if (i >= tiers.length - 1) return;
    const next = tiers[i + 1];
    cleared[tier] = true;
    sectionOf(tier).classList.remove('active-tier');
    sectionOf(next).classList.add('active-tier');
    currentTier = next;
    updateTracker();
    updateControls();
    window.scrollTo(0, 0);
}

updateTracker();
updateControls();