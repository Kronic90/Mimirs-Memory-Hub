/* ================================================================
   Conversations.js — Unified saved chats browser
   Shows both single-agent chats and multi-agent conversations
   ================================================================ */

const ConversationsPage = (() => {
    let allConversations = [];
    let currentFilter = 'all';

    async function loadConversations() {
        const list = document.getElementById('conversations-list');
        list.innerHTML = '<div class="loading">Loading…</div>';

        try {
            // Fetch both single-agent and multi-agent conversations
            const [chats, multiRes] = await Promise.all([
                App.api('/conversations'),
                fetch('/api/multi-conversations').then(r => r.json()).catch(() => ({ conversations: [] })),
            ]);

            const multiConvs = (multiRes.conversations || []).map(c => ({
                id: c.id,
                title: c.title || 'Untitled',
                created: c.created ? new Date(c.created * 1000).toISOString() : '',
                last_modified: c.last_modified ? new Date(c.last_modified * 1000).toISOString() : '',
                message_count: null,
                preset: '',
                agent: '',
                type: 'multi',
                participants: c.participants || [],
            }));

            allConversations = [...(chats || []), ...multiConvs];

            // Sort by last_modified or created, newest first
            allConversations.sort((a, b) => {
                const da = a.last_modified || a.created || '';
                const db = b.last_modified || b.created || '';
                return db.localeCompare(da);
            });

            renderList();
        } catch (e) {
            list.innerHTML = `<div class="error">Error loading conversations: ${e.message}</div>`;
        }
    }

    function renderList() {
        const list = document.getElementById('conversations-list');
        const searchTerm = (document.getElementById('conv-search')?.value || '').toLowerCase();
        const sortMode = document.getElementById('conv-sort')?.value || 'newest';

        let filtered = currentFilter === 'all'
            ? allConversations
            : allConversations.filter(c => c.type === currentFilter);

        // Search filter
        if (searchTerm) {
            filtered = filtered.filter(c => {
                const title = (c.title || '').toLowerCase();
                const agent = (c.agent || '').toLowerCase();
                const preset = (c.preset || '').toLowerCase();
                return title.includes(searchTerm) || agent.includes(searchTerm) || preset.includes(searchTerm);
            });
        }

        // Sort
        filtered = [...filtered];
        switch (sortMode) {
            case 'oldest':
                filtered.sort((a, b) => (a.last_modified || a.created || '').localeCompare(b.last_modified || b.created || ''));
                break;
            case 'a-z':
                filtered.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
                break;
            case 'z-a':
                filtered.sort((a, b) => (b.title || '').localeCompare(a.title || ''));
                break;
            default: // newest
                filtered.sort((a, b) => (b.last_modified || b.created || '').localeCompare(a.last_modified || a.created || ''));
        }

        if (filtered.length === 0) {
            list.innerHTML = '<div class="empty-state" style="padding:40px;text-align:center;color:var(--text-muted);">No saved conversations yet. Start chatting and they\'ll appear here automatically.</div>';
            return;
        }

        list.innerHTML = filtered.map(conv => {
            const isMulti = conv.type === 'multi';
            const badge = isMulti
                ? '<span class="conv-type-badge multi">Multi-Agent</span>'
                : '<span class="conv-type-badge chat">Chat</span>';
            const participants = isMulti && conv.participants
                ? conv.participants.map(p => `<span class="participant-badge">${escapeHtml(p.name)}</span>`).join('')
                : '';
            const meta = [];
            if (conv.message_count != null) meta.push(`${conv.message_count} msgs`);
            if (conv.preset) meta.push(conv.preset);
            if (conv.agent) meta.push(`🤖 ${conv.agent}`);
            const dateStr = formatDate(conv.last_modified || conv.created);

            return `
                <div class="conversation-card" data-conv-id="${escapeHtml(conv.id)}" data-conv-type="${conv.type}">
                    <div class="conv-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            ${badge}
                            <h3 style="margin:0;font-size:0.95rem;">${escapeHtml(conv.title)}</h3>
                        </div>
                        <span class="conv-date">${dateStr}</span>
                    </div>
                    ${participants ? `<div class="conv-participants">${participants}</div>` : ''}
                    ${meta.length ? `<div class="conv-meta"><span class="text-muted" style="font-size:0.8rem;">${meta.join(' • ')}</span></div>` : ''}
                    <div class="conv-actions">
                        <button class="btn btn-small btn-primary btn-open-conv" data-conv-id="${escapeHtml(conv.id)}" data-conv-type="${conv.type}">Open</button>
                        <button class="btn btn-small btn-secondary btn-delete-conv" data-conv-id="${escapeHtml(conv.id)}" data-conv-type="${conv.type}">🗑️ Delete</button>
                    </div>
                </div>`;
        }).join('');

        // Wire up buttons
        document.querySelectorAll('.btn-open-conv').forEach(btn => {
            btn.addEventListener('click', () => openConversation(btn.dataset.convId, btn.dataset.convType));
        });
        document.querySelectorAll('.btn-delete-conv').forEach(btn => {
            btn.addEventListener('click', () => deleteConversation(btn.dataset.convId, btn.dataset.convType));
        });
    }

    async function openConversation(id, type) {
        if (type === 'multi') {
            // Navigate to multi-chat page
            App.navigate('multi-chat');
            setTimeout(() => MultiChatPage.loadConversation(id), 100);
        } else {
            // Load single-agent chat into chat page
            try {
                const data = await App.api('/conversations/' + id);
                const container = document.getElementById('chat-messages');
                container.innerHTML = '';
                (data.messages || []).forEach(m => {
                    Chat.createMessageEl(m.role, m.content);
                });
                App.navigate('chat');
                App.toast('Conversation loaded', 'success');
            } catch {
                App.toast('Failed to load conversation', 'error');
            }
        }
    }

    async function deleteConversation(id, type) {
        if (!confirm('Delete this conversation? This cannot be undone.')) return;
        try {
            if (type === 'multi') {
                await fetch(`/api/multi-conversations/${id}`, { method: 'DELETE' });
            } else {
                await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
            }
            loadConversations();
            App.toast('Conversation deleted');
        } catch (e) {
            App.toast('Delete failed: ' + e.message, 'error');
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function formatDate(timestamp) {
        if (!timestamp) return '—';
        const date = new Date(typeof timestamp === 'number' ? timestamp * 1000 : timestamp);
        if (isNaN(date.getTime())) return '—';
        const now = new Date();
        const diff = now - date;
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';
        return date.toLocaleDateString();
    }

    function init() {
        loadConversations();

        // Filter buttons
        document.querySelectorAll('.conv-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.conv-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.dataset.filter;
                renderList();
            });
        });

        document.getElementById('btn-new-multi-chat').addEventListener('click', () => {
            App.navigate('multi-chat');
        });

        // Search & sort
        const searchInput = document.getElementById('conv-search');
        if (searchInput) searchInput.addEventListener('input', () => renderList());
        const sortSelect = document.getElementById('conv-sort');
        if (sortSelect) sortSelect.addEventListener('change', () => renderList());
    }

    return { init, loadConversations };
})();
