/* ================================================================
   Chat.js — Chat interface + streaming + conversation history
   ================================================================ */

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
    // Partially-streaming open tags not yet closed
    const _REMEMBER_OPEN_RE   = /<remember(?:[^>]*)>[\s\S]*/i;
    const _REMIND_OPEN_RE     = /<remind(?:[^>]*)>[\s\S]*/i;

    function stripSpecialTags(text) {
        return text
            .replace(_REMEMBER_RE, '')
            .replace(_REMIND_RE, '')
            .replace(_SHOWIMAGE_RE, '')
            .replace(_REMEMBER_OPEN_RE, '')
            .replace(_REMIND_OPEN_RE, '')
            .trim();
    }
    // Keep old name as alias so nothing breaks
    const stripRememberTags = stripSpecialTags;

    // ── Split think/thinking blocks from response text ───────────────
    // Handles <think>, <thinking>, case variants, and still-streaming open tags.
    // Returns { thinking: string|null, response: string, streaming: bool }
    const _THINK_OPEN_RE  = /<(think|thinking)>/i;
    const _THINK_CLOSE_RE = /<\/(think|thinking)>/i;

    function splitThinking(raw) {
        if (!raw) return { thinking: null, response: raw };

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
                    endorphin: 'bar-endorphin',
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
    }

    // ── Save conversation ────────────────────────────────────────
    async function saveConversation() {
        try {
            const result = await App.apiPost('/conversations/save', {});
            if (result.error) { App.toast(result.error, 'error'); return; }
            App.toast(`Saved: ${result.title}`, 'success');
        } catch { App.toast('Save failed', 'error'); }
    }

    // ── Show conversation history modal ──────────────────────────
    async function showHistory() {
        const modal = document.getElementById('history-modal');
        const list = document.getElementById('history-list');
        modal.style.display = '';
        list.innerHTML = '<p class="text-muted">Loading…</p>';

        try {
            const convos = await App.api('/conversations');
            if (!convos.length) {
                list.innerHTML = '<p class="text-muted">No saved conversations yet.</p>';
                return;
            }
            list.innerHTML = '';
            convos.forEach(c => {
                const item = document.createElement('div');
                item.className = 'history-item';
                const titleEl = document.createElement('span');
                titleEl.textContent = c.title || c.id;
                titleEl.className = 'history-title';
                const metaEl = document.createElement('span');
                metaEl.className = 'text-muted';
                metaEl.textContent = `${c.message_count} msgs • ${c.preset || ''} • ${c.created || ''}`;
                const actionsEl = document.createElement('div');
                actionsEl.className = 'history-actions';

                const loadBtn = document.createElement('button');
                loadBtn.className = 'btn btn-sm btn-primary';
                loadBtn.textContent = 'Load';
                loadBtn.addEventListener('click', () => loadConversation(c.id));

                const delBtn = document.createElement('button');
                delBtn.className = 'btn btn-sm btn-secondary';
                delBtn.textContent = '🗑️';
                delBtn.addEventListener('click', async () => {
                    if (!confirm('Delete this conversation?')) return;
                    await fetch('/api/conversations/' + c.id, { method: 'DELETE' });
                    showHistory();
                });

                actionsEl.appendChild(loadBtn);
                actionsEl.appendChild(delBtn);

                const infoRow = document.createElement('div');
                infoRow.className = 'history-info';
                infoRow.appendChild(titleEl);
                infoRow.appendChild(metaEl);

                item.appendChild(infoRow);
                item.appendChild(actionsEl);
                list.appendChild(item);
            });
        } catch { list.innerHTML = '<p class="text-muted" style="color:var(--error)">Failed to load.</p>'; }
    }

    // ── Load a saved conversation ────────────────────────────────
    async function loadConversation(id) {
        try {
            const data = await App.api('/conversations/' + id);
            const container = document.getElementById('chat-messages');
            container.innerHTML = '';
            (data.messages || []).forEach(m => {
                // createMessageEl handles <think> splitting for assistant messages
                createMessageEl(m.role, m.content);
            });
            document.getElementById('history-modal').style.display = 'none';
            App.toast('Conversation loaded', 'success');
        } catch { App.toast('Load failed', 'error'); }
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
        const saveBtn = document.getElementById('btn-save-chat');
        const historyBtn = document.getElementById('btn-history');
        const toggleBtn = document.getElementById('btn-toggle-panel');
        const closeHistory = document.getElementById('btn-close-history');
        const historyBackdrop = document.querySelector('#history-modal .modal-backdrop');

        sendBtn.addEventListener('click', send);
        newBtn.addEventListener('click', newChat);
        if (saveBtn) saveBtn.addEventListener('click', saveConversation);
        if (historyBtn) historyBtn.addEventListener('click', showHistory);
        if (closeHistory) closeHistory.addEventListener('click', () => {
            document.getElementById('history-modal').style.display = 'none';
        });
        if (historyBackdrop) historyBackdrop.addEventListener('click', () => {
            document.getElementById('history-modal').style.display = 'none';
        });

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
            // Ctrl+Shift+S — save chat
            if (e.ctrlKey && e.shiftKey && e.key === 'S') { e.preventDefault(); saveConversation(); }
            // Ctrl+Shift+H — history
            if (e.ctrlKey && e.shiftKey && e.key === 'H') { e.preventDefault(); showHistory(); }
            // Escape — close modal
            if (e.key === 'Escape') {
                document.getElementById('history-modal').style.display = 'none';
            }
        });

        updateMemoryPanel();
    }

    return { init, handleMessage };
})();
