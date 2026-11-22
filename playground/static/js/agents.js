/* ================================================================
   Agents.js — Characters page: the character sheet.
   A character has a look (picture), identity (name, nicknames, tagline,
   appearance), personality (traits, how they talk, likes/dislikes, quirks),
   story (backstory, situation, relationship, greetings, example dialogue),
   how they see YOU (what they call you, optional persona override),
   a voice, and advanced model settings — plus their own isolated memory.
   ================================================================ */

const AgentsPage = (() => {
    let editingId = null;
    let agents = [];
    let activeId = '';
    let draft = null;          // working copy of the character being edited
    let dirty = false;
    let currentTab = 'basics';

    const TRAIT_SUGGESTIONS = [
        'Warm', 'Playful', 'Witty', 'Sarcastic', 'Shy', 'Curious', 'Calm', 'Bold',
        'Gentle', 'Protective', 'Chaotic', 'Optimistic', 'Grumpy', 'Mysterious',
        'Romantic', 'Nerdy', 'Dramatic', 'Loyal', 'Mischievous', 'Wise',
        'Anxious', 'Confident', 'Blunt', 'Dreamy', 'Competitive', 'Caring',
    ];
    const TABS = [
        ['basics', '🪪', 'Basics'],
        ['personality', '💫', 'Personality'],
        ['story', '📖', 'Story'],
        ['you', '🫵', 'You'],
        ['voice', '🔊', 'Voice'],
        ['advanced', '⚙️', 'Advanced'],
    ];

    // ── Load ──────────────────────────────────────────────────────────
    async function load() {
        try {
            const [data, settings] = await Promise.all([App.api('/characters'), App.api('/settings')]);
            agents = data.characters || [];
            activeId = settings.active_character_id || '';
            renderList();
            if (editingId && agents.find(a => a.id === editingId)) openEditor(editingId, true);
        } catch {
            App.toast('Could not load characters', 'error');
        }
    }

    function esc(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    const asList = (v) => Array.isArray(v) ? v.filter(Boolean)
        : String(v || '').split(/[,\n]/).map(x => x.trim()).filter(Boolean);

    function avatarHTML(c, cls = '') {
        if (c && c.avatar) {
            return `<div class="agent-avatar has-img ${cls}"><img src="/api/characters/${encodeURIComponent(c.id)}/avatar?v=${c.avatar}" alt=""></div>`;
        }
        return `<div class="agent-avatar ${cls}">${esc(((c && c.name) || '?')[0].toUpperCase())}</div>`;
    }

    // ── List ──────────────────────────────────────────────────────────
    function renderList() {
        const container = document.getElementById('agent-list');
        if (!container) return;
        if (!agents.length) {
            container.innerHTML = '<div class="agent-empty">No characters yet. Click <strong>+ New Character</strong> or import a card.</div>';
            return;
        }
        container.innerHTML = agents.map(a => `
            <div class="agent-card${a.id === editingId ? ' selected' : ''}${a.id === activeId ? ' agent-is-active' : ''}" data-id="${esc(a.id)}">
                ${avatarHTML(a)}
                <div class="agent-card-info">
                    <div class="agent-card-name">${esc(a.name || 'Unnamed')}</div>
                    <div class="agent-card-desc">${esc(a.tagline || (a.description || '').slice(0, 60) || 'No description yet')}</div>
                    ${a.id === activeId ? '<span class="agent-active-badge">Active</span>' : ''}
                </div>
            </div>`).join('');
        container.querySelectorAll('.agent-card').forEach(card =>
            card.addEventListener('click', () => {
                if (dirty && editingId && editingId !== card.dataset.id
                    && !confirm('You have unsaved changes. Leave without saving?')) return;
                openEditor(card.dataset.id);
            }));
    }

    // ── Sheet ─────────────────────────────────────────────────────────
    function openEditor(id, keepTab) {
        editingId = id;
        const src = agents.find(a => a.id === id) || {};
        draft = JSON.parse(JSON.stringify(src));
        draft.nicknames = asList(draft.nicknames);
        draft.traits = asList(draft.traits);
        draft.likes = asList(draft.likes);
        draft.dislikes = asList(draft.dislikes);
        draft.alternate_greetings = Array.isArray(draft.alternate_greetings) ? draft.alternate_greetings : [];
        draft.user_persona = draft.user_persona || { enabled: false, name: '', about: '' };
        dirty = false;
        if (!keepTab) currentTab = 'basics';
        renderList();
        renderSheet();
    }

    function completeness(c) {
        const checks = [
            ['a picture', !!c.avatar], ['a tagline', !!(c.tagline || '').trim()],
            ['some traits', (c.traits || []).length >= 2], ['how they talk', !!(c.speaking_style || '').trim()],
            ['likes', (c.likes || []).length > 0], ['a backstory', (c.description || '').trim().length > 40],
            ['a greeting', !!(c.greeting || '').trim()], ['what they call you', !!(c.user_nickname || '').trim()],
        ];
        const done = checks.filter(x => x[1]).length;
        const next = checks.find(x => !x[1]);
        return { pct: Math.round(done / checks.length * 100), next: next ? next[0] : '' };
    }

    function renderSheet() {
        const editor = document.getElementById('agent-editor');
        if (!editor || !draft) return;
        const isActive = draft.id === activeId;
        const comp = completeness(draft);
        editor.innerHTML = `
<div class="sheet">
  <aside class="sheet-card">
    <div class="sheet-portrait" id="sheet-portrait" title="Click or drop an image to set their picture">
      ${draft.avatar
        ? `<img src="/api/characters/${encodeURIComponent(draft.id)}/avatar?v=${draft.avatar}" alt="">`
        : `<div class="sheet-portrait-empty"><span>${esc((draft.name || '?')[0].toUpperCase())}</span><small>Add a picture</small></div>`}
      <input type="file" id="sheet-avatar-input" accept="image/*" style="display:none;">
    </div>
    ${draft.avatar ? '<button class="link-btn" id="sheet-avatar-remove">Remove picture</button>' : ''}
    <div class="sheet-name">${esc(draft.name || 'Unnamed')}</div>
    ${draft.nicknames.length ? `<div class="sheet-aka">aka ${esc(draft.nicknames.join(', '))}</div>` : ''}
    ${draft.tagline ? `<div class="sheet-tagline">“${esc(draft.tagline)}”</div>` : ''}
    <div class="sheet-traits">${draft.traits.map(t => `<span class="trait-chip static">${esc(t)}</span>`).join('')}</div>
    <div class="sheet-meter" title="How complete this sheet is">
      <div class="sheet-meter-bar"><div style="width:${comp.pct}%"></div></div>
      <div class="sheet-meter-label">${comp.pct === 100 ? 'Fully fleshed out ✨' : `${comp.pct}% — try adding ${esc(comp.next)}`}</div>
    </div>
    <div class="sheet-card-actions">
      <button id="btn-agent-activate" class="btn ${isActive ? 'btn-secondary' : 'btn-primary'}">${isActive ? '✓ Chatting with them' : '💬 Chat with them'}</button>
      <button id="btn-agent-preview" class="btn btn-secondary btn-sm" data-tip="See exactly what the model is told about this character">👁 What the AI sees</button>
    </div>
  </aside>

  <section class="sheet-main">
    <nav class="sheet-tabs">${TABS.map(([k, i, l]) =>
        `<button class="sheet-tab${k === currentTab ? ' active' : ''}" data-tab="${k}">${i} ${l}</button>`).join('')}</nav>
    <div class="sheet-body">${tabHTML(currentTab)}</div>
    <div class="sheet-footer">
      <span class="sheet-dirty" id="sheet-dirty">${dirty ? '● Unsaved changes' : ''}</span>
      <button id="btn-agent-delete" class="btn btn-danger btn-sm">Delete</button>
      <button id="btn-agent-save" class="btn btn-primary">Save</button>
    </div>
  </section>
</div>`;
        bindSheet();
    }

    const field = (key, label, hint, rows, placeholder) => `
      <div class="form-group">
        <label>${label}${hint ? ` <span class="label-hint">— ${hint}</span>` : ''}</label>
        ${rows ? `<textarea class="input textarea" rows="${rows}" data-key="${key}" placeholder="${esc(placeholder || '')}">${esc(draft[key])}</textarea>`
               : `<input type="text" class="input" data-key="${key}" value="${esc(draft[key])}" placeholder="${esc(placeholder || '')}">`}
      </div>`;
    const chips = (key, label, hint, placeholder, suggestions) => `
      <div class="form-group">
        <label>${label}${hint ? ` <span class="label-hint">— ${hint}</span>` : ''}</label>
        <div class="chip-input" data-chips="${key}">
          ${draft[key].map((t, i) => `<span class="trait-chip">${esc(t)}<button data-chip-del="${key}" data-i="${i}" title="Remove">×</button></span>`).join('')}
          <input type="text" placeholder="${esc(placeholder)}" data-chip-add="${key}">
        </div>
        ${suggestions ? `<div class="chip-suggestions">${suggestions.filter(s => !draft[key].some(t => t.toLowerCase() === s.toLowerCase()))
            .map(s => `<button class="trait-chip suggest" data-suggest="${key}">${esc(s)}</button>`).join('')}</div>` : ''}
      </div>`;

    function tabHTML(tab) {
        const n = esc(draft.name || 'they');
        if (tab === 'basics') return `
          ${field('name', 'Name', '', 0, 'e.g. Luna')}
          ${chips('nicknames', 'Nicknames', 'other names people call them', 'Type a nickname and press Enter')}
          ${field('tagline', 'Tagline', 'one line that sums them up', 0, 'e.g. A sleepy witch who runs a midnight bakery')}
          ${field('appearance', 'Appearance', 'what they look like', 3, 'Silver hair in a messy bun, flour on her sleeves, always wearing mismatched socks…')}
          <p class="sheet-tip">💡 Click the picture on the left (or drop an image on it) to give them a face.</p>`;
        if (tab === 'personality') return `
          ${chips('traits', 'Traits', 'click suggestions or type your own', 'Add a trait…', TRAIT_SUGGESTIONS)}
          <button class="btn btn-secondary btn-sm" id="btn-surprise">🎲 Surprise me</button>
          ${field('personality', 'Personality', 'in your own words', 3, `What makes ${n} tick? How do they react when things go wrong?`)}
          ${field('speaking_style', 'How they talk', 'voice, slang, catchphrases', 2, 'Short, teasing sentences. Calls everyone "darling". Uses lots of baking puns.')}
          <div class="form-row">
            <div style="flex:1">${chips('likes', 'Loves', '', 'Add something they love…')}</div>
            <div style="flex:1">${chips('dislikes', "Can't stand", '', 'Add something they hate…')}</div>
          </div>
          ${field('quirks', 'Quirks & habits', '', 2, 'Hums when nervous. Names every houseplant.')}`;
        if (tab === 'story') return `
          ${field('description', 'Backstory', 'who they are and where they come from', 5, 'Their history, job, people in their life…')}
          ${field('scenario', 'The situation', 'where and when your chats take place', 3, 'It\'s late at night in her bakery; you\'re the only customer who still comes by.')}
          ${field('relationship', 'Your relationship', 'how they know you', 2, 'Old friends from university who lost touch and just reconnected.')}
          ${field('greeting', 'First message', 'what they say when a new chat starts', 3, 'Oh! You came back. Sit down, the kettle\'s on…')}
          <div class="form-group">
            <label>Other greetings <span class="label-hint">— one is picked at random for variety</span></label>
            <div id="alt-greetings">${draft.alternate_greetings.map((g, i) => `
              <div class="alt-greeting"><textarea class="input textarea" rows="2" data-alt="${i}">${esc(g)}</textarea>
              <button class="btn btn-secondary btn-sm" data-alt-del="${i}" title="Remove">×</button></div>`).join('')}</div>
            <button class="btn btn-secondary btn-sm" id="btn-alt-add">+ Add a greeting</button>
          </div>
          ${field('example_dialogue', 'Example dialogue', 'shows the model how they talk — never treated as a real memory', 4, '{{user}}: Morning!\n{{char}}: *yawns* It\'s 3pm, darling.')}`;
        if (tab === 'you') {
            const gp = (App.state.settings && App.state.settings.user_persona) || {};
            const up = draft.user_persona;
            return `
          ${field('user_nickname', `What ${n} calls you`, 'a pet name or nickname', 0, 'e.g. sunshine, boss, partner')}
          <div class="sheet-box">
            <div class="sheet-box-title">Who you are</div>
            <p class="text-muted" style="font-size:13px;margin:4px 0 8px;">
              ${gp.name || gp.about
                ? `By default ${n} knows you as <strong>${esc(gp.name || 'you')}</strong>${gp.about ? ` — “${esc(gp.about.slice(0, 120))}${gp.about.length > 120 ? '…' : ''}”` : ''}.`
                : `You haven't set up your persona yet — add your name and a little about you in <a href="#" id="link-persona">Settings → Your persona</a>.`}
            </p>
            <label class="toggle-label"><input type="checkbox" id="up-enabled" ${up.enabled ? 'checked' : ''}><span>Be someone else with ${n}</span></label>
            <div id="up-fields" style="${up.enabled ? '' : 'display:none;'}margin-top:8px;">
              <div class="form-group"><label>Your name here</label><input type="text" class="input" id="up-name" value="${esc(up.name)}" placeholder="e.g. Captain Rhys"></div>
              <div class="form-group"><label>About you here</label><textarea class="input textarea" rows="3" id="up-about" placeholder="Who you are in this story…">${esc(up.about)}</textarea></div>
            </div>
          </div>`;
        }
        if (tab === 'voice') return `
          <div class="form-group">
            <label>Voice <span class="label-hint">— used when text-to-speech is on</span></label>
            <div style="display:flex;gap:6px;align-items:center;">
              <select id="ae-tts-voice" class="input input-sm" style="flex:1;"><option value="">Use global voice</option></select>
              <button id="btn-ae-test-voice" class="btn btn-secondary btn-sm" title="Hear this voice">🔊 Listen</button>
            </div>
          </div>
          ${field('voice_prompt', 'Voice description', 'for Maya TTS — describe the voice naturally', 2, 'Female voice in her 20s, light and whimsical, soft and warm, unhurried')}`;
        // advanced
        const pt = draft.preset_type || 'companion', ab = draft.backend || '';
        return `
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Preset <span class="label-hint">— behaviour profile</span></label>
              <select id="ae-preset-type" class="input input-sm">
                ${App.presetOptions()
                    .map(([v, l]) => `<option value="${v}" ${pt === v ? 'selected' : ''}>${l}</option>`).join('')}
              </select></div>
            <div class="form-group" style="flex:1"><label>Backend <span class="label-hint">— empty = global</span></label>
              <select id="ae-backend" class="input input-sm">
                ${[['', '🌐 Use global default'], ['ollama', '🦙 Ollama'], ['local', '💾 Local GGUF'], ['openai', '🤖 OpenAI'], ['anthropic', '🧠 Anthropic'], ['google', '🔮 Google'], ['openrouter', '🔀 OpenRouter'], ['demonroute', '😈 Demon Route'], ['vllm', '⚡ vLLM'], ['custom', '⚙️ Custom'], ['openai_compat', '🔌 OpenAI compatible']]
                    .map(([v, l]) => `<option value="${v}" ${ab === v ? 'selected' : ''}>${l}</option>`).join('')}
              </select></div>
          </div>
          <div class="form-row">
            <div class="form-group" style="flex:1"><label>Model</label>
              <div style="display:flex;gap:6px;align-items:center;">
                <select id="ae-model" class="input input-sm" style="flex:1;"><option value="">Loading models…</option></select>
                <button id="btn-ae-refresh-models" class="btn btn-secondary btn-sm" title="Refresh model list" style="padding:4px 8px;min-width:auto;">🔄</button>
              </div></div>
            <div class="form-group" style="flex:1"><label>Vision model <span class="label-hint">— Local GGUF only</span></label>
              <select id="ae-vision-model" class="input input-sm"><option value="">Loading…</option></select></div>
          </div>
          ${field('system_prompt', 'Extra instructions', 'added to the end of what the model is told', 4, 'Anything else the model should always follow…')}`;
    }

    // ── Events ───────────────────────────────────────────────────────
    function markDirty() {
        dirty = true;
        const d = document.getElementById('sheet-dirty');
        if (d) d.textContent = '● Unsaved changes';
    }

    function refreshCard() {
        // Re-render keeping the current tab, focus is restored by callers
        renderSheet();
    }

    function bindSheet() {
        const ed = document.getElementById('agent-editor');
        ed.querySelectorAll('.sheet-tab').forEach(b => b.addEventListener('click', () => {
            collectAdvanced();
            currentTab = b.dataset.tab;
            renderSheet();
        }));
        ed.querySelectorAll('[data-key]').forEach(inp => inp.addEventListener('input', () => {
            draft[inp.dataset.key] = inp.value;
            markDirty();
            if (['name', 'tagline'].includes(inp.dataset.key)) {
                const nm = ed.querySelector('.sheet-name');
                if (inp.dataset.key === 'name' && nm) nm.textContent = inp.value || 'Unnamed';
            }
        }));
        // chips
        ed.querySelectorAll('[data-chip-add]').forEach(inp => inp.addEventListener('keydown', e => {
            if ((e.key === 'Enter' || e.key === ',') && inp.value.trim()) {
                e.preventDefault();
                addChip(inp.dataset.chipAdd, inp.value.trim());
            } else if (e.key === 'Backspace' && !inp.value && draft[inp.dataset.chipAdd].length) {
                draft[inp.dataset.chipAdd].pop(); markDirty(); renderSheetFocus(inp.dataset.chipAdd);
            }
        }));
        ed.querySelectorAll('[data-chip-del]').forEach(b => b.addEventListener('click', () => {
            draft[b.dataset.chipDel].splice(+b.dataset.i, 1); markDirty(); renderSheetFocus(b.dataset.chipDel);
        }));
        ed.querySelectorAll('[data-suggest]').forEach(b => b.addEventListener('click', () => addChip(b.dataset.suggest, b.textContent)));
        const surprise = document.getElementById('btn-surprise');
        if (surprise) surprise.addEventListener('click', () => {
            const pool = TRAIT_SUGGESTIONS.filter(t => !draft.traits.includes(t)).sort(() => Math.random() - 0.5);
            draft.traits = draft.traits.concat(pool.slice(0, 3)).slice(-8);
            markDirty(); renderSheet();
        });
        // greetings
        ed.querySelectorAll('[data-alt]').forEach(t => t.addEventListener('input', () => {
            draft.alternate_greetings[+t.dataset.alt] = t.value; markDirty();
        }));
        ed.querySelectorAll('[data-alt-del]').forEach(b => b.addEventListener('click', () => {
            draft.alternate_greetings.splice(+b.dataset.altDel, 1); markDirty(); renderSheet();
        }));
        const addAlt = document.getElementById('btn-alt-add');
        if (addAlt) addAlt.addEventListener('click', () => { draft.alternate_greetings.push(''); markDirty(); renderSheet(); });
        // you
        const upEn = document.getElementById('up-enabled');
        if (upEn) {
            upEn.addEventListener('change', () => {
                draft.user_persona.enabled = upEn.checked; markDirty();
                document.getElementById('up-fields').style.display = upEn.checked ? '' : 'none';
            });
            ['name', 'about'].forEach(k => document.getElementById('up-' + k).addEventListener('input', e => {
                draft.user_persona[k] = e.target.value; markDirty();
            }));
        }
        const lp = document.getElementById('link-persona');
        if (lp) lp.addEventListener('click', e => {
            e.preventDefault(); App.navigate('settings');
            setTimeout(() => document.getElementById('settings-persona')?.scrollIntoView({ behavior: 'smooth' }), 150);
        });
        // picture
        const portrait = document.getElementById('sheet-portrait');
        const fileIn = document.getElementById('sheet-avatar-input');
        portrait.addEventListener('click', () => fileIn.click());
        fileIn.addEventListener('change', () => fileIn.files[0] && uploadAvatar(fileIn.files[0]));
        portrait.addEventListener('dragover', e => { e.preventDefault(); portrait.classList.add('drag'); });
        portrait.addEventListener('dragleave', () => portrait.classList.remove('drag'));
        portrait.addEventListener('drop', e => {
            e.preventDefault(); portrait.classList.remove('drag');
            const f = e.dataTransfer.files[0];
            if (f && f.type.startsWith('image/')) uploadAvatar(f);
        });
        const rm = document.getElementById('sheet-avatar-remove');
        if (rm) rm.addEventListener('click', removeAvatar);
        // voice / advanced
        if (document.getElementById('ae-tts-voice')) {
            loadTTSVoices();
            document.getElementById('ae-tts-voice').addEventListener('change', e => { draft.tts_voice = e.target.value; markDirty(); });
            document.getElementById('btn-ae-test-voice').addEventListener('click', testVoice);
        }
        if (document.getElementById('ae-backend')) {
            document.getElementById('ae-backend').addEventListener('change', () => { markDirty(); loadModelsForAgent(); });
            document.getElementById('btn-ae-refresh-models').addEventListener('click', loadModelsForAgent);
            ['ae-preset-type', 'ae-model', 'ae-vision-model'].forEach(id =>
                document.getElementById(id).addEventListener('change', markDirty));
            loadModelsForAgent();
            loadVisionModelsForAgent();
        }
        // actions
        document.getElementById('btn-agent-save').addEventListener('click', save);
        document.getElementById('btn-agent-delete').addEventListener('click', del);
        document.getElementById('btn-agent-activate').addEventListener('click', () =>
            draft.id === activeId ? deactivate() : activate(draft.id));
        document.getElementById('btn-agent-preview').addEventListener('click', previewPrompt);
    }

    function renderSheetFocus(key) {
        renderSheet();
        const inp = document.querySelector(`[data-chip-add="${key}"]`);
        if (inp) inp.focus();
    }

    function addChip(key, value) {
        value.split(',').map(v => v.trim()).filter(Boolean).forEach(v => {
            if (!draft[key].some(t => t.toLowerCase() === v.toLowerCase())) draft[key].push(v);
        });
        markDirty();
        renderSheetFocus(key);
    }

    function collectAdvanced() {
        const g = id => document.getElementById(id);
        if (g('ae-preset-type')) {
            draft.preset_type = g('ae-preset-type').value;
            draft.backend = g('ae-backend').value;
            if (g('ae-model').value || !draft.model) draft.model = g('ae-model').value.trim();
            draft.vision_model = g('ae-vision-model').value;
        }
        if (g('ae-tts-voice') && g('ae-tts-voice').options.length > 1) draft.tts_voice = g('ae-tts-voice').value;
    }

    function fileToB64(file) {
        return new Promise((res, rej) => {
            const r = new FileReader();
            r.onload = () => res(String(r.result).split(',')[1] || '');
            r.onerror = rej;
            r.readAsDataURL(file);
        });
    }

    async function uploadAvatar(file) {
        try {
            const b64 = await fileToB64(file);
            const c = await App.apiPost(`/characters/${draft.id}/avatar`, { image_b64: b64 });
            if (c.error) throw new Error(c.error);
            const i = agents.findIndex(a => a.id === draft.id);
            if (i >= 0) agents[i].avatar = c.avatar;
            draft.avatar = c.avatar;
            renderList(); renderSheet();
            App.loadAgentDropdown();
            App.toast('Picture updated', 'success');
        } catch (e) {
            App.toast('Could not use that image: ' + (e.message || e), 'error');
        }
    }

    async function removeAvatar() {
        await fetch(`/api/characters/${draft.id}/avatar`, { method: 'DELETE' });
        const i = agents.findIndex(a => a.id === draft.id);
        if (i >= 0) agents[i].avatar = 0;
        draft.avatar = 0;
        renderList(); renderSheet(); App.loadAgentDropdown();
    }

    // ── Prompt preview ───────────────────────────────────────────────
    async function previewPrompt() {
        collectAdvanced();
        try {
            const r = await App.apiPost('/characters/preview-prompt', { character: draft });
            const box = document.createElement('div');
            box.className = 'sheet-preview-overlay';
            box.innerHTML = `<div class="sheet-preview">
                <div class="sheet-preview-head"><strong>What the AI is told about ${esc(draft.name || 'them')}</strong>
                <button class="btn btn-secondary btn-sm">Close</button></div>
                <p class="text-muted" style="font-size:12px;margin:0 0 8px;">Memories, mood and instructions are added after this in every chat.</p>
                <pre>${esc(r.prompt || '')}</pre></div>`;
            box.addEventListener('click', e => { if (e.target === box || e.target.tagName === 'BUTTON') box.remove(); });
            document.body.appendChild(box);
        } catch {
            App.toast('Could not build the preview', 'error');
        }
    }

    // ── Models / voices (advanced + voice tabs) ──────────────────────
    async function loadVisionModelsForAgent() {
        const select = document.getElementById('ae-vision-model');
        if (!select) return;
        select.innerHTML = '<option value="">(none — text only)</option>';
        try {
            let mmprojs = await App.api('/models/mmproj/cache');
            if ((!mmprojs || mmprojs.length === 0) && !App.state.settings?.mmproj_scanned) {
                mmprojs = await App.api('/models/mmproj/scan');
                if (App.state.settings) App.state.settings.mmproj_scanned = true;
            }
            (mmprojs || []).forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.path;
                opt.textContent = m.filename + ' (' + App.formatBytes(m.size) + ')';
                select.appendChild(opt);
            });
            if (draft.vision_model) select.value = draft.vision_model;
        } catch { /* keep the "none" option */ }
    }

    async function loadModelsForAgent() {
        const select = document.getElementById('ae-model');
        const backendSel = document.getElementById('ae-backend');
        if (!select || !backendSel) return;
        const queryBackend = backendSel.value || App.state.backend || 'ollama';
        select.innerHTML = '<option value="">Loading…</option>';
        try {
            const data = await App.api('/models/for-backend/' + encodeURIComponent(queryBackend));
            select.innerHTML = '<option value="">(use global model)</option>';
            (data.models || []).forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name || m.id;
                select.appendChild(opt);
            });
            if (draft.model) {
                if (![...select.options].some(o => o.value === draft.model)) {
                    const opt = document.createElement('option');
                    opt.value = draft.model;
                    opt.textContent = draft.model.split(/[\\/]/).pop() || draft.model;
                    select.appendChild(opt);
                }
                select.value = draft.model;
            }
        } catch {
            select.innerHTML = '<option value="">(use global model)</option>';
        }
    }

    async function loadTTSVoices() {
        const select = document.getElementById('ae-tts-voice');
        if (!select) return;
        try {
            const data = await App.api('/tts/voices');
            select.innerHTML = '<option value="">Use global voice</option>';
            Object.entries(data.voices || {}).forEach(([label, id]) => {
                const opt = document.createElement('option');
                opt.value = id; opt.textContent = label;
                select.appendChild(opt);
            });
            if (draft.tts_voice) select.value = draft.tts_voice;
        } catch {
            select.innerHTML = '<option value="">Voices unavailable</option>';
        }
    }

    let _previewAudio = null;
    async function testVoice() {
        const voiceId = document.getElementById('ae-tts-voice').value;
        if (!voiceId) { App.toast('Pick a voice first', 'info'); return; }
        const btn = document.getElementById('btn-ae-test-voice');
        const orig = btn.textContent;
        btn.textContent = '⏳'; btn.disabled = true;
        try {
            const res = await App.apiPost('/tts/preview', {
                voice: voiceId,
                text: (draft.greeting || '').trim().slice(0, 160)
                    || `Hello! My name is ${draft.name || 'nobody yet'}. This is how I sound.`,
            });
            if (res.audio_b64) {
                if (_previewAudio) _previewAudio.pause();
                _previewAudio = new Audio('data:audio/mp3;base64,' + res.audio_b64);
                _previewAudio.play();
            }
        } catch (e) {
            App.toast('Preview failed: ' + (e.message || e), 'error');
        } finally {
            btn.textContent = orig; btn.disabled = false;
        }
    }

    // ── Save / activate / delete / create / import ───────────────────
    async function save() {
        collectAdvanced();
        const updates = { ...draft };
        delete updates._original;
        updates.name = (updates.name || '').trim();
        updates.alternate_greetings = (updates.alternate_greetings || []).map(g => g.trim()).filter(Boolean);
        if (!updates.name) { App.toast('Give them a name first', 'error'); currentTab = 'basics'; renderSheet(); return; }
        try {
            const saved = await App.apiPut('/characters/' + draft.id, updates);
            const i = agents.findIndex(a => a.id === draft.id);
            if (i >= 0) agents[i] = saved;
            dirty = false;
            openEditor(draft.id, true);
            App.toast('Saved', 'success');
            App.loadAgentDropdown();
        } catch {
            App.toast('Save failed', 'error');
        }
    }

    async function activate(id) {
        if (dirty) await save();
        try {
            await App.apiPost('/characters/' + id + '/activate', {});
            activeId = id;
            App.state.settings = await App.api('/settings');
            const agent = agents.find(a => a.id === id) || {};
            App.toast(`Now chatting with ${agent.name || 'them'}`, 'success');
            renderList(); renderSheet();
            await App.loadAgentDropdown();
            if (agent.model) App.loadModels();
        } catch {
            App.toast('Could not switch character', 'error');
        }
    }

    async function deactivate() {
        try {
            await fetch('/api/characters/activate', { method: 'DELETE' });
            activeId = '';
            App.state.settings = await App.api('/settings');
            App.toast('Back to the default persona', 'info');
            renderList(); renderSheet();
            App.loadAgentDropdown(); App.loadModels();
        } catch {
            App.toast('Could not switch back', 'error');
        }
    }

    async function del() {
        if (!confirm(`Delete "${draft.name || 'this character'}" and all of their memories? This can't be undone.`)) return;
        try {
            await fetch('/api/characters/' + draft.id, { method: 'DELETE' });
            agents = agents.filter(a => a.id !== draft.id);
            if (activeId === draft.id) activeId = '';
            editingId = null; draft = null; dirty = false;
            renderList();
            document.getElementById('agent-editor').innerHTML =
                '<div class="agent-editor-empty"><p>Select a character or create a new one to get started.</p></div>';
            App.toast('Character deleted', 'success');
            App.loadAgentDropdown();
        } catch {
            App.toast('Delete failed', 'error');
        }
    }

    async function createNew() {
        try {
            const agent = await App.apiPost('/characters', { name: 'New Character', preset_type: 'companion' });
            agents.push(agent);
            openEditor(agent.id);
            App.loadAgentDropdown();
        } catch {
            App.toast('Could not create a character', 'error');
        }
    }

    async function importCards(files) {
        let last = null, ok = 0;
        for (const file of files) {
            try {
                const data_b64 = await fileToB64(file);
                const r = await App.apiPost('/characters/import-card', { filename: file.name, data_b64 });
                if (r.error) throw new Error(r.error);
                agents.push(r.character); last = r.character; ok++;
            } catch (e) {
                App.toast(`${file.name}: ${e.message || e}`, 'error');
            }
        }
        if (ok) {
            App.toast(`Imported ${ok} character${ok > 1 ? 's' : ''}`, 'success');
            openEditor(last.id);
            App.loadAgentDropdown();
        }
    }

    // ── Bring a character + chats over from Character.ai ─────────────
    function openCaiImport() {
        const box = document.createElement('div');
        box.className = 'sheet-preview-overlay';
        box.innerHTML = `<div class="sheet-preview cai-import">
          <div class="sheet-preview-head"><strong>🌙 Bring a character over from Character.ai</strong>
            <button class="btn btn-secondary btn-sm" data-close>Close</button></div>
          <ol class="cai-steps">
            <li>Install the free <a href="https://github.com/irsat000/CAI-Tools" target="_blank" rel="noopener">CAI Tools</a> browser extension and open your chat on character.ai.</li>
            <li>From its menu, download the <strong>Character Card (png)</strong> — and your chat as <strong>Tavern chat (.jsonl)</strong> or <strong>Offline chat (.html)</strong> (one per chat, or the whole history).</li>
            <li>Add them below. Your chats appear in Saved Chats, and the moments that mattered become the character's memories.</li>
          </ol>
          <div class="form-group"><label>Character card <span class="label-hint">— optional, .png or .json</span></label>
            <input type="file" id="cai-char" class="input" accept=".png,.json"></div>
          <div class="form-group"><label>Chats <span class="label-hint">— optional, .jsonl / .html / .json / .txt, several at once</span></label>
            <input type="file" id="cai-chats" class="input" accept=".jsonl,.json,.html,.htm,.txt" multiple></div>
          <div class="form-group"><label>Add the chats to</label>
            <select id="cai-target" class="input input-sm">
              <option value="">The character above (or a new one named in the chat)</option>
              ${agents.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('')}
            </select></div>
          <div id="cai-status" class="text-muted" style="font-size:13px;min-height:18px;"></div>
          <div style="display:flex;justify-content:flex-end;"><button class="btn btn-primary" id="cai-go">Import</button></div>
        </div>`;
        box.addEventListener('click', e => { if (e.target === box || e.target.hasAttribute('data-close')) box.remove(); });
        document.body.appendChild(box);
        box.querySelector('#cai-go').addEventListener('click', async () => {
            const status = box.querySelector('#cai-status');
            const cf = box.querySelector('#cai-char').files[0];
            const chats = [...box.querySelector('#cai-chats').files];
            const target = box.querySelector('#cai-target').value;
            if (!cf && !chats.length) { status.textContent = 'Add a character card, a chat, or both.'; return; }
            const go = box.querySelector('#cai-go');
            go.disabled = true; status.textContent = 'Importing… (long histories take a moment)';
            try {
                const body = { chat_files: [] };
                if (cf && !target) body.character_file = { filename: cf.name, data_b64: await fileToB64(cf) };
                if (target) body.character_id = target;
                for (const f of chats) body.chat_files.push({ filename: f.name, data_b64: await fileToB64(f) });
                const r = await App.apiPost('/import/characterai', body);
                if (r.error) throw new Error(r.error);
                const c = r.character;
                const i = agents.findIndex(a => a.id === c.id);
                if (i >= 0) agents[i] = c; else agents.push(c);
                status.innerHTML = `✅ <strong>${esc(c.name)}</strong> is here` +
                    (r.chats ? ` — ${r.chats} chat${r.chats > 1 ? 's' : ''} (${r.messages} messages) in Saved Chats, ${r.memories} memories formed.` : '.') +
                    (r.user_name_in_export ? `<br>Your name in the export was “${esc(r.user_name_in_export)}” — set it in Settings → Your persona if you'd like them to use it.` : '');
                go.textContent = 'Done'; go.disabled = false;
                go.onclick = () => box.remove();
                openEditor(c.id);
                App.loadAgentDropdown();
            } catch (e) {
                let msg = String(e.message || e).replace(/^HTTP \d+: /, '');
                try { msg = JSON.parse(msg).error || msg; } catch { /* plain text */ }
                status.textContent = '❌ ' + msg;
                go.disabled = false;
            }
        });
    }

    // ── Init ─────────────────────────────────────────────────────────
    let _initialized = false;
    function init() {
        if (!_initialized) {
            document.getElementById('btn-new-agent')?.addEventListener('click', createNew);
            const fileIn = document.getElementById('import-card-input');
            document.getElementById('btn-import-st')?.addEventListener('click', () => fileIn && fileIn.click());
            fileIn?.addEventListener('change', () => { importCards([...fileIn.files]); fileIn.value = ''; });
            document.getElementById('btn-import-cai')?.addEventListener('click', openCaiImport);
            window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
            _initialized = true;
        }
        load();
    }

    return { init, load };
})();
