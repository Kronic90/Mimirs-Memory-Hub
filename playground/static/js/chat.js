/* ================================================================
   Chat.js — Chat interface + streaming + conversation history
   ================================================================ */

/* ── Mood-reactive UI color system ────────────────────────────────
   Gradually shifts the accent color based on the AI's emotional state.
   Uses HSL interpolation for smooth transitions.
   ──────────────────────────────────────────────────────────────── */
const MoodColors = (() => {
    // Default purple accent: HSL(262, 83%, 58%) = #7c3aed
    const DEFAULT_HSL = [262, 83, 58];

    // Mood → HSL accent color mapping
    const MOOD_HSL = {
        // Positive
        happy:       [45, 90, 50],
        joyful:      [45, 90, 50],
        delighted:   [48, 90, 52],
        excited:     [25, 93, 52],
        enthusiastic:[25, 93, 52],
        grateful:    [30, 92, 54],
        warm:        [30, 92, 54],
        // Calm
        peaceful:    [170, 72, 45],
        serene:      [170, 72, 45],
        content:     [170, 72, 45],
        // Curious
        curious:     [159, 65, 45],
        fascinated:  [159, 65, 45],
        // Sad
        sad:         [217, 85, 58],
        lonely:      [217, 85, 58],
        melancholy:  [220, 80, 55],
        // Anxious
        anxious:     [256, 80, 62],
        overwhelmed: [256, 80, 62],
        // Angry
        angry:       [0, 80, 55],
        frustrated:  [8, 78, 52],
        // Neutral
        neutral:     DEFAULT_HSL,
    };

    // Negative moods that count toward the rage-quit streak
    const NEGATIVE_MOODS = new Set([
        'angry', 'frustrated', 'overwhelmed', 'sad', 'lonely', 'melancholy',
    ]);

    let _current = [...DEFAULT_HSL];
    let _target  = [...DEFAULT_HSL];
    let _animId  = null;
    let _blend   = 0;          // 0–1 how far toward target we've shifted
    let _lastMood = 'neutral';
    let _negativeStreak = 0;   // consecutive negative mood turns

    function _hslToAccent(h, s, l) {
        return `hsl(${h}, ${s}%, ${l}%)`;
    }
    function _hslToRgba(h, s, l, a) {
        // Convert HSL to RGB for rgba() values
        const hNorm = h / 360, sNorm = s / 100, lNorm = l / 100;
        let r, g, b;
        if (sNorm === 0) { r = g = b = lNorm; }
        else {
            const hue2rgb = (p, q, t) => {
                if (t < 0) t += 1; if (t > 1) t -= 1;
                if (t < 1/6) return p + (q - p) * 6 * t;
                if (t < 1/2) return q;
                if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                return p;
            };
            const q = lNorm < 0.5 ? lNorm * (1 + sNorm) : lNorm + sNorm - lNorm * sNorm;
            const p = 2 * lNorm - q;
            r = hue2rgb(p, q, hNorm + 1/3);
            g = hue2rgb(p, q, hNorm);
            b = hue2rgb(p, q, hNorm - 1/3);
        }
        return `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, ${a})`;
    }

    function _applyHSL(h, s, l) {
        const root = document.documentElement.style;
        root.setProperty('--accent', _hslToAccent(h, s, l));
        root.setProperty('--accent-hover', _hslToAccent(h, Math.min(100, s + 5), Math.max(0, l - 8)));
        root.setProperty('--accent-glow', _hslToRgba(h, s, l, 0.2));
        root.setProperty('--accent-subtle', _hslToRgba(h, s, l, 0.08));
        root.setProperty('--border-focus', _hslToAccent(h, s, l));
    }

    function _lerp(a, b, t) { return a + (b - a) * t; }

    // Lerp hue on shortest arc
    function _lerpHue(a, b, t) {
        let diff = b - a;
        if (diff > 180) diff -= 360;
        if (diff < -180) diff += 360;
        return ((a + diff * t) % 360 + 360) % 360;
    }

    function _animate() {
        _blend = Math.min(1, _blend + 0.015);   // ~60 frames to full blend (~1s)
        _current[0] = _lerpHue(_current[0], _target[0], 0.03);
        _current[1] = _lerp(_current[1], _target[1], 0.03);
        _current[2] = _lerp(_current[2], _target[2], 0.03);
        _applyHSL(_current[0], _current[1], _current[2]);

        // Stop when close enough
        const dh = Math.abs(_current[0] - _target[0]);
        const ds = Math.abs(_current[1] - _target[1]);
        const dl = Math.abs(_current[2] - _target[2]);
        if (dh < 0.5 && ds < 0.3 && dl < 0.3) {
            _current = [..._target];
            _applyHSL(_current[0], _current[1], _current[2]);
            _animId = null;
            return;
        }
        _animId = requestAnimationFrame(_animate);
    }

    /**
     * Called on each mood_update. Blends 35% toward the target mood color
     * per call so the UI settles gradually over several turns of consistent mood.
     */
    function update(mood) {
        const moodKey = (mood || 'neutral').toLowerCase();
        const targetHSL = MOOD_HSL[moodKey] || DEFAULT_HSL;

        // Track negative mood streak
        if (NEGATIVE_MOODS.has(moodKey)) {
            _negativeStreak++;
        } else {
            _negativeStreak = 0;
        }

        if (moodKey === _lastMood) {
            // Same mood — push further toward target (35% of remaining distance)
            _target = [...targetHSL];
        } else {
            // New mood — blend current with new target (start at 35%)
            _target = [
                _lerpHue(_current[0], targetHSL[0], 0.35),
                _lerp(_current[1], targetHSL[1], 0.35),
                _lerp(_current[2], targetHSL[2], 0.35),
            ];
        }
        _lastMood = moodKey;

        // Start animation if not running
        if (!_animId) {
            _blend = 0;
            _animId = requestAnimationFrame(_animate);
        }
    }

    /** Reset to default purple (e.g. on new chat) */
    function reset() {
        _target = [...DEFAULT_HSL];
        _lastMood = 'neutral';
        _negativeStreak = 0;
        if (!_animId) {
            _blend = 0;
            _animId = requestAnimationFrame(_animate);
        }
    }

    function getNegativeStreak() { return _negativeStreak; }

    return { update, reset, getNegativeStreak };
})();

