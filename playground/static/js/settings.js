/* ================================================================
   Settings.js — Settings page
   ================================================================ */

const SettingsPage = (() => {
    let initialized = false;

    // ── Load settings into form ──────────────────────────────────
    async function load() {
        try {
            const s = await App.api('/settings');

            document.getElementById('set-persona-name').value = s.persona_name || '';
            document.getElementById('set-persona-desc').value = s.persona_description || '';
            const up = s.user_persona || {};
            document.getElementById('set-user-name').value = up.name || '';
            document.getElementById('set-user-about').value = up.about || '';
            document.getElementById('set-system-prompt').value = s.system_prompt || '';
            myPresets = Array.isArray(s.user_presets) ? s.user_presets.map(p => ({ ...p })) : [];
            renderMyPresets();
            fillDefaultPresetSelect(s.active_preset || 'companion');

            const params = s.llm_params || {};
            document.getElementById('set-temperature').value = params.temperature ?? 0.7;
            document.getElementById('set-top-p').value = params.top_p ?? 0.9;
            document.getElementById('set-max-tokens').value = params.max_tokens ?? 2048;

            const mem = s.memory || {};
            document.getElementById('set-memory-enabled').checked = mem.enabled !== false;
            document.getElementById('set-auto-remember').checked = mem.auto_remember !== false;
            document.getElementById('set-chemistry').checked = mem.chemistry !== false;

            // TTS / STT
            const tts = s.tts || {};
            document.getElementById('set-tts-enabled').checked = !!tts.enabled;
            document.getElementById('set-tts-mode').value = tts.mode || 'edge';
            document.getElementById('set-tts-model-path').value = tts.model_path || 'maya-research/maya1';
            document.getElementById('set-tts-server-url').value = tts.server_url || 'http://localhost:8081';

            // Populate voice dropdown
            await populateVoices(tts.voice || 'en-US-JennyNeural');
            updateTTSModeUI();

            const stt = s.stt || {};
            document.getElementById('set-stt-enabled').checked = !!stt.enabled;
            document.getElementById('set-stt-model-size').value = stt.model_size || 'base';
            document.getElementById('set-stt-device').value = stt.device || 'auto';

            // Show/hide mic button
            const micBtn = document.getElementById('btn-mic');
            if (micBtn) micBtn.style.display = '';   // voice notes work without STT

            document.getElementById('set-profile').value = s.active_profile || 'default';

            // Theme
            const theme = s.theme || localStorage.getItem('mimir-theme') || 'dark';
            document.getElementById('set-theme').value = theme;
            applyTheme(theme);

            // Check TTS/STT status
            checkVoiceStatus();
        } catch {
            App.toast('Could not load settings', 'error');
        }
    }

    async function checkVoiceStatus() {
        try {
            const [ttsRes, sttRes] = await Promise.all([
                App.api('/tts/status'),
                App.api('/stt/status'),
            ]);
            const ttsBadge = document.getElementById('tts-status-badge');
            const sttBadge = document.getElementById('stt-status-badge');
            if (ttsBadge) {
                if (!ttsRes.enabled) {
                    ttsBadge.textContent = 'OFF';
                    ttsBadge.style.color = 'var(--text-muted)';
                } else if (ttsRes.ready) {
                    ttsBadge.textContent = '✓ Ready';
                    ttsBadge.style.color = '#10b981';
                } else {
                    ttsBadge.textContent = '⚠ ' + (ttsRes.error || 'Not ready');
                    ttsBadge.style.color = '#f59e0b';
                }
            }
            if (sttBadge) {
                if (!sttRes.enabled) {
                    sttBadge.textContent = 'OFF';
                    sttBadge.style.color = 'var(--text-muted)';
                } else if (sttRes.ready) {
                    sttBadge.textContent = '✓ Ready';
                    sttBadge.style.color = '#10b981';
                } else {
                    sttBadge.textContent = '⚠ ' + (sttRes.error || 'Not ready');
                    sttBadge.style.color = '#f59e0b';
                }
            }
        } catch { /* ignore */ }
    }

    // ── TTS voice helpers ───────────────────────────────────────
    async function populateVoices(selectedVoice) {
        const sel = document.getElementById('set-tts-voice');
        if (!sel) return;
        try {
            const data = await App.api('/tts/voices');
            sel.innerHTML = '';
            for (const [label, voiceId] of Object.entries(data.voices || {})) {
                const opt = document.createElement('option');
                opt.value = voiceId;
                opt.textContent = label;
                if (voiceId === selectedVoice) opt.selected = true;
                sel.appendChild(opt);
            }
        } catch {
            sel.innerHTML = '<option value="en-US-JennyNeural">Jenny (US Female)</option>';
        }
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('mimir-theme', theme);
    }

    function updateTTSModeUI() {
        const mode = document.getElementById('set-tts-mode').value;
        const voiceGrp = document.getElementById('tts-voice-group');
        const modelGrp = document.getElementById('tts-model-group');
        const serverGrp = document.getElementById('tts-server-group');
        if (voiceGrp) voiceGrp.style.display = mode === 'edge' ? '' : 'none';
        if (modelGrp) modelGrp.style.display = mode !== 'edge' ? '' : 'none';
        if (serverGrp) serverGrp.style.display = mode === 'llama_server' ? '' : 'none';
    }

    // ── Save settings ────────────────────────────────────────────
    async function save() {
        const patch = {
            theme: document.getElementById('set-theme').value,
            persona_name: document.getElementById('set-persona-name').value,
            persona_description: document.getElementById('set-persona-desc').value,
            user_persona: {
                name: document.getElementById('set-user-name').value.trim(),
                about: document.getElementById('set-user-about').value.trim(),
            },
            system_prompt: document.getElementById('set-system-prompt').value,
            active_preset: document.getElementById('set-default-preset').value,
            user_presets: myPresets.filter(p => p.id).map(p => ({
                id: p.id, label: (p.label || '').trim() || 'My preset',
                based_on: p.based_on || 'companion', instructions: p.instructions || '' })),
            active_profile: document.getElementById('set-profile').value,
            llm_params: {
                temperature: parseFloat(document.getElementById('set-temperature').value),
                top_p: parseFloat(document.getElementById('set-top-p').value),
                max_tokens: parseInt(document.getElementById('set-max-tokens').value),
            },
            memory: {
                enabled: document.getElementById('set-memory-enabled').checked,
                auto_remember: document.getElementById('set-auto-remember').checked,
                chemistry: document.getElementById('set-chemistry').checked,
            },
            tts: {
                enabled: document.getElementById('set-tts-enabled').checked,
                mode: document.getElementById('set-tts-mode').value,
                voice: document.getElementById('set-tts-voice').value,
                model_path: document.getElementById('set-tts-model-path').value,
                server_url: document.getElementById('set-tts-server-url').value,
            },
            stt: {
                enabled: document.getElementById('set-stt-enabled').checked,
                model_size: document.getElementById('set-stt-model-size').value,
                device: document.getElementById('set-stt-device').value,
            },
        };

        await App.apiPut('/settings', patch);
        App.state.settings = { ...(App.state.settings || {}), ...patch };
        App.state.preset = patch.active_preset;
        fillDefaultPresetSelect(patch.active_preset);
        if (typeof Chat !== 'undefined' && Chat.refreshAvatars) Chat.refreshAvatars();

        // Show/hide mic button based on STT setting
        const micBtn = document.getElementById('btn-mic');
        if (micBtn) micBtn.style.display = '';   // voice notes work without STT
        App.toast('Settings saved', 'success');
    }

    // ── Init ─────────────────────────────────────────────────────
    // ── Updates ──────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    function escHtml(t) {
        return String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function setStatus(id, html, cls) {
        const el = $(id);
        el.className = cls || 'text-muted';
        el.style.fontSize = '13px';
        el.innerHTML = html;
    }
    const updStatus = (html, cls) => setStatus('upd-status', html, cls);
    const impStatus = (html, cls) => setStatus('imp-status', html, cls);

    async function loadVersion() {
        try {
            const v = await App.api('/version');
            $('upd-current').textContent = 'v' + v.version;
            const sv = $('sidebar-version');
            if (sv) sv.textContent = 'v' + v.version;
        } catch { /* fine offline */ }
    }

    async function checkUpdates() {
        const btn = $('btn-upd-check');
        btn.disabled = true;
        $('btn-upd-apply').style.display = 'none';
        updStatus('Checking GitHub…');
        try {
            const r = await App.api('/update/check');
            $('upd-current').textContent = 'v' + r.current;
            if (r.notes) {
                $('upd-notes').innerHTML = (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined')
                    ? DOMPurify.sanitize(marked.parse(r.notes)) : escHtml(r.notes);
                $('upd-notes-wrap').style.display = '';
            }
            if (r.kind === 'git') {
                const g = r.git || {};
                if (g.error) {
                    updStatus(escHtml(g.error), 'upd-err');
                } else if (r.update_available) {
                    updStatus(`${g.behind} new change${g.behind === 1 ? '' : 's'} on <code>${escHtml(g.upstream)}</code>`
                        + (r.latest ? ` (latest release v${escHtml(r.latest)})` : '')
                        + (g.dirty ? '<br><span class="upd-err">You have local code changes — commit or stash them first.</span>' : ''));
                    $('btn-upd-apply').style.display = '';
                } else {
                    updStatus(`You're up to date with <code>${escHtml(g.upstream || 'the remote')}</code>.`, 'upd-ok');
                }
            } else if (r.release_error) {
                updStatus(escHtml(r.release_error), 'upd-err');
            } else if (r.update_available) {
                updStatus(`<strong>v${escHtml(r.latest)}</strong> is available`
                    + (r.url ? ` — <a href="${escHtml(r.url)}" target="_blank" rel="noopener">release page</a>` : '')
                    + `. Updating replaces the hub's code only — your data stays put and the old code is backed up.`);
                $('btn-upd-apply').style.display = '';
            } else {
                updStatus(`You're on the latest version (v${escHtml(r.current)}).`, 'upd-ok');
            }
        } catch (e) {
            updStatus(`Couldn't check for updates: ${escHtml(e.message)}`, 'upd-err');
        } finally {
            btn.disabled = false;
        }
    }

    async function applyUpdate() {
        const btn = $('btn-upd-apply');
        btn.disabled = true;
        updStatus('Updating… downloading and installing anything new, this can take a minute.');
        try {
            const r = await App.api('/update/apply', { method: 'POST', body: '{}' });
            if (!r.ok) { updStatus(escHtml(r.error), 'upd-err'); return; }
            let msg = r.version ? `Updated to v${escHtml(r.version)}.` : `Updated (${escHtml(r.from)} → ${escHtml(r.to)}).`;
            if (r.pip && !r.pip.ok) {
                msg += `<br><span class="upd-err">Installing new requirements had a problem:</span> <code>${escHtml(r.pip.output)}</code>`;
            }
            msg += ' Restart the hub to start using it.';
            updStatus(msg, 'upd-ok');
            btn.style.display = 'none';
            $('btn-upd-restart').style.display = '';
        } catch (e) {
            updStatus(`Update failed: ${escHtml(e.message)}`, 'upd-err');
        } finally {
            btn.disabled = false;
        }
    }

    async function restartHub(statusFn) {
        const say = statusFn || updStatus;
        say('Restarting… this page will reload by itself.');
        try { await App.api('/update/restart', { method: 'POST', body: '{}' }); } catch { /* expected */ }
        // Give the old server time to exit, then wait for the new one
        await new Promise(r => setTimeout(r, 3000));
        for (let i = 0; i < 120; i++) {
            try {
                const resp = await fetch('/api/version', { cache: 'no-store' });
                if (resp.ok) { location.reload(); return; }
            } catch { /* not up yet */ }
            await new Promise(r => setTimeout(r, 1000));
        }
        say(`The hub didn't come back by itself — please start it again (run.bat).`, 'upd-err');
    }

    // ── Bring data from another copy ─────────────────────────────
    async function previewImport() {
        $('imp-confirm').style.display = 'none';
        const path = $('imp-path').value.trim();
        if (!path) { impStatus('Paste the folder of the older copy first.', 'upd-err'); return; }
        try {
            const r = await App.apiPost('/data/import-preview', { path });
            if (!r.ok) { impStatus(escHtml(r.error), 'upd-err'); return; }
            let html = `Found <strong>${r.memories}</strong> memories, <strong>${r.characters}</strong> characters and `
                + `<strong>${r.conversations}</strong> conversations in <code>${escHtml(r.source)}</code>`
                + (r.newest ? ` (newest from ${fmtWhen(r.newest)}).` : '.');
            const cur = r.current;
            if (cur && (cur.memories > 0 || cur.conversations > 0)) {
                const newer = cur.newest && r.newest && cur.newest > r.newest;
                html += `<br>This copy has <strong>${cur.memories}</strong> memories and <strong>${cur.conversations}</strong> conversations`
                    + (cur.newest ? ` (newest from ${fmtWhen(cur.newest)})` : '') + '.';
                if (newer || cur.memories > r.memories) {
                    html += `<div class="upd-err" style="margin-top:6px;">⚠️ This copy has <strong>newer</strong> data than the one you're importing. `
                        + `Importing replaces it with the older data (it's kept in a backup, but you'd lose it from view). `
                        + `If this copy already has your characters and memories, you don't need to import.</div>`;
                }
            }
            if (r.model_refs > 0) {
                html += `<div class="text-muted" style="margin-top:6px;">ℹ️ Its settings use model files stored inside that old folder. `
                    + `They keep working while the old folder exists — tick “Also copy its downloaded models” if you plan to delete it.</div>`;
            }
            impStatus(html);
            $('imp-models-label').textContent = `Also copy its downloaded models (${r.models_gb} GB)`;
            $('imp-models-wrap').style.display = r.models_gb > 0 ? '' : 'none';
            $('imp-models').checked = false;
            $('imp-confirm').style.display = '';
        } catch (e) {
            impStatus(`Couldn't read that folder: ${escHtml(e.message)}`, 'upd-err');
        }
    }

    async function doImport() {
        const path = $('imp-path').value.trim();
        if (!confirm("Replace this copy's data with the older copy's? This copy's current data is backed up to _update_backups first.")) return;
        $('btn-imp-go').disabled = true;
        impStatus('Copying…');
        try {
            const r = await App.apiPost('/data/import-stage', { path, include_models: $('imp-models').checked });
            if (!r.ok) {
                impStatus(escHtml(r.error), 'upd-err');
                $('btn-imp-go').disabled = false;
                return;
            }
            await restartHub(impStatus);
        } catch (e) {
            impStatus(`Import failed: ${escHtml(e.message)}`, 'upd-err');
            $('btn-imp-go').disabled = false;
        }
    }

    // ── My presets ───────────────────────────────────────────────
    let myPresets = [];
    function fillDefaultPresetSelect(value) {
        const sel = document.getElementById('set-default-preset');
        if (!sel) return;
        const opts = App.BUILTIN_PRESETS.map(([v, l]) => [v, l.replace(/^\S+\s/, '')])
            .concat(myPresets.filter(p => p.id).map(p => [p.id, '⭐ ' + ((p.label || '').trim() || 'My preset')]));
        sel.innerHTML = opts.map(([v, l]) => `<option value="${escHtml(v)}">${escHtml(l)}</option>`).join('');
        sel.value = opts.some(o => o[0] === value) ? value : 'companion';
    }
    function renderMyPresets() {
        const box = $('my-presets');
        if (!box) return;
        if (!myPresets.length) {
            box.innerHTML = '<div class="text-muted" style="font-size:13px;margin-bottom:8px;">No presets of your own yet.</div>';
            return;
        }
        const bases = App.BUILTIN_PRESETS;
        box.innerHTML = myPresets.map((p, i) => `
            <div class="my-preset" data-i="${i}">
                <div class="form-row" style="gap:8px;align-items:center;">
                    <input class="input input-sm" data-f="label" placeholder="Name, e.g. Cosy bedtime chats" value="${escHtml(p.label || '')}" style="flex:1;">
                    <select class="input input-sm" data-f="based_on" title="Built on">
                        ${bases.map(([v, l]) => `<option value="${v}" ${(p.based_on || 'companion') === v ? 'selected' : ''}>based on ${escHtml(l)}</option>`).join('')}
                    </select>
                    <button class="btn btn-secondary btn-sm" data-del="${i}" type="button" title="Delete this preset">🗑</button>
                </div>
                <textarea class="input textarea" data-f="instructions" rows="3" placeholder="Your instructions: how replies should feel, length, style, things to always or never do…">${escHtml(p.instructions || '')}</textarea>
            </div>`).join('');
        box.querySelectorAll('.my-preset').forEach(card => {
            const p = myPresets[+card.dataset.i];
            card.querySelectorAll('[data-f]').forEach(el => el.addEventListener('input', () => {
                p[el.dataset.f] = el.value;
                if (el.dataset.f === 'label') fillDefaultPresetSelect($('set-default-preset').value);
            }));
        });
        box.querySelectorAll('[data-del]').forEach(btn => btn.addEventListener('click', () => {
            myPresets.splice(+btn.dataset.del, 1);
            renderMyPresets();
            fillDefaultPresetSelect($('set-default-preset').value);
        }));
    }
    function addPreset() {
        myPresets.push({ id: 'my-' + Date.now().toString(36), label: '', based_on: 'companion', instructions: '' });
        renderMyPresets();
        fillDefaultPresetSelect($('set-default-preset').value);
        const labels = document.querySelectorAll('#my-presets input[data-f="label"]');
        labels[labels.length - 1]?.focus();
    }

    // ── Setup file (export / import) ─────────────────────────────
    const setupStatus = (html, cls) => setStatus('setup-file-status', html, cls);
    let setupFilePath = '';
    function exportSetup() {
        const keys = $('export-keys').checked ? 1 : 0;
        setupStatus('Preparing your file… the download starts in a moment.');
        const a = document.createElement('a');
        a.href = `/api/data/export?keys=${keys}`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => setupStatus(keys
            ? 'Saved. ⚠️ This file contains your API keys, so keep it private.'
            : 'Saved (without API keys). Loading it keeps whatever keys that copy already has.', 'upd-ok'), 2500);
    }
    async function importSetupFile(file) {
        $('setup-file-confirm').style.display = 'none';
        if (!file) return;
        setupStatus('Reading the file…');
        try {
            const resp = await fetch('/api/data/import-file', { method: 'POST', body: file });
            const r = await resp.json();
            if (!r.ok) { setupStatus(escHtml(r.error || 'Could not read that file.'), 'upd-err'); return; }
            setupFilePath = r.source;
            let html = `This file has <strong>${r.memories}</strong> memories, <strong>${r.characters}</strong> characters and `
                + `<strong>${r.conversations}</strong> chats` + (r.newest ? ` (newest from ${fmtWhen(r.newest)})` : '')
                + (r.file_version ? `, saved from v${escHtml(r.file_version)}` : '') + '.';
            const cur = r.current;
            if (cur && (cur.memories > 0 || cur.conversations > 0)) {
                html += `<br>This copy has <strong>${cur.memories}</strong> memories and <strong>${cur.conversations}</strong> chats`
                    + (cur.newest ? ` (newest from ${fmtWhen(cur.newest)})` : '') + `. Loading replaces them (they're kept as a backup).`;
                if ((cur.newest && r.newest && cur.newest > r.newest) || cur.memories > r.memories) {
                    html += `<div class="upd-err" style="margin-top:6px;">⚠️ This copy has <strong>newer</strong> data than the file.</div>`;
                }
            }
            setupStatus(html);
            $('setup-file-confirm').style.display = '';
        } catch (e) {
            setupStatus(`Could not read that file: ${escHtml(e.message)}`, 'upd-err');
        }
    }
    async function applySetupFile() {
        if (!setupFilePath) return;
        if (!confirm("Load this setup file? This copy's current data is backed up first, then the hub restarts.")) return;
        $('btn-setup-file-go').disabled = true;
        try {
            const r = await App.apiPost('/data/import-stage', { path: setupFilePath, include_models: false });
            if (!r.ok) { setupStatus(escHtml(r.error), 'upd-err'); $('btn-setup-file-go').disabled = false; return; }
            await restartHub(setupStatus);
        } catch (e) {
            setupStatus(`Loading failed: ${escHtml(e.message)}`, 'upd-err');
            $('btn-setup-file-go').disabled = false;
        }
    }

    function fmtWhen(ts) {
        const d = new Date(ts);
        return isNaN(d) ? escHtml(ts) : d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    }

    async function loadBackups() {
        const box = $('backup-list');
        if (!box) return;
        try {
            const r = await App.api('/data/backups');
            const list = r.backups || [];
            if (!list.length) { box.innerHTML = '<span class="text-muted" style="font-size:13px;">No backups yet.</span>'; return; }
            box.innerHTML = list.map((b, i) => `
                <div class="backup-row">
                    <div><strong>${b.newest ? fmtWhen(b.newest) : escHtml(b.saved)}</strong>
                        <span class="text-muted"> — ${b.memories} memories, ${b.characters} characters, ${b.conversations} chats</span></div>
                    <button class="btn btn-secondary btn-sm" data-i="${i}">Restore</button>
                </div>`).join('');
            box.querySelectorAll('button[data-i]').forEach(btn => btn.addEventListener('click', async () => {
                const b = list[+btn.dataset.i];
                if (!confirm(`Restore the backup with ${b.memories} memories and ${b.characters} characters? `
                    + `What this copy has now is backed up first. The hub restarts.`)) return;
                btn.disabled = true;
                try {
                    const s = await App.apiPost('/data/import-stage', { path: b.path, include_models: false });
                    if (!s.ok) { App.toast(s.error || 'Restore failed', 'error'); btn.disabled = false; return; }
                    await restartHub(impStatus);
                } catch (e) { App.toast('Restore failed: ' + e.message, 'error'); btn.disabled = false; }
            }));
        } catch {
            box.innerHTML = `<span class="text-muted" style="font-size:13px;">Couldn't list backups.</span>`;
        }
    }

    function init() {
        loadBackups();
        if (!initialized) {
            $('btn-upd-check').addEventListener('click', checkUpdates);
            $('btn-upd-apply').addEventListener('click', applyUpdate);
            $('btn-upd-restart').addEventListener('click', () => restartHub());
            $('btn-imp-preview').addEventListener('click', previewImport);
            $('btn-imp-go').addEventListener('click', doImport);
            $('btn-add-preset').addEventListener('click', addPreset);
            $('btn-export-setup').addEventListener('click', exportSetup);
            $('btn-import-setup').addEventListener('click', () => $('import-setup-file').click());
            $('import-setup-file').addEventListener('change', (e) => { importSetupFile(e.target.files[0]); e.target.value = ''; });
            $('btn-setup-file-go').addEventListener('click', applySetupFile);
            document.getElementById('btn-save-settings').addEventListener('click', save);
            const modeSelect = document.getElementById('set-tts-mode');
            if (modeSelect) modeSelect.addEventListener('change', updateTTSModeUI);
            const themeSelect = document.getElementById('set-theme');
            if (themeSelect) themeSelect.addEventListener('change', () => applyTheme(themeSelect.value));
            initialized = true;
        }
        load();
        loadVersion();
    }

    return { init, checkUpdates, loadVersion };
})();
