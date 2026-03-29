/* ================================================================
   Conversations.js — Browse and manage saved conversations
   ================================================================ */

const ConversationsPage = (() => {
    async function loadConversations() {
        const list = document.getElementById('conversations-list');
        list.innerHTML = '<div class="loading">Loading…</div>';

        try {
            const data = await fetch('/api/multi-conversations').then(r => r.json());
            const convs = data.conversations || [];

            if (convs.length === 0) {
                list.innerHTML = '<div class="empty-state">No conversations yet. <a href="#multi-chat">Start one!</a></div>';
                return;
            }

            list.innerHTML = convs.map(conv => `
                <div class="conversation-card" data-conv-id="${conv.id}">
                    <div class="conv-header">
                        <h3>${escapeHtml(conv.title)}</h3>
                        <span class="conv-date">${formatDate(conv.created)}</span>
                    </div>
                    <div class="conv-participants">
                        ${conv.participants.map(p => 
                            `<span class="participant-badge">${escapeHtml(p.name)}</span>`
                        ).join('')}
                    </div>
                    <div class="conv-meta">
                        <span>${conv.last_modified ? 'Modified: ' + formatDate(conv.last_modified) : ''}</span>
                    </div>
                    <div class="conv-actions">
                        <button class="btn btn-small btn-primary btn-open-conv" data-conv-id="${conv.id}">Open</button>
                        <button class="btn btn-small btn-secondary btn-delete-conv" data-conv-id="${conv.id}">Delete</button>
                    </div>
                </div>
            `).join('');

            // Wire up buttons
            document.querySelectorAll('.btn-open-conv').forEach(btn => {
                btn.addEventListener('click', () => {
                    window.location.hash = 'multi-chat';
                    // Set conversation selector to this one
                    setTimeout(() => {
                        MultiChatPage.loadConversation(btn.dataset.convId);
                    }, 100);
                });
            });

            document.querySelectorAll('.btn-delete-conv').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (confirm('Delete this conversation?')) {
                        const convId = btn.dataset.convId;
                        try {
                            await fetch(`/api/multi-conversations/${convId}`, { method: 'DELETE' });
                            loadConversations();
                            App.toast('Conversation deleted');
                        } catch (e) {
                            App.toast('Delete failed: ' + e.message, 'error');
                        }
                    }
                });
            });
        } catch (e) {
            list.innerHTML = `<div class="error">Error loading conversations: ${e.message}</div>`;
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatDate(timestamp) {
        if (!timestamp) return '—';
        const date = new Date(timestamp * 1000 || timestamp);
        return date.toLocaleDateString();
    }

    function init() {
        loadConversations();

        document.getElementById('btn-new-multi-chat').addEventListener('click', () => {
            window.location.hash = 'multi-chat';
        });
    }

    return { init, loadConversations };
})();
