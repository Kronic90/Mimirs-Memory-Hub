/* ================================================================
   Agents.js — Agent / persona management page
   Each agent has: name, description, personality, system_prompt,
   preset_type (companion/agent/assistant/character/custom),
   model (optional per-agent override), voice_prompt (Maya TTS),
   greeting, and isolated memory.
   ================================================================ */

const AgentsPage = (() => {
    let editingId   = null;
    let agents      = [];
    let activeId    = '';

    // ── Load all agents ───────────────────────────────────────────────
    async function load() {
        try {
            const [data, settings] = await Promise.all([
                App.api('/characters'),
                App.api('/settings'),
            ]);
            agents   = data.characters || [];
            activeId = settings.active_character_id || '';
            renderList();
        } catch {
            App.toast('Could not load agents', 'error');
        }
    }

    // ── Render agent list ─────────────────────────────────────────────
    function renderList() {
        const container = document.getElementById('agent-list');
        if (!container) return;
        container.innerHTML = '';

        if (!agents.length) {
            container.innerHTML = '<div class="agent-empty">No agents yet. Click <strong>+ New Agent</strong> to create one.</div>';
            return;
        }

        agents.forEach(a => {
            const card = document.createElement('div');
            card.className = 'agent-card'
                + (a.id === editingId ? ' selected' : '')
                + (a.id === activeId  ? ' agent-is-active' : '');

            const av = document.createElement('div');
            av.className = 'agent-avatar';
            av.textContent = (a.name || '?')[0].toUpperCase();

            const info = document.createElement('div');
            info.className = 'agent-card-info';

            const nameEl = document.createElement('div');
            nameEl.className = 'agent-card-name';
            nameEl.textContent = a.name || 'Unnamed';

            const descEl = document.createElement('div');
            descEl.className = 'agent-card-desc';
            const presetLabel = (a.preset_type || 'companion').charAt(0).toUpperCase() + (a.preset_type || 'companion').slice(1);
            descEl.textContent = presetLabel + (a.description ? ' • ' + a.description.slice(0, 40) : '');

            info.appendChild(nameEl);
            info.appendChild(descEl);

            if (a.id === activeId) {
                const badge = document.createElement('span');
                badge.className = 'agent-active-badge';
                badge.textContent = 'Active';
                info.appendChild(badge);
            }

            card.appendChild(av);
            card.appendChild(info);
            card.addEventListener('click', () => openEditor(a.id));
            container.appendChild(card);
        });
    }

    // ── Open editor for an agent ───────────────────────────────────────
    function openEditor(agentId) {
        editingId = agentId;
        renderList();

        const agent = agents.find(a => a.id === agentId) || {};
        const editor = document.getElementById('agent-editor');
        editor.innerHTML = buildEditorHTML(agent);
        bindEditorEvents(agentId);
    }

    function esc(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function buildEditorHTML(agent) {
        const isActive = agent.id === activeId;
        const pt = agent.preset_type || 'companion';
        return `
<div class="agent-editor-form">
  <div class="agent-editor-header">
    <div class="agent-avatar large">${esc((agent.name || 'N')[0].toUpperCase())}</div>
    <div style="flex:1">
      <input type="text" id="ae-name" class="input" value="${esc(agent.name)}" placeholder="Agent name…">
      ${isActive ? '<span class="agent-active-badge" style="margin-top:6px;display:inline-block;">Currently Active</span>' : ''}
    </div>
  </div>

  <div class="form-row">
    <div class="form-group" style="flex:1">
      <label>Preset Type <span class="label-hint">— behaviour profile</span></label>
      <select id="ae-preset-type" class="input input-sm">
        <option value="companion" ${pt==='companion'?'selected':''}>🤝 Companion</option>
        <option value="agent" ${pt==='agent'?'selected':''}>⚡ Agent</option>
        <option value="copilot" ${pt==='copilot'?'selected':''}>💻 Copilot</option>
        <option value="assistant" ${pt==='assistant'?'selected':''}>💼 Assistant</option>
        <option value="character" ${pt==='character'?'selected':''}>🎭 Character</option>
        <option value="custom" ${pt==='custom'?'selected':''}>⚙️ Custom</option>
      </select>
    </div>
    <div class="form-group" style="flex:1">
      <label>Model Override <span class="label-hint">— leave empty to use global</span></label>
      <input type="text" id="ae-model" class="input input-sm" value="${esc(agent.model)}" placeholder="(use global model)">
    </div>
  </div>

  <div class="form-group">
    <label>Description / Background</label>
    <textarea id="ae-description" class="input textarea" rows="3"
      placeholder="Who is this agent? Background, traits, quirks…">${esc(agent.description)}</textarea>
  </div>

  <div class="form-group">
    <label>Personality</label>
    <textarea id="ae-personality" class="input textarea" rows="2"
      placeholder="Personality traits, speaking style…">${esc(agent.personality)}</textarea>
  </div>

  <div class="form-group">
    <label>System Prompt</label>
    <textarea id="ae-system-prompt" class="input textarea" rows="4"
      placeholder="Custom instructions prepended to every turn…">${esc(agent.system_prompt)}</textarea>
  </div>

  <div class="form-group">
    <label>Voice Prompt <span class="label-hint">— for Maya TTS (describe the voice naturally)</span></label>
    <textarea id="ae-voice-prompt" class="input textarea" rows="2"
      placeholder="e.g. Female voice in her 20s with a light whimsical tone, soft and warm, conversational pacing">${esc(agent.voice_prompt)}</textarea>
  </div>

  <div class="form-group">
    <label>Greeting <span class="label-hint">— sent as first message when activated</span></label>
    <textarea id="ae-greeting" class="input textarea" rows="2"
      placeholder="Hello! How can I help you today?">${esc(agent.greeting)}</textarea>
  </div>

  <div class="agent-editor-actions">
    <button id="btn-agent-activate" class="btn ${isActive ? 'btn-secondary' : 'btn-primary'}">
      ${isActive ? '✓ Deactivate' : '⚡ Activate'}
    </button>
    <button id="btn-agent-save" class="btn btn-secondary">Save</button>
    <button id="btn-agent-delete" class="btn btn-danger">Delete</button>
  </div>
</div>`;
    }

    function bindEditorEvents(agentId) {
        document.getElementById('btn-agent-save').addEventListener('click', () => save(agentId));
        document.getElementById('btn-agent-delete').addEventListener('click', () => del(agentId));
        document.getElementById('btn-agent-activate').addEventListener('click', () => {
            if (agentId === activeId) deactivate();
            else activate(agentId);
        });
    }

    // ── Save ──────────────────────────────────────────────────────────────
    async function save(agentId) {
        const updates = {
            name:          document.getElementById('ae-name').value.trim(),
            description:   document.getElementById('ae-description').value,
            personality:   document.getElementById('ae-personality').value,
            system_prompt: document.getElementById('ae-system-prompt').value,
            voice_prompt:  document.getElementById('ae-voice-prompt').value,
            greeting:      document.getElementById('ae-greeting').value,
            preset_type:   document.getElementById('ae-preset-type').value,
            model:         document.getElementById('ae-model').value.trim(),
        };
        if (!updates.name) { App.toast('Name cannot be empty', 'error'); return; }
        try {
            await App.apiPut('/characters/' + agentId, updates);
            const idx = agents.findIndex(a => a.id === agentId);
            if (idx >= 0) agents[idx] = { ...agents[idx], ...updates };
            renderList();
            App.toast('Agent saved', 'success');
            // Refresh chat header dropdown in case name changed
            App.loadAgentDropdown();
        } catch {
            App.toast('Save failed', 'error');
        }
    }

    // ── Activate ──────────────────────────────────────────────────────────
    async function activate(agentId) {
        try {
            await App.apiPost('/characters/' + agentId + '/activate', {});
            activeId = agentId;
            const agent = agents.find(a => a.id === agentId) || {};
            App.toast(`${agent.name || 'Agent'} activated`, 'success');
            renderList();
            openEditor(agentId);

            if (agent.greeting) {
                App.toast('Greeting: ' + agent.greeting.slice(0, 60), 'info');
            }

            // Refresh chat header dropdown
            App.loadAgentDropdown();
            // Reload models if agent has a model override
            if (agent.model) App.loadModels();
        } catch {
            App.toast('Activation failed', 'error');
        }
    }

    // ── Deactivate ────────────────────────────────────────────────────────
    async function deactivate() {
        try {
            await fetch('/api/characters/activate', { method: 'DELETE' });
            activeId = '';
            App.toast('Agent deactivated — Default active', 'info');
            renderList();
            openEditor(editingId);
            App.loadAgentDropdown();
            App.loadModels();
        } catch {
            App.toast('Deactivate failed', 'error');
        }
    }

    // ── Delete ────────────────────────────────────────────────────────────
    async function del(agentId) {
        const agent = agents.find(a => a.id === agentId);
        if (!confirm(`Delete "${agent ? agent.name : agentId}"? This cannot be undone.`)) return;
        try {
            await fetch('/api/characters/' + agentId, { method: 'DELETE' });
            agents = agents.filter(a => a.id !== agentId);
            if (activeId === agentId) activeId = '';
            editingId = null;
            renderList();
            document.getElementById('agent-editor').innerHTML =
                '<div class="agent-editor-empty"><p>Select an agent or create a new one to get started.</p></div>';
            App.toast('Agent deleted', 'success');
            App.loadAgentDropdown();
        } catch {
            App.toast('Delete failed', 'error');
        }
    }

    // ── Create new ────────────────────────────────────────────────────────
    async function createNew() {
        try {
            const agent = await App.apiPost('/characters', { name: 'New Agent', preset_type: 'companion' });
            agents.push(agent);
            renderList();
            openEditor(agent.id);
            App.loadAgentDropdown();
        } catch {
            App.toast('Could not create agent', 'error');
        }
    }

    // ── Import SillyTavern ────────────────────────────────────────────────
    async function importST() {
        const path = prompt('Enter path to SillyTavern character JSON file:');
        if (!path) return;
        try {
            const result = await App.apiPost('/characters/import-sillytavern', { file_path: path });
            if (result.character) {
                agents.push(result.character);
                renderList();
                openEditor(result.character.id);
                App.loadAgentDropdown();
                App.toast(result.message || 'Imported!', 'success');
            }
        } catch (e) {
            App.toast('Import failed: ' + e.message, 'error');
        }
    }

    // ── Init ─────────────────────────────────────────────────────────────
    let _initialized = false;
    function init() {
        if (!_initialized) {
            const newBtn = document.getElementById('btn-new-agent');
            if (newBtn) newBtn.addEventListener('click', createNew);
            const importBtn = document.getElementById('btn-import-st');
            if (importBtn) importBtn.addEventListener('click', importST);
            _initialized = true;
        }
        load();
    }

    return { init, load };
})();