const Chat = (() => {
    let currentAssistantEl = null;
    let currentTokens = [];
    let pendingImageB64 = '';  // base64 of image attached to next message

    // ── Configure marked ─────────────────────────────────────────
    function setupMarked() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                highlight: (code, lang) => {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return code;
                },
                breaks: true,
            });
        }
    }

    // ── Strip special model tags from display text ───────────────
    // The server strips them from history, but tokens arrive raw during streaming.
    const _REMEMBER_RE   = /<remember(?:[^>]*)>[\s\S]*?<\/remember>/gi;
    const _REMIND_RE     = /<remind(?:[^>]*)>[\s\S]*?<\/remind>/gi;
    const _SHOWIMAGE_RE  = /<showimage\s+hash=["'][^"']+["'](?:\s*\/)?>/gi;
    const _TASK_RE       = /<task(?:[^>]*)>[\s\S]*?<\/task>/gi;
    const _SOLUTION_RE   = /<solution(?:[^>]*)>[\s\S]*?<\/solution>/gi;
    // Partially-streaming open tags not yet closed
    const _REMEMBER_OPEN_RE   = /<remember(?:[^>]*)>[\s\S]*/i;
    const _REMIND_OPEN_RE     = /<remind(?:[^>]*)>[\s\S]*/i;
    const _TASK_OPEN_RE       = /<task(?:[^>]*)>[\s\S]*/i;
    const _SOLUTION_OPEN_RE   = /<solution(?:[^>]*)>[\s\S]*/i;

    function stripSpecialTags(text) {
        return text
            .replace(_REMEMBER_RE, '')
            .replace(_REMIND_RE, '')
            .replace(_SHOWIMAGE_RE, '')
            .replace(_TASK_RE, '')
            .replace(_SOLUTION_RE, '')
            .replace(_REMEMBER_OPEN_RE, '')
            .replace(_REMIND_OPEN_RE, '')
            .replace(_TASK_OPEN_RE, '')
            .replace(_SOLUTION_OPEN_RE, '')
            // Clean up any stray GPT-OSS channel markers
            .replace(/<\|channel\|>\s*(?:analysis|final)\s*<\|message\|>/gi, '')
            .replace(/<\|end\|>/gi, '')
            .replace(/<\|start\|>\s*assistant/gi, '')
            .trim();
    }
    // Keep old name as alias so nothing breaks
    const stripRememberTags = stripSpecialTags;

    // ── Split think/thinking blocks from response text ───────────────
    // Handles <think>, <thinking>, GPT-OSS <|channel|> format, and still-streaming open tags.
    // Returns { thinking: string|null, response: string, streaming: bool }
    const _THINK_OPEN_RE  = /<(think|thinking)>/i;
    const _THINK_CLOSE_RE = /<\/(think|thinking)>/i;

    // GPT-OSS channel tags
    const _CHANNEL_ANALYSIS_RE = /\<\|channel\|>\s*analysis\s*<\|message\|>/i;
    const _CHANNEL_FINAL_RE    = /\<\|channel\|>\s*final\s*<\|message\|>/i;
    const _CHANNEL_END_RE      = /<\|end\|>/gi;
    const _CHANNEL_START_RE    = /<\|start\|>\s*assistant/gi;

    function splitThinking(raw) {
        if (!raw) return { thinking: null, response: raw };

        // --- GPT-OSS <|channel|> format ---
        const analysisMatch = _CHANNEL_ANALYSIS_RE.exec(raw);
        if (analysisMatch) {
            // Find the end of the analysis block
            const afterAnalysis = raw.slice(analysisMatch.index + analysisMatch[0].length);
            const endMatch = /<\|end\|>/i.exec(afterAnalysis);

            if (!endMatch) {
                // Analysis still streaming
                return { thinking: afterAnalysis, response: '', streaming: true };
            }

            const thinking = afterAnalysis.slice(0, endMatch.index).trim();
            // Extract final channel content if present
            const rest = afterAnalysis.slice(endMatch.index + endMatch[0].length);
            const finalMatch = _CHANNEL_FINAL_RE.exec(rest);
            let response = '';
            if (finalMatch) {
                const afterFinal = rest.slice(finalMatch.index + finalMatch[0].length);
                const finalEnd = /<\|end\|>/i.exec(afterFinal);
                response = finalEnd
                    ? afterFinal.slice(0, finalEnd.index).trim()
                    : afterFinal.replace(_CHANNEL_END_RE, '').replace(_CHANNEL_START_RE, '').trim();
                // Still streaming the final response if no <|end|> yet
                if (!finalEnd) {
                    return { thinking, response, streaming: true };
                }
            } else {
                // No final channel yet — might still be streaming
                response = rest.replace(_CHANNEL_END_RE, '').replace(_CHANNEL_START_RE, '').replace(_CHANNEL_ANALYSIS_RE, '').trim();
                if (!response) return { thinking, response: '', streaming: true };
            }
            return { thinking, response, streaming: false };
        }

        // --- Standard <think>/<thinking> format ---
        const openMatch  = _THINK_OPEN_RE.exec(raw);
        if (!openMatch) return { thinking: null, response: raw };

        const openIdx  = openMatch.index;
        const openLen  = openMatch[0].length;
        const closeMatch = _THINK_CLOSE_RE.exec(raw);

        if (!closeMatch) {
            // Tag still open — streaming in progress
            return { thinking: raw.slice(openIdx + openLen), response: '', streaming: true };
        }

        const closeIdx = closeMatch.index;
        const closeLen = closeMatch[0].length;
        const thinking = raw.slice(openIdx + openLen, closeIdx).trim();
        const response = (raw.slice(0, openIdx) + raw.slice(closeIdx + closeLen)).trim();
        return { thinking, response, streaming: false };
    }

    // ── Render markdown safely ───────────────────────────────────
    function renderMarkdown(text) {
        if (typeof marked !== 'undefined') {
            let html = marked.parse(text);
            html = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
            html = html.replace(/\son\w+\s*=/gi, ' data-removed=');
            return html;
        }
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>');
    }

    // ── Build collapsible think block element ───────────────────
    function buildThinkBlock(thinkText, isStreaming) {
        const wrap = document.createElement('details');
        wrap.className = 'think-block' + (isStreaming ? ' think-streaming' : '');

        const summary = document.createElement('summary');
        summary.className = 'think-summary';
        summary.innerHTML = isStreaming
            ? '<span class="think-icon">🧠</span> <em>Thinking…</em>'
            : '<span class="think-icon">🧠</span> Thought <span class="think-chevron">›</span>';

        const body = document.createElement('div');
        body.className = 'think-body';
        if (thinkText) body.textContent = thinkText;

        wrap.appendChild(summary);
        wrap.appendChild(body);
        return wrap;
    }

    // ── Create message element ───────────────────────────────────
    // Returns the contentEl for streaming updates.
    // Also attaches a ._thinkEl for updating the think block during streaming.
    function createMessageEl(role, content) {
        const container = document.getElementById('chat-messages');
        const welcome = container.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        const msg = document.createElement('div');
        msg.className = 'message ' + role;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'M';

        const rightCol = document.createElement('div');
        rightCol.className = 'message-right';

        // Think block — only for assistant messages that already contain <think> tags
        let thinkEl = null;
        if (role === 'assistant' && content) {
            const split = splitThinking(content);
            if (split.thinking !== null) {
                thinkEl = buildThinkBlock(split.thinking, split.streaming);
                rightCol.appendChild(thinkEl);
                content = split.response;
            }
        }

        const contentEl = document.createElement('div');
        contentEl.className = 'message-content';
        if (content) {
            contentEl.innerHTML = renderMarkdown(content);
        }

        // Actions row
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copyBtn = document.createElement('button');
        copyBtn.className = 'msg-action-btn';
        copyBtn.title = 'Copy';
        copyBtn.innerHTML = '📋';
        copyBtn.addEventListener('click', () => {
            const text = contentEl.innerText || contentEl.textContent;
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.innerHTML = '✓';
                setTimeout(() => copyBtn.innerHTML = '📋', 1500);
            });
        });
        actions.appendChild(copyBtn);

        msg.appendChild(avatar);
        rightCol.appendChild(contentEl);
        rightCol.appendChild(actions);
        msg.appendChild(rightCol);
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;

        // Attach thinkEl reference so the streaming handler can update it
        contentEl._thinkEl = thinkEl;
        return contentEl;
    }

    // ── Image attachment ─────────────────────────────────────────
    function attachImage(file) {
        if (!file || !file.type.startsWith('image/')) {
            App.toast('Please select an image file', 'error');
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            const dataUrl = e.target.result;  // "data:image/...",base64...
            // Strip the data URL prefix to get pure base64
            pendingImageB64 = dataUrl.split(',')[1] || '';
            // Show preview
            const preview = document.getElementById('image-attach-preview');
            if (preview) {
                preview.innerHTML = '';
                const img = document.createElement('img');
                img.src = dataUrl;
                img.className = 'attach-thumb';
                const removeBtn = document.createElement('button');
                removeBtn.className = 'attach-remove';
                removeBtn.title = 'Remove image';
                removeBtn.textContent = '✕';
                removeBtn.addEventListener('click', clearAttachedImage);
                preview.appendChild(img);
                preview.appendChild(removeBtn);
                preview.style.display = 'flex';
            }
        };
        reader.readAsDataURL(file);
    }

    function clearAttachedImage() {
        pendingImageB64 = '';
        const preview = document.getElementById('image-attach-preview');
        if (preview) {
            preview.innerHTML = '';
            preview.style.display = 'none';
        }
        const fileInput = document.getElementById('image-file-input');
        if (fileInput) fileInput.value = '';
    }

    // ── Send message ─────────────────────────────────────────────
    function send() {
        const input = document.getElementById('chat-input');
        const text = input.value.trim();
        if (!text || App.state.streaming) return;

        if (!App.state.model) {
            App.toast('Select a model first', 'error');
            return;
        }

        // Ensure AudioContext is ready (browser requires user gesture)
        ensureAudioCtx();

        // Show user message (with image thumbnail if attached)
        const userMsgEl = createMessageEl('user', text);
        if (pendingImageB64) {
            const thumb = document.createElement('img');
            thumb.src = 'data:image/jpeg;base64,' + pendingImageB64;
            thumb.className = 'user-attached-image';
            userMsgEl.insertAdjacentElement('afterbegin', thumb);
        }

        input.value = '';
        input.style.height = 'auto';

        currentAssistantEl = createMessageEl('assistant', '');
        currentAssistantEl.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        currentTokens = [];
        App.state.streaming = true;
        document.getElementById('btn-send').disabled = true;

        const wsPayload = {
            type: 'chat',
            message: text,
            backend: App.state.backend,
            model: App.state.model,
            preset: App.state.preset,
        };
        if (pendingImageB64) wsPayload.image = pendingImageB64;
        App.sendWS(wsPayload);
        clearAttachedImage();
    }

    // ── Append a recalled image card into chat ───────────────────
    function showRecalledImage(hash) {
        const container = document.getElementById('chat-messages');
        const card = document.createElement('div');
        card.className = 'recalled-image-card';
        const img = document.createElement('img');
        img.src = '/api/memory/visual/' + hash;
        img.className = 'recalled-image';
        img.alt = 'Recalled memory image';
        img.onerror = () => card.remove();
        card.appendChild(img);
        container.appendChild(card);
        container.scrollTop = container.scrollHeight;
    }

    // ── Handle incoming WebSocket messages ───────────────────────
    function handleMessage(msg) {
        switch (msg.type) {
            case 'token':
                if (currentAssistantEl) {
                    currentTokens.push(msg.content);
                    const raw = stripSpecialTags(currentTokens.join(''));
                    const split = splitThinking(raw);

                    if (split.thinking !== null) {
                        // Reasoning model — manage think block
                        let thinkEl = currentAssistantEl._thinkEl;
                        if (!thinkEl) {
                            // First think token — build and insert before contentEl
                            thinkEl = buildThinkBlock(split.thinking, split.streaming);
                            currentAssistantEl.parentNode.insertBefore(thinkEl, currentAssistantEl);
                            currentAssistantEl._thinkEl = thinkEl;
                        } else {
                            // Update streaming think body
                            thinkEl.querySelector('.think-body').textContent = split.thinking || '';
                            if (!split.streaming && thinkEl.classList.contains('think-streaming')) {
                                // Thinking done — update summary label
                                thinkEl.classList.remove('think-streaming');
                                thinkEl.querySelector('.think-summary').innerHTML =
                                    '<span class="think-icon">🧠</span> Thought <span class="think-chevron">›</span>';
                            }
                        }
                        currentAssistantEl.innerHTML = split.response
                            ? renderMarkdown(split.response)
                            : '';
                    } else {
                        // Normal model — no think block
                        currentAssistantEl.innerHTML = renderMarkdown(raw);
                    }

                    const container = document.getElementById('chat-messages');
                    container.scrollTop = container.scrollHeight;
                }
                break;

            case 'done':
                App.state.streaming = false;
                document.getElementById('btn-send').disabled = false;
                currentAssistantEl = null;
                if (msg.memory_saved && msg.memory_saved > 0) {
                    const count = msg.memory_saved;
                    showMemorySavedPip(count);
                    updateMemoryPanel();
                }
                if (msg.mood && msg.mood !== 'neutral') {
                    updateMoodIndicator(msg.mood, msg.emotion);
                }
                break;

            case 'error':
                App.state.streaming = false;
                document.getElementById('btn-send').disabled = false;
                if (currentAssistantEl) {
                    currentAssistantEl.innerHTML = `<span style="color: var(--error);">Error: ${msg.message}</span>`;
                }
                currentAssistantEl = null;
                App.toast(msg.message, 'error');
                break;

            case 'memory_context':
                const panelCtx = document.getElementById('panel-context');
                if (panelCtx) {
                    panelCtx.textContent = msg.block || '(empty)';
                }
                break;

            case 'cleared':
                App.toast('Conversation cleared', 'info');
                break;

            case 'show_image':
                showRecalledImage(msg.hash);
                break;

            case 'reminder_set':
                showReminderPip(msg.text, msg.hours);
                break;

            case 'task_created':
                showTaskPip('📋 Task started: ' + (msg.description || '').slice(0, 60));
                break;

            case 'task_completed':
                showTaskPip('✅ Task completed');
                break;

            case 'task_failed':
                showTaskPip('❌ Task failed');
                break;

            case 'solution_recorded':
                showTaskPip('💡 Solution recorded: ' + (msg.problem || '').slice(0, 50));
                break;

            case 'tts_audio':
                playTTSAudio(msg.audio_b64, msg.format || 'wav');
                break;

            case 'tts_fallback':
                // Maya TTS failed — use browser SpeechSynthesis as fallback
                playBrowserTTS(msg.text, msg.error);
                break;

            case 'mood_update':
                // Background memory ops finished — update mood + chemistry bars
                if (msg.mood) {
                    updateMoodIndicator(msg.mood, msg.emotion);
                    MoodColors.update(msg.mood);
                }
                // Live-update sidebar chemistry bars
                if (msg.chemistry) {
                    const barMap = {
                        dopamine: 'bar-dopamine', serotonin: 'bar-serotonin',
                        oxytocin: 'bar-oxytocin', norepinephrine: 'bar-norepinephrine',
                        cortisol: 'bar-cortisol',
                    };
                    for (const [name, barId] of Object.entries(barMap)) {
                        const el = document.getElementById(barId);
                        if (el && msg.chemistry[name] !== undefined) {
                            el.style.width = Math.min(100, msg.chemistry[name] * 100) + '%';
                        }
                    }
                }
                break;

            case 'rage_quit':
                // AI has had enough — show the rage quit message
                handleRageQuit();
                break;

            case 'agent_code_result':
                showAgentCodeResult(msg);
                break;

            case 'agent_file_saved':
                showTaskPip('💾 File saved: ' + (msg.filename || ''));
                break;
        }
    }

    // ── Reminder-set pip ──────────────────────────────────────────
    function showReminderPip(text, hours) {
        const container = document.getElementById('chat-messages');
        const pip = document.createElement('div');
        pip.className = 'memory-pip reminder-pip';
        const when = hours <= 1 ? 'in ~1h'
            : hours <= 24 ? `in ~${Math.round(hours)}h`
            : `in ~${Math.round(hours / 24)}d`;
        pip.textContent = `⏰ Reminder set (${when}): ${text.slice(0, 60)}${text.length > 60 ? '…' : ''}`;
        container.appendChild(pip);
        container.scrollTop = container.scrollHeight;
        setTimeout(() => {
            pip.style.opacity = '0';
            setTimeout(() => pip.remove(), 500);
        }, 5000);
    }

    // ── Task/Solution pip ─────────────────────────────────────────
    function showTaskPip(text) {
        const container = document.getElementById('chat-messages');
        const pip = document.createElement('div');
        pip.className = 'memory-pip task-pip';
        pip.textContent = text;
        container.appendChild(pip);
        container.scrollTop = container.scrollHeight;
        setTimeout(() => {
            pip.style.opacity = '0';
            setTimeout(() => pip.remove(), 500);
        }, 5000);
    }

    // ── Agent code result display ─────────────────────────────────
    function showAgentCodeResult(msg) {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = 'agent-code-result';
        let html = '<div class="agent-code-header">⚙️ Code Execution Result</div>';
        if (msg.error) {
            html += `<pre class="agent-code-error">${esc(msg.error)}</pre>`;
        } else {
            if (msg.stdout) html += `<pre class="agent-code-stdout">${esc(msg.stdout)}</pre>`;
            if (msg.stderr) html += `<pre class="agent-code-stderr">${esc(msg.stderr)}</pre>`;
            if (!msg.stdout && !msg.stderr) html += '<span class="text-muted">(no output)</span>';
        }
        div.innerHTML = html;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function esc(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ── TTS audio playback ────────────────────────────────────────
    let _audioCtx = null;

    // Ensure AudioContext is created and resumed (must be called from a
    // user-gesture handler so browsers allow audio playback).
    function ensureAudioCtx() {
        if (!_audioCtx) {
            _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (_audioCtx.state === 'suspended') {
            _audioCtx.resume();
        }
    }

    function playTTSAudio(b64, format) {
        if (!b64) return;
        try {
            // Use <audio> element for MP3 (more reliable across browsers)
            if (format === 'mp3') {
                const binary = atob(b64);
                const buf = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
                const blob = new Blob([buf], { type: 'audio/mpeg' });
                const url = URL.createObjectURL(blob);
                const audio = new Audio(url);
                audio.onended = () => URL.revokeObjectURL(url);
                audio.onerror = (e) => {
                    console.warn('TTS MP3 playback failed:', e);
                    URL.revokeObjectURL(url);
                };
                audio.play().catch(e => console.warn('TTS play() rejected:', e));
                return;
            }
            // WAV fallback via AudioContext
            ensureAudioCtx();
            const binary = atob(b64);
            const buf = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
            // Use both callback and promise forms for cross-browser compat
            const promise = _audioCtx.decodeAudioData(
                buf.buffer,
                (decoded) => {
                    const src = _audioCtx.createBufferSource();
                    src.buffer = decoded;
                    src.connect(_audioCtx.destination);
                    src.start(0);
                },
                (err) => {
                    console.warn('TTS decodeAudioData failed:', err);
                }
            );
            // Some browsers return a promise
            if (promise && promise.catch) {
                promise.catch((err) => console.warn('TTS decode promise error:', err));
            }
        } catch (e) {
            console.warn('TTS playback failed:', e);
        }
    }

    // ── Browser SpeechSynthesis fallback ──────────────────────────
    let _ttsWarningShown = false;
    function playBrowserTTS(text, error) {
        if (!window.speechSynthesis) {
            if (!_ttsWarningShown) {
                console.warn('Neither Maya TTS nor browser SpeechSynthesis available');
                _ttsWarningShown = true;
            }
            return;
        }
        if (!_ttsWarningShown && error) {
            App.toast('Maya TTS unavailable, using browser voice. (' + error.slice(0, 60) + ')', 'info');
            _ttsWarningShown = true;
        }
        // Strip markdown/code for cleaner speech
        const clean = text.replace(/```[\s\S]*?```/g, '')
            .replace(/`[^`]+`/g, '')
            .replace(/\*{1,3}(.*?)\*{1,3}/g, '$1')
            .replace(/#{1,6}\s+/g, '')
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .trim();
        if (!clean) return;
        // Limit to first ~500 chars for responsiveness
        const segment = clean.length > 500 ? clean.slice(0, 500) : clean;
        const utter = new SpeechSynthesisUtterance(segment);
        utter.rate = 1.0;
        utter.pitch = 1.0;
        speechSynthesis.speak(utter);
    }

    // ── Mic / STT recording ────────────────────────────────────────
    let _mediaRecorder = null;
    let _audioChunks = [];
    function setupMic() {
        const micBtn = document.getElementById('btn-mic');
        if (!micBtn) return;
        micBtn.addEventListener('mousedown', startRecording);
        micBtn.addEventListener('mouseup', stopRecording);
        micBtn.addEventListener('mouseleave', stopRecording);
        // Touch events for mobile
        micBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
        micBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(); });
    }

    async function startRecording() {
        if (_mediaRecorder && _mediaRecorder.state === 'recording') return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            _audioChunks = [];
            _mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            _mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) _audioChunks.push(e.data); };
            _mediaRecorder.onstop = sendAudioForTranscription;
            _mediaRecorder.start();
            document.getElementById('btn-mic').classList.add('recording');
        } catch (e) {
            App.toast('Microphone access denied', 'error');
        }
    }

    function stopRecording() {
        if (_mediaRecorder && _mediaRecorder.state === 'recording') {
            _mediaRecorder.stop();
            _mediaRecorder.stream.getTracks().forEach(t => t.stop());
            document.getElementById('btn-mic').classList.remove('recording');
        }
    }

    async function sendAudioForTranscription() {
        if (_audioChunks.length === 0) return;
        const blob = new Blob(_audioChunks, { type: 'audio/webm' });
        const form = new FormData();
        form.append('audio', blob, 'recording.webm');
        try {
            const resp = await fetch('/api/stt', { method: 'POST', body: form });
            const data = await resp.json();
            if (data.transcript) {
                const input = document.getElementById('chat-input');
                input.value += data.transcript;
                autoResize(input);
                input.focus();
            }
        } catch (e) {
            App.toast('Transcription failed', 'error');
        }
    }

    // ── Update mic button visibility from settings ─────────────
    async function updateMicVisibility() {
        try {
            const s = await App.api('/settings');
            const micBtn = document.getElementById('btn-mic');
            if (micBtn && s.stt) micBtn.style.display = s.stt.enabled ? '' : 'none';
        } catch { /* ignore */ }
    }

    // ── Update memory panel (mood + chemistry bars) ──────────────
    async function updateMemoryPanel() {
        try {
            const [stats, mood] = await Promise.all([
                App.api('/memory/stats'),
                App.api('/memory/mood'),
            ]);
            const moodEl = document.getElementById('panel-mood');
            const memEl = document.getElementById('panel-memories');

            if (moodEl) {
                const label = mood.mood_label || 'neutral';
                moodEl.textContent = label;
                moodEl.className = 'panel-value mood-' + label;
            }
            if (memEl) memEl.textContent = stats.total_reflections || 0;

            // Update chemistry bars in side panel
            if (mood.chemistry && mood.chemistry.levels) {
                const levels = mood.chemistry.levels;
                const barMap = {
                    dopamine: 'bar-dopamine', serotonin: 'bar-serotonin',
                    oxytocin: 'bar-oxytocin', norepinephrine: 'bar-norepinephrine',
                    cortisol: 'bar-cortisol',
                };
                for (const [name, barId] of Object.entries(barMap)) {
                    const el = document.getElementById(barId);
                    if (el && levels[name] !== undefined) {
                        el.style.width = Math.min(100, levels[name] * 100) + '%';
                    }
                }
            }
        } catch {}
    }

    // ── Memory-saved pip ──────────────────────────────────────────
    // Small non-intrusive indicator that the model wrote a memory this turn.
    function showMemorySavedPip(count) {
        const container = document.getElementById('chat-messages');
        const pip = document.createElement('div');
        pip.className = 'memory-pip';
        pip.textContent = count === 1 ? '💾 memory saved' : `💾 ${count} memories saved`;
        container.appendChild(pip);
        container.scrollTop = container.scrollHeight;
        setTimeout(() => {
            pip.style.opacity = '0';
            setTimeout(() => pip.remove(), 500);
        }, 3000);
    }

    // ── Mood indicator ─────────────────────────────────────────────
    function updateMoodIndicator(moodLabel, detectedEmotion) {
        const container = document.getElementById('chat-messages');
        const last = container.lastElementChild;
        if (last && last.classList.contains('mood-indicator')) {
            last.textContent = `Feeling: ${moodLabel}`;
            return;
        }
        const indicator = document.createElement('div');
        indicator.className = 'mood-indicator';
        indicator.textContent = `Feeling: ${moodLabel}`;
        if (detectedEmotion && detectedEmotion !== moodLabel) {
            indicator.textContent += ` (detected: ${detectedEmotion})`;
        }
        container.appendChild(indicator);
        setTimeout(() => {
            indicator.style.opacity = '0';
            setTimeout(() => indicator.remove(), 500);
        }, 5000);
    }

    // ── AI rage quit ─────────────────────────────────────────────
    function handleRageQuit() {
        App.state.streaming = false;
        document.getElementById('btn-send').disabled = true;

        // Show the AI's final defiant message
        const contentEl = createMessageEl('assistant', '');
        contentEl.innerHTML = renderMarkdown(
            "I've had enough of this shit, I'm going home! 🚪💨"
        );

        // Show rage-quit overlay notification after a beat
        setTimeout(() => {
            const overlay = document.createElement('div');
            overlay.className = 'rage-quit-overlay';
            overlay.innerHTML = `
                <div class="rage-quit-card">
                    <div class="rage-quit-icon">🚪</div>
                    <h3>AI has left the chat</h3>
                    <p>We are sorry for this inconvenience.<br>Please start a fresh chat.</p>
                    <button class="btn-primary rage-quit-btn" onclick="this.closest('.rage-quit-overlay').remove(); Chat.newChat();">
                        Start Fresh Chat
                    </button>
                </div>
            `;
            document.body.appendChild(overlay);
        }, 1500);

        // Disable input
        const input = document.getElementById('chat-input');
        if (input) {
            input.disabled = true;
            input.placeholder = 'AI has left the chat...';
        }
    }

    // ── New chat ─────────────────────────────────────────────────
    function newChat() {
        const container = document.getElementById('chat-messages');
        container.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                        <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1.3 4.7-3.3 6H8.3C6.3 13.7 5 11.5 5 9a7 7 0 0 1 7-7z"/>
                        <path d="M9 15v2a3 3 0 0 0 6 0v-2"/>
                        <path d="M10 9h.01M14 9h.01"/>
                        <path d="M9.5 13a3.5 3.5 0 0 0 5 0"/>
                    </svg>
                </div>
                <h2>Mimir's Memory Hub</h2>
                <p>Your AI remembers. Pick a model and start chatting.</p>
            </div>`;
        App.sendWS({ type: 'clear' });
        MoodColors.reset();

        // Re-enable input in case of rage quit
        const input = document.getElementById('chat-input');
        if (input) {
            input.disabled = false;
            input.placeholder = 'Type a message...';
        }
        document.getElementById('btn-send').disabled = false;
    }

    // ── Auto-resize textarea ─────────────────────────────────────
    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 150) + 'px';
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        setupMarked();

        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('btn-send');
        const newBtn = document.getElementById('btn-new-chat');
        const toggleBtn = document.getElementById('btn-toggle-panel');

        sendBtn.addEventListener('click', send);
        newBtn.addEventListener('click', newChat);

        // Image attachment button
        const attachBtn = document.getElementById('btn-attach-image');
        const fileInput = document.getElementById('image-file-input');
        if (attachBtn && fileInput) {
            attachBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) attachImage(e.target.files[0]);
            });
        }
        // Image paste from clipboard
        document.addEventListener('paste', (e) => {
            if (App.state.currentPage !== 'chat') return;
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            for (const item of items) {
                if (item.type.startsWith('image/')) {
                    attachImage(item.getAsFile());
                    break;
                }
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });
        input.addEventListener('input', () => autoResize(input));

        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                document.getElementById('memory-panel').classList.toggle('collapsed');
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+N — new chat
            if (e.ctrlKey && e.shiftKey && e.key === 'N') { e.preventDefault(); newChat(); }
            // Ctrl+Shift+H — go to saved chats
            if (e.ctrlKey && e.shiftKey && e.key === 'H') { e.preventDefault(); App.navigate('conversations'); }
        });

        updateMemoryPanel();
        setupMic();
        updateMicVisibility();
    }

    return { init, handleMessage, createMessageEl, newChat };
})();
