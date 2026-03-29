/* ================================================================
   Characters.js — Character / Agent management page
   Each character has: name, description, personality, system_prompt,
   voice_prompt (for Maya TTS), greeting, and isolated memory.
   ================================================================ */

const CharactersPage = (() => {
    let editingId   = null;   // currently selected char id (null = none)
    let characters  = [];     // local cache of character list
    let activeId    = '';     // active_character_id from settings

    // ── Load all characters ───────────────────────────────────────────────
    async function load() {
        try {
            const [data, settings] = await Promise.all([
                App.api('/characters'),
                App.api('/settings'),
            ]);
            characters = data.characters || [];
            activeId   = settings.active_character_id || '';
            renderList();
        } catch {
            App.toast('Could not load characters', 'error');
        }
    }

    // ── Render character list ─────────────────────────────────────────────
    function renderList() {
        const container = document.getElementById('char-list');
        if (!container) return;
        container.innerHTML = '';

        if (!characters.length) {
            container.innerHTML = '<div class="char-empty">No characters yet. Click <strong>+ New</strong> to create one.</div>';
            return;
        }

        characters.forEach(ch => {
            const card = document.createElement('div');
            card.className = 'char-card'
                + (ch.id === editingId ? ' selected' : '')
                + (ch.id === activeId  ? ' char-active' : '');

            const av = document.createElement('div');
            av.className = 'char-avatar';
            av.textContent = (ch.name || '?')[0].toUpperCase();

            const info = document.createElement('div');
            info.className = 'char-card-info';

            const nameEl = document.createElement('div');
            nameEl.className = 'char-card-name';
            nameEl.textContent = ch.name || 'Unnamed';

            const descEl = document.createElement('div');
            descEl.className = 'char-card-desc';
            descEl.textContent = (ch.description || '').slice(0, 64) || '—';

            info.appendChild(nameEl);
            info.appendChild(descEl);

            if (ch.id === activeId) {
                const badge = document.createElement('span');
                badge.className = 'char-active-badge';
                badge.textContent = 'Active';
                info.appendChild(badge);
            }

            card.appendChild(av);
            card.appendChild(info);
            card.addEventListener('click', () => openEditor(ch.id));
            container.appendChild(card);
        });
    }

    // ── Open editor for a character ───────────────────────────────────────
    function openEditor(charId) {
        editingId = charId;
        renderList();   // highlight selected card

        const char = characters.find(c => c.id === charId) || {};
        const editor = document.getElementById('char-editor');
        editor.innerHTML = buildEditorHTML(char);
        bindEditorEvents(charId);
    }

    function esc(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function buildEditorHTML(char) {
        const isActive = char.id === activeId;
        return `
<div class="char-editor-form">
  <div class="char-editor-header">
    <div class="char-avatar large">${esc((char.name || 'N')[0].toUpperCase())}</div>
    <div style="flex:1">
      <input type="text" id="ce-name" class="input" value="${esc(char.name)}" placeholder="Character name…">
      ${isActive ? '<span class="char-active-badge" style="margin-top:6px;display:inline-block;">Currently Active</span>' : ''}
    </div>
  </div>

  <div class="form-group">
    <label>Description / Background</label>
    <textarea id="ce-description" class="input textarea" rows="3"
      placeholder="Who is this character? Background, traits, quirks…">${esc(char.description)}</textarea>
  </div>

  <div class="form-group">
    <label>Personality</label>
    <textarea id="ce-personality" class="input textarea" rows="2"
      placeholder="Personality traits, speaking style…">${esc(char.personality)}</textarea>
  </div>

  <div class="form-group">
    <label>System Prompt</label>
    <textarea id="ce-system-prompt" class="input textarea" rows="4"
      placeholder="Custom instructions prepended to every turn…">${esc(char.system_prompt)}</textarea>
  </div>

  <div class="form-group">
    <label>Voice Prompt <span class="label-hint">— for Maya TTS (describe the voice naturally)</span></label>
    <textarea id="ce-voice-prompt" class="input textarea" rows="2"
      placeholder="e.g. Female voice in her 20s with a light whimsical tone, soft and warm, conversational pacing">${esc(char.voice_prompt)}</textarea>
  </div>

  <div class="form-group">
    <label>Greeting <span class="label-hint">— sent as first message when activated</span></label>
    <textarea id="ce-greeting" class="input textarea" rows="2"
      placeholder="Hello! How can I help you today?">${esc(char.greeting)}</textarea>
  </div>

  <div class="char-editor-actions">
    <button id="btn-char-activate" class="btn ${isActive ? 'btn-secondary' : 'btn-primary'}">
      ${isActive ? '✓ Deactivate' : '⚡ Activate'}
    </button>
    <button id="btn-char-save" class="btn btn-secondary">Save</button>
    <button id="btn-char-delete" class="btn btn-danger">Delete</button>
  </div>
</div>`;
    }

    function bindEditorEvents(charId) {
        document.getElementById('btn-char-save').addEventListener('click', () => save(charId));
        document.getElementById('btn-char-delete').addEventListener('click', () => del(charId));
        document.getElementById('btn-char-activate').addEventListener('click', () => {
            if (charId === activeId) {
                deactivate();
            } else {
                activate(charId);
            }
        });
    }

    // ── Save ──────────────────────────────────────────────────────────────
    async function save(charId) {
        const updates = {
            name:          document.getElementById('ce-name').value.trim(),
            description:   document.getElementById('ce-description').value,
            personality:   document.getElementById('ce-personality').value,
            system_prompt: document.getElementById('ce-system-prompt').value,
            voice_prompt:  document.getElementById('ce-voice-prompt').value,
            greeting:      document.getElementById('ce-greeting').value,
        };
        if (!updates.name) { App.toast('Name cannot be empty', 'error'); return; }
        try {
            await App.apiPut('/characters/' + charId, updates);
            const idx = characters.findIndex(c => c.id === charId);
            if (idx >= 0) characters[idx] = { ...characters[idx], ...updates };
            renderList();
            App.toast('Character saved', 'success');
        } catch {
            App.toast('Save failed', 'error');
        }
    }

    // ── Activate ──────────────────────────────────────────────────────────
    async function activate(charId) {
        try {
            const data = await App.apiPost('/characters/' + charId + '/activate', {});
            activeId = charId;
            App.toast(`${data.character.name} activated`, 'success');
            renderList();
            openEditor(charId);

            // Show greeting in chat if defined
            const char = characters.find(c => c.id === charId) || {};
            if (char.greeting) {
                App.toast('Greeting: ' + char.greeting.slice(0, 60), 'info');
            }

            // Update chat header badge
            _updateChatBadge(char.name || '');
        } catch {
            App.toast('Activation failed', 'error');
        }
    }

    // ── Deactivate ────────────────────────────────────────────────────────
    async function deactivate() {
        try {
            await fetch('/api/characters/activate', { method: 'DELETE' });
            activeId = '';
            App.toast('Character deactivated', 'info');
            renderList();
            openEditor(editingId);   // re-render editor (button changes)
            _updateChatBadge('');
        } catch {
            App.toast('Deactivate failed', 'error');
        }
    }

    // ── Delete ────────────────────────────────────────────────────────────
    async function del(charId) {
        const char = characters.find(c => c.id === charId);
        if (!confirm(`Delete "${char ? char.name : charId}"? This cannot be undone.`)) return;
        try {
            await fetch('/api/characters/' + charId, { method: 'DELETE' });
            characters = characters.filter(c => c.id !== charId);
            if (activeId === charId) { activeId = ''; _updateChatBadge(''); }
            editingId = null;
            renderList();
            const editor = document.getElementById('char-editor');
            if (editor) editor.innerHTML = '<div class="char-editor-empty"><p>Select a character or create a new one.</p></div>';
            App.toast('Character deleted', 'success');
        } catch {
            App.toast('Delete failed', 'error');
        }
    }

    // ── Create new character ──────────────────────────────────────────────
    async function createNew() {
        try {
            const char = await App.apiPost('/characters', { name: 'New Character' });
            characters.push(char);
            renderList();
            openEditor(char.id);
        } catch {
            App.toast('Could not create character', 'error');
        }
    }

    // ── Update chat header active-character badge ─────────────────────────
    function _updateChatBadge(name) {
        const badge = document.getElementById('active-char-badge');
        if (!badge) return;
        if (name) {
            badge.textContent = name;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    }

    // ── Init ─────────────────────────────────────────────────────────────
    let _initialized = false;
    function init() {
        if (!_initialized) {
            const newBtn = document.getElementById('btn-new-character');
            if (newBtn) newBtn.addEventListener('click', createNew);
            _initialized = true;
        }
        load();
    }

    return { init, load, updateChatBadge: _updateChatBadge };
})();
