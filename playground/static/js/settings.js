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

            const params = s.llm_params || {};
            document.getElementById('set-temperature').value = params.temperature ?? 0.7;
            document.getElementById('set-top-p').value = params.top_p ?? 0.9;
            document.getElementById('set-max-tokens').value = params.max_tokens ?? 2048;

            const mem = s.memory || {};
            document.getElementById('set-memory-enabled').checked = mem.enabled !== false;
            document.getElementById('set-auto-remember').checked = mem.auto_remember !== false;
            document.getElementById('set-chemistry').checked = mem.chemistry !== false;

            document.getElementById('set-profile').value = s.active_profile || 'default';
        } catch {
            App.toast('Could not load settings', 'error');
        }
    }

    // ── Save settings ────────────────────────────────────────────
    async function save() {
        const patch = {
            persona_name: document.getElementById('set-persona-name').value,
            persona_description: document.getElementById('set-persona-desc').value,
            system_prompt: document.getElementById('set-system-prompt').value,
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
        };

        await App.apiPut('/settings', patch);
        App.toast('Settings saved', 'success');
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        if (!initialized) {
            document.getElementById('btn-save-settings').addEventListener('click', save);
            initialized = true;
        }
        load();
    }

    return { init };
})();
