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
            document.getElementById('set-system-prompt').value = s.system_prompt || '';
            document.getElementById('set-default-preset').value = s.active_preset || 'companion';

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
            if (micBtn) micBtn.style.display = stt.enabled ? '' : 'none';

            document.getElementById('set-profile').value = s.active_profile || 'default';

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
            persona_name: document.getElementById('set-persona-name').value,
            persona_description: document.getElementById('set-persona-desc').value,
            system_prompt: document.getElementById('set-system-prompt').value,
            active_preset: document.getElementById('set-default-preset').value,
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

        // Show/hide mic button based on STT setting
        const micBtn = document.getElementById('btn-mic');
        if (micBtn) micBtn.style.display = patch.stt.enabled ? '' : 'none';
        App.toast('Settings saved', 'success');
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        if (!initialized) {
            document.getElementById('btn-save-settings').addEventListener('click', save);
            const modeSelect = document.getElementById('set-tts-mode');
            if (modeSelect) modeSelect.addEventListener('change', updateTTSModeUI);
            initialized = true;
        }
        load();
    }

    return { init };
})();
