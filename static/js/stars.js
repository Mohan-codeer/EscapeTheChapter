(function () {
    const KEY = 'chapterEscape.stars';

    function read() {
        try { return Math.max(0, parseInt(localStorage.getItem(KEY), 10) || 0); }
        catch (e) { return 0; }
    }

    function write(n) {
        try { localStorage.setItem(KEY, String(n)); } catch (e) {}
    }

    function render(pop) {
        const total = read();
        document.querySelectorAll('.stars-count').forEach(el => { el.textContent = total; });
        if (!pop) return;
        document.querySelectorAll('.stars-badge').forEach(badge => {
            badge.classList.remove('pop');
            void badge.offsetWidth;
            badge.classList.add('pop');
        });
    }

    window.Stars = {
        get: read,
        add(n) {
            write(read() + Math.max(0, Math.floor(n)));
            render(true);
            return read();
        }
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => render(false));
    else render(false);
})();