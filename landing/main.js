/* ─────────────────────────────────────────────
   RoninClips Landing — JavaScript
   Terminal animation, scroll reveals, copy buttons
   ───────────────────────────────────────────── */

(function () {
    'use strict';

    // ── Terminal typing animation ──
    const terminalLines = [
        { type: 'cmd', text: '$ git clone https://github.com/clascuna556171/roninclips.git' },
        { type: 'output', text: 'Cloning into \'roninclips\'...' },
        { type: 'output', text: 'Receiving objects: 100% (247/247), done.' },
        { type: 'cmd', text: '$ cd roninclips && setup.bat' },
        { type: 'info', text: '[✓] PHP 8.3.14 detected' },
        { type: 'info', text: '[✓] Python 3.11.7 detected' },
        { type: 'info', text: '[✓] FFmpeg 7.1 detected' },
        { type: 'warn', text: '[✓] NVIDIA RTX 4070 — CUDA 12.6 enabled' },
        { type: 'output', text: 'Creating .venv ... installing dependencies ...' },
        { type: 'output', text: 'Running migrations ... done.' },
        { type: 'success', text: '⚔ RoninClips is ready at http://127.0.0.1:8000' },
        { type: 'cmd', text: '$ start.bat' },
        { type: 'success', text: '▶ Dashboard launched. Drop a video to begin.' },
    ];

    const terminalOutput = document.getElementById('terminal-output');
    let lineIndex = 0;

    function addTerminalLine() {
        if (lineIndex >= terminalLines.length) return;

        const item = terminalLines[lineIndex];
        const lineEl = document.createElement('div');
        lineEl.classList.add('line');

        const delay = lineIndex * 0.12;
        lineEl.style.animationDelay = `${delay}s`;

        if (item.type === 'cmd') {
            lineEl.innerHTML = `<span class="prompt-sym">$ </span><span class="cmd">${escapeHtml(item.text.substring(2))}</span>`;
        } else {
            lineEl.innerHTML = `<span class="${item.type}">${escapeHtml(item.text)}</span>`;
        }

        terminalOutput.appendChild(lineEl);
        lineIndex++;

        const nextDelay = item.type === 'cmd' ? 600 : 200;
        setTimeout(addTerminalLine, nextDelay);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Start terminal animation when hero is visible
    const heroObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                setTimeout(addTerminalLine, 800);
                heroObserver.disconnect();
            }
        });
    }, { threshold: 0.3 });

    const heroSection = document.getElementById('hero');
    if (heroSection) heroObserver.observe(heroSection);

    // ── Scroll-triggered fade-in ──
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -40px 0px'
    });

    document.querySelectorAll('.feature-card, .pipe-step, .stack-item, .install-card').forEach(el => {
        revealObserver.observe(el);
    });

    // ── Copy buttons ──
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const codeEl = document.getElementById(targetId);
            if (!codeEl) return;

            const text = codeEl.textContent;
            navigator.clipboard.writeText(text).then(() => {
                const original = btn.textContent;
                btn.textContent = 'copied!';
                btn.style.color = 'var(--accent)';
                btn.style.borderColor = 'var(--accent)';
                setTimeout(() => {
                    btn.textContent = original;
                    btn.style.color = '';
                    btn.style.borderColor = '';
                }, 1500);
            }).catch(() => {
                // Fallback for older browsers
                const range = document.createRange();
                range.selectNodeContents(codeEl);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('copy');
                sel.removeAllRanges();
            });
        });
    });

    // ── Nav scroll effect ──
    const nav = document.getElementById('nav');
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;
        if (currentScroll > 100) {
            nav.style.borderBottomColor = 'var(--border)';
        } else {
            nav.style.borderBottomColor = 'var(--border-subtle)';
        }
        lastScroll = currentScroll;
    }, { passive: true });

    // ── Smooth scroll for anchor links ──
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

})();
