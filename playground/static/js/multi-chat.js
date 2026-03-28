/* ================================================================
   Multi-Chat.js — Multi-agent conversation interface with WebSocket
   View modes: combined | tabs | columns
   ================================================================ */

const MultiChatPage = (() => {
    // ── State ────────────────────────────────────────────────────

    let currentConv = null;
    let currentWs = null;
    let currentAgents = [];
    let isStreaming = false;
    let currentViewMode = 'combined';   // 'combined' | 'tabs' | 'columns'
    let activeTab = 'all';              // agent name or 'all'
    let currentSettings = { turn_order: 'user_addresses', max_per_round: 3 };

    // All messages stored for tab/column rebuilding
    let allMessages = [];               // [{speaker, content, id}]

    // Unique color palette for agents
    const AGENT_COLORS = [
        '#667eea', '#f093fb', '#4facfe', '#43e97b',
        '#fa709a', '#fee140', '#a18cd1', '#fda085',
    ];
    const agentColorMap = {};

    function getAgentColor(name) {
        if (!agentColorMap[name]) {
            const idx = Object.keys(agentColorMap).length % AGENT_COLORS.length;
            agentColorMap[name] = AGENT_COLORS[idx];
        }
        return agentColorMap[name];
    }

    // ── WebSocket Management ──────────────────────────────────────

    function connectWebSocket(convId) {
        if (currentWs) currentWs.close();

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        currentWs = new WebSocket(`${proto}//${location.host}/ws/multi-chat/${convId}`);

        currentWs.onopen = () => {
            console.log('Multi-chat WS connected');
        };

        currentWs.onmessage = (evt) => {
            const msg = JSON.parse(evt.data);
            handleWebSocketMessage(msg);
        };

        currentWs.onerror = () => {
            App.toast('Connection error', 'error');
        };

        currentWs.onclose = () => {
            console.log('Multi-chat WS closed');
            currentWs = null;
        };
    }

    function sendMessage(content) {
        if (!currentWs || currentWs.readyState !== WebSocket.OPEN) {
            App.toast('Not connected — reload the conversation', 'error');
            return;
        }
        currentWs.send(JSON.stringify({ type: 'message', content }));
        isStreaming = true;
    }

    // ── Message Routing (view-mode aware) ────────────────────────

    function handleWebSocketMessage(msg) {
        const type = msg.type;

        if (type === 'user_message') {
            const entry = { id: Date.now(), speaker: 'You', content: msg.content };
            allMessages.push(entry);
            appendMessageToViews(entry);
        }
        else if (type === 'token') {
            streamToken(msg.speaker || 'Agent', msg.content);
        }
        else if (type === 'agent_done') {
            finalizeAgent(msg.speaker);
        }
        else if (type === 'error') {
            App.toast(`${msg.speaker || 'Error'}: ${msg.message}`, 'error');
            isStreaming = false;
            enableInput();
        }
        else if (type === 'settings_saved') {
            currentSettings = msg.settings || currentSettings;
            App.toast('Settings saved', 'success');
        }
    }

    function sendSettings(data) {
        if (!currentWs || currentWs.readyState !== WebSocket.OPEN) return;
        currentWs.send(JSON.stringify({ type: 'settings', data }));
    }

    function applySavedSettings(settings) {
        if (!settings) return;
        currentSettings = { ...currentSettings, ...settings };
        const radio = document.querySelector(`input[name="turn-order"][value="${currentSettings.turn_order}"]`);
        if (radio) radio.checked = true;
        const slider = document.getElementById('max-agents-slider');
        const valEl = document.getElementById('max-agents-value');
        if (slider) slider.value = currentSettings.max_per_round || 3;
        if (valEl) valEl.textContent = currentSettings.max_per_round || 3;
    }

    /* Append a complete message to whichever layout is active */
    function appendMessageToViews(entry) {
        const isUser = entry.speaker === 'You';

        if (currentViewMode === 'combined') {
            const scroll = document.getElementById('multi-message-scroll');
            const div = createMessageEl(entry.speaker, entry.content, isUser, entry.id);
            scroll.appendChild(div);
            scroll.scrollTop = scroll.scrollHeight;
        }
        else if (currentViewMode === 'tabs') {
            const scroll = document.getElementById('multi-message-scroll');
            const visible = activeTab === 'all' || activeTab === entry.speaker || isUser;
            const div = createMessageEl(entry.speaker, entry.content, isUser, entry.id);
            div.setAttribute('data-tab-speaker', entry.speaker);
            if (!visible) div.style.display = 'none';
            scroll.appendChild(div);
            if (visible) scroll.scrollTop = scroll.scrollHeight;
        }
        else if (currentViewMode === 'columns') {
            const colId = isUser ? 'col-You' : `col-${entry.speaker}`;
            const colScroll = document.getElementById(colId);
            if (colScroll) {
                const div = createMessageEl(entry.speaker, entry.content, isUser, entry.id);
                colScroll.appendChild(div);
                colScroll.scrollTop = colScroll.scrollHeight;
            }
        }
    }

    /* Stream a token into the active streaming bubble */
    function streamToken(speaker, token) {
        const isUser = speaker === 'You';

        if (currentViewMode === 'combined' || currentViewMode === 'tabs') {
            const scroll = document.getElementById('multi-message-scroll');
            let bubble = scroll.querySelector(`[data-streaming="${CSS.escape(speaker)}"]`);

            if (!bubble) {
                const shouldHide = currentViewMode === 'tabs' && activeTab !== 'all' && activeTab !== speaker;
                bubble = createMessageEl(speaker, '', isUser, `streaming-${speaker}`);
                bubble.setAttribute('data-streaming', speaker);
                bubble.setAttribute('data-tab-speaker', speaker);
                if (shouldHide) bubble.style.display = 'none';
                scroll.appendChild(bubble);
            }

            bubble.querySelector('.message-content').textContent += token;
            if (bubble.style.display !== 'none') scroll.scrollTop = scroll.scrollHeight;
        }
        else if (currentViewMode === 'columns') {
            const colId = `col-${speaker}`;
            const colScroll = document.getElementById(colId);
            if (!colScroll) return;

            let bubble = colScroll.querySelector(`[data-streaming="${CSS.escape(speaker)}"]`);
            if (!bubble) {
                bubble = createMessageEl(speaker, '', isUser, `streaming-${speaker}`);
                bubble.setAttribute('data-streaming', speaker);
                colScroll.appendChild(bubble);
            }

            bubble.querySelector('.message-content').textContent += token;
            colScroll.scrollTop = colScroll.scrollHeight;
        }
    }

    function finalizeAgent(speaker) {
        let content = '';

        if (currentViewMode !== 'columns') {
            const scroll = document.getElementById('multi-message-scroll');
            const bubble = scroll?.querySelector(`[data-streaming="${CSS.escape(speaker)}"]`);
            if (bubble) {
                content = bubble.querySelector('.message-content')?.textContent || '';
                bubble.removeAttribute('data-streaming');
            }
        } else {
            const colScroll = document.getElementById(`col-${speaker}`);
            const bubble = colScroll?.querySelector(`[data-streaming="${CSS.escape(speaker)}"]`);
            if (bubble) {
                content = bubble.querySelector('.message-content')?.textContent || '';
                bubble.removeAttribute('data-streaming');
            }
        }

        if (content) allMessages.push({ id: Date.now(), speaker, content });
        isStreaming = false;
        enableInput();
    }

    // ── Message Element Factory ───────────────────────────────────

    function createMessageEl(speaker, content, isUser, id) {
        const div = document.createElement('div');
        div.className = `message ${isUser ? 'message-user' : 'message-agent'}`;
        div.setAttribute('data-msg-id', id);

        const color = isUser ? 'var(--accent)' : getAgentColor(speaker);
        div.innerHTML = `
            <div class="message-speaker" style="color:${color};">${escapeHtml(speaker)}</div>
            <div class="message-content">${escapeHtml(content)}</div>
        `;
        return div;
    }

    // ── View Mode Logic ───────────────────────────────────────────

    function setViewMode(mode) {
        currentViewMode = mode;

        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });

        const tabsBar = document.getElementById('agent-tabs-bar');
        const singleScroll = document.getElementById('multi-message-scroll');
        const colLayout = document.getElementById('columns-layout');

        if (mode === 'combined') {
            tabsBar.style.display = 'none';
            singleScroll.style.display = '';
            colLayout.style.display = 'none';
            rebuildCombinedView();
        }
        else if (mode === 'tabs') {
            tabsBar.style.display = activeTab ? 'flex' : 'none';
            singleScroll.style.display = '';
            colLayout.style.display = 'none';
            rebuildTabsView(activeTab);
        }
        else if (mode === 'columns') {
            tabsBar.style.display = 'none';
            singleScroll.style.display = 'none';
            colLayout.style.display = 'flex';
            buildColumnsLayout();
            rebuildColumnsView();
        }
    }

    function rebuildCombinedView() {
        const scroll = document.getElementById('multi-message-scroll');
        scroll.innerHTML = '';
        allMessages.forEach(entry => {
            scroll.appendChild(createMessageEl(entry.speaker, entry.content, entry.speaker === 'You', entry.id));
        });
        scroll.scrollTop = scroll.scrollHeight;
    }

    function rebuildTabsView(tab) {
        activeTab = tab;
        const scroll = document.getElementById('multi-message-scroll');
        scroll.innerHTML = '';
        allMessages.forEach(entry => {
            const isUser = entry.speaker === 'You';
            const visible = tab === 'all' || tab === entry.speaker || isUser;
            const div = createMessageEl(entry.speaker, entry.content, isUser, entry.id);
            div.setAttribute('data-tab-speaker', entry.speaker);
            if (!visible) div.style.display = 'none';
            scroll.appendChild(div);
        });
        scroll.scrollTop = scroll.scrollHeight;

        document.querySelectorAll('.agent-tab').forEach(t => {
            const isActive = t.dataset.agent === tab;
            t.classList.toggle('active', isActive);
            if (t.dataset.agent !== 'all') {
                const agentName = t.dataset.agent;
                const color = getAgentColor(agentName);
                t.style.color = isActive ? color : '';
                t.style.borderBottomColor = isActive ? color : 'transparent';
            }
        });
    }

    function buildTabsBar() {
        const bar = document.getElementById('agent-tabs-bar');
        bar.innerHTML = '';

        const allBtn = document.createElement('button');
        allBtn.className = `agent-tab${activeTab === 'all' ? ' active' : ''}`;
        allBtn.dataset.agent = 'all';
        allBtn.textContent = 'All';
        bar.appendChild(allBtn);

        currentAgents.forEach(agent => {
            const color = getAgentColor(agent.name);
            const btn = document.createElement('button');
            btn.className = `agent-tab${activeTab === agent.name ? ' active' : ''}`;
            btn.dataset.agent = agent.name;
            btn.style.color = activeTab === agent.name ? color : '';
            btn.style.borderBottomColor = activeTab === agent.name ? color : 'transparent';
            btn.textContent = agent.name;
            bar.appendChild(btn);
        });

        bar.addEventListener('click', (e) => {
            const tab = e.target.closest('.agent-tab');
            if (tab) rebuildTabsView(tab.dataset.agent);
        });
    }

    function buildColumnsLayout() {
        const layout = document.getElementById('columns-layout');
        layout.innerHTML = '';
        layout.appendChild(buildColumn('You', true));
        currentAgents.forEach(agent => layout.appendChild(buildColumn(agent.name, false)));
    }

    function buildColumn(name, isUser) {
        const col = document.createElement('div');
        col.className = `agent-column${isUser ? ' user-column' : ''}`;
        const color = isUser ? 'var(--text-secondary)' : getAgentColor(name);
        col.innerHTML = `
            <div class="agent-column-header">
                <div class="agent-column-dot" style="background:${color};"></div>
                <div class="agent-column-name">${escapeHtml(name)}</div>
            </div>
            <div class="agent-column-scroll" id="col-${name}"></div>
        `;
        return col;
    }

    function rebuildColumnsView() {
        allMessages.forEach(entry => {
            const isUser = entry.speaker === 'You';
            const colId = `col-${entry.speaker}`;
            const colScroll = document.getElementById(colId);
            if (colScroll) {
                colScroll.appendChild(createMessageEl(entry.speaker, entry.content, isUser, entry.id));
                colScroll.scrollTop = colScroll.scrollHeight;
            }
        });
    }

    // ── Conversation Loading ──────────────────────────────────────

    async function loadCharacters() {
        try {
            const data = await App.api('/characters');
            return data.characters || [];
        } catch { return []; }
    }

    async function loadConversations() {
        try {
            const data = await App.api('/multi-conversations');
            return data.conversations || [];
        } catch { return []; }
    }

    async function loadConversation(convId) {
        try {
            const data = await App.api(`/multi-conversations/${convId}`);
            currentConv = data.meta;
            currentAgents = (data.meta.participants || []).filter(p => p.type !== 'user');

            // Reset
            allMessages = [];
            Object.keys(agentColorMap).forEach(k => delete agentColorMap[k]);
            activeTab = 'all';

            // Assign colors
            currentAgents.forEach(a => getAgentColor(a.name));

            // Load history
            (data.messages || []).forEach(msg => {
                allMessages.push({
                    id: msg.timestamp || Date.now(),
                    speaker: msg.speaker || 'Agent',
                    content: msg.content || '',
                });
            });

            connectWebSocket(convId);
            document.getElementById('multi-conv-select').value = convId;
            renderParticipants();
            buildTabsBar();
            setViewMode(currentViewMode);
            showConversationUI();
            applySavedSettings(data.meta.settings);
            App.toast(`Loaded: ${currentConv.title}`);
        } catch (e) {
            App.toast('Load failed: ' + e.message, 'error');
        }
    }

    async function createConversation() {
        const title = prompt('Conversation title:');
        if (!title) return;

        const chars = await loadCharacters();
        if (chars.length === 0) {
            App.toast('Create a character first', 'info');
            return;
        }

        try {
            const participants = [
                { type: 'user', name: 'You' },
                { type: 'agent', name: chars[0].name, character_id: chars[0].id },
            ];

            const data = await App.api('/multi-conversations', {
                method: 'POST',
                body: JSON.stringify({ title, participants }),
            });

            const sel = document.getElementById('multi-conv-select');
            const opt = document.createElement('option');
            opt.value = data.id;
            opt.textContent = escapeHtml(title);
            sel.appendChild(opt);

            loadConversation(data.id);
        } catch (e) {
            App.toast('Create failed: ' + e.message, 'error');
        }
    }

    // ── UI Helpers ────────────────────────────────────────────────

    function renderParticipants() {
        const container = document.getElementById('participants-list');
        if (!currentConv?.participants) { container.innerHTML = ''; return; }
        container.innerHTML = currentConv.participants.map(p => {
            const color = p.type === 'user' ? 'var(--text-secondary)' : getAgentColor(p.name);
            return `
                <div class="participant-item ${p.type}">
                    <span class="participant-type">${p.type === 'user' ? '👤' : '🤖'}</span>
                    <span class="participant-name" style="color:${color};">${escapeHtml(p.name)}</span>
                </div>`;
        }).join('');
    }

    function showConversationUI() {
        document.getElementById('multi-chat-empty').style.display = 'none';
        document.getElementById('multi-chat-participants').style.display = 'block';
        document.getElementById('multi-chat-messages').style.display = 'flex';
        document.getElementById('multi-chat-input').style.display = 'block';
        document.getElementById('btn-add-agent').style.display = 'inline-flex';
        document.getElementById('view-mode-toggle').style.display = 'flex';
        document.getElementById('btn-conv-settings').style.display = 'inline-flex';
    }

    function hideConversationUI() {
        document.getElementById('multi-chat-empty').style.display = 'flex';
        document.getElementById('multi-chat-participants').style.display = 'none';
        document.getElementById('multi-chat-messages').style.display = 'none';
        document.getElementById('btn-add-agent').style.display = 'none';
        document.getElementById('view-mode-toggle').style.display = 'none';
        document.getElementById('agent-tabs-bar').style.display = 'none';
        document.getElementById('btn-conv-settings').style.display = 'none';
        document.getElementById('conv-settings-drawer').style.display = 'none';
    }

    function enableInput() {
        const inp = document.getElementById('multi-chat-input');
        if (inp) { inp.disabled = false; inp.focus(); }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = String(text ?? '');
        return div.innerHTML;
    }

    // ── Init ──────────────────────────────────────────────────────

    async function init() {
        const convSelect = document.getElementById('multi-conv-select');
        const addAgentBtn = document.getElementById('btn-add-agent');
        const newConvBtn = document.getElementById('btn-new-multi-conv');
        const chatInput = document.getElementById('multi-chat-input');

        const convs = await loadConversations();
        if (convs.length > 0) {
            convSelect.innerHTML = '<option value="">Select conversation…</option>' +
                convs.map(c => `<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
        }

        convSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                loadConversation(e.target.value);
            } else {
                hideConversationUI();
                currentConv = null;
                currentAgents = [];
                allMessages = [];
                if (currentWs) currentWs.close();
            }
        });

        newConvBtn?.addEventListener('click', createConversation);

        addAgentBtn.addEventListener('click', async () => {
            const chars = await loadCharacters();
            if (!chars.length) { App.toast('No characters — create one first', 'info'); return; }

            const names = chars.map(c => c.name).join('\n');
            const selected = prompt(`Select character to add:\n${names}`);
            if (!selected || !currentConv) return;

            const char = chars.find(c => c.name === selected);
            if (!char) { App.toast('Character not found', 'error'); return; }

            currentConv.participants.push({ type: 'agent', name: char.name, character_id: char.id });
            currentAgents = currentConv.participants.filter(p => p.type !== 'user');
            getAgentColor(char.name);

            renderParticipants();
            buildTabsBar();
            if (currentViewMode === 'columns') { buildColumnsLayout(); rebuildColumnsView(); }

            try {
                await App.api(`/multi-conversations/${currentConv.id}`, {
                    method: 'PUT',
                    body: JSON.stringify({ participants: currentConv.participants }),
                });
                App.toast(`Added ${char.name}`);
            } catch (e) {
                App.toast('Save failed: ' + e.message, 'error');
            }
        });

        // View mode toggle
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (currentConv) setViewMode(btn.dataset.mode);
            });
        });

        // Settings gear toggle
        document.getElementById('btn-conv-settings')?.addEventListener('click', () => {
            const drawer = document.getElementById('conv-settings-drawer');
            if (drawer) drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
        });

        // Turn order radios
        document.querySelectorAll('input[name="turn-order"]').forEach(radio => {
            radio.addEventListener('change', () => {
                currentSettings.turn_order = radio.value;
                sendSettings({ turn_order: radio.value });
            });
        });

        // Max agents slider
        const slider = document.getElementById('max-agents-slider');
        const valEl = document.getElementById('max-agents-value');
        slider?.addEventListener('input', () => {
            const v = parseInt(slider.value);
            if (valEl) valEl.textContent = v;
            currentSettings.max_per_round = v;
            sendSettings({ max_per_round: v });
        });

        // Chat input — Enter to send
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && chatInput.value.trim() && !isStreaming) {
                e.preventDefault();
                const msg = chatInput.value.trim();
                chatInput.value = '';
                chatInput.disabled = true;
                sendMessage(msg);
            }
        });
    }

    return { init, loadConversation, setViewMode };
})();
