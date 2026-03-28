/* ================================================================
   App.js — SPA router, state, utilities
   ================================================================ */

const App = (() => {
    // ── State ────────────────────────────────────────────────────
    const state = {
        backend: 'ollama',
        model: '',
        preset: 'companion',
        settings: {},
        ws: null,
        streaming: false,
    };

    // ── Router ───────────────────────────────────────────────────
    function navigate(page) {
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        const el = document.getElementById('page-' + page);
        if (el) el.classList.add('active');
        const nav = document.querySelector(`.nav-item[data-page="${page}"]`);
        if (nav) nav.classList.add('active');
        window.location.hash = page;

        // Trigger page init
        if (page === 'models') ModelsPage.init();
        if (page === 'memory') MemoryPage.init();
        if (page === 'visualize') VisualizePage.init();
        if (page === 'tools') ToolsPage.init();
        if (page === 'import') ImportPage.init();
        if (page === 'settings') SettingsPage.init();
        if (page === 'conversations') ConversationsPage.init();
        if (page === 'multi-chat') MultiChatPage.init();
    }

    // ── Toast ────────────────────────────────────────────────────
    function toast(message, type = 'info') {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 200);
        }, 3500);
    }

    // ── API helpers ──────────────────────────────────────────────
    async function api(path, options = {}) {
        try {
            const resp = await fetch('/api' + path, {
                headers: { 'Content-Type': 'application/json' },
                ...options,
            });
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${text}`);
            }
            return resp.json();
        } catch (e) {
            console.error(`API request failed:`, path, e);
            throw e;
        }
    }

    async function apiPost(path, body) {
        return api(path, { method: 'POST', body: JSON.stringify(body) });
    }

    async function apiPut(path, body) {
        return api(path, { method: 'PUT', body: JSON.stringify(body) });
    }

    // ── WebSocket ────────────────────────────────────────────────
    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
        ws.onopen = () => { state.ws = ws; };
        ws.onclose = () => {
            state.ws = null;
            setTimeout(connectWS, 2000);
        };
        ws.onerror = () => ws.close();
        ws.onmessage = (evt) => {
            const msg = JSON.parse(evt.data);
            Chat.handleMessage(msg);
        };
    }

    function sendWS(msg) {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify(msg));
        } else {
            toast('Not connected to server', 'error');
        }
    }

    // ── Format bytes ─────────────────────────────────────────────
    function formatBytes(bytes) {
        if (!bytes) return '—';
        const gb = bytes / (1024 ** 3);
        if (gb >= 1) return gb.toFixed(1) + ' GB';
        const mb = bytes / (1024 ** 2);
        return mb.toFixed(0) + ' MB';
    }

    // ── Load models for dropdown ─────────────────────────────────
    async function loadModels() {
        const select = document.getElementById('model-select');
        select.innerHTML = '<option value="">Loading…</option>';
        try {
            const data = await api('/models');
            select.innerHTML = '';
            if (data.models && data.models.length > 0) {
                data.models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.id;
                    opt.textContent = m.name || m.id;
                    select.appendChild(opt);
                });
                // Select current model if it's in the list, otherwise pick first
                let found = false;
                if (state.model) {
                    for (const opt of select.options) {
                        if (opt.value === state.model) { found = true; break; }
                    }
                }
                if (!found) {
                    // For local backend, re-add active model if it's a valid path
                    if (data.backend === 'local' && state.model && state.model.includes('\\')) {
                        const name = state.model.split(/[\\/]/).pop() || state.model;
                        const opt = document.createElement('option');
                        opt.value = state.model;
                        opt.textContent = name;
                        select.appendChild(opt);
                        found = true;
                    } else {
                        state.model = data.models[0].id;
                        found = true;
                    }
                }
                select.value = state.model;
                apiPut('/settings', { active_model: state.model });
            } else {
                if (data.backend === 'local') {
                    select.innerHTML = '<option value="">Go to Models → Local tab to scan</option>';
                } else {
                    select.innerHTML = '<option value="">No models found</option>';
                }
            }
        } catch {
            select.innerHTML = '<option value="">Error loading models</option>';
        }
    }

    // ── Load settings ────────────────────────────────────────────
    async function loadSettings() {
        try {
            state.settings = await api('/settings');
            state.backend = state.settings.active_backend || 'ollama';
            state.model = state.settings.active_model || '';
            state.preset = state.settings.active_preset || 'companion';

            document.getElementById('backend-select').value = state.backend;
            document.getElementById('preset-select').value = state.preset;
        } catch {
            console.warn('Could not load settings');
        }
    }

    // ── Init ─────────────────────────────────────────────────────
    async function init() {
        // Nav clicks
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => navigate(item.dataset.page));
        });

        // Header selects
        document.getElementById('backend-select').addEventListener('change', async (e) => {
            state.backend = e.target.value;
            state.model = '';  // Clear model when switching backends
            await apiPut('/settings', { active_backend: state.backend, active_model: '' });
            loadModels();
        });
        document.getElementById('model-select').addEventListener('change', (e) => {
            state.model = e.target.value;
            apiPut('/settings', { active_model: state.model });
        });
        document.getElementById('preset-select').addEventListener('change', (e) => {
            state.preset = e.target.value;
            apiPut('/settings', { active_preset: state.preset });
        });

        // Connect WebSocket
        connectWS();

        // Load settings & models
        await loadSettings();
        await loadModels();

        // Handle hash routing
        const hash = window.location.hash.replace('#', '') || 'chat';
        navigate(hash);

        // Init chat
        Chat.init();
    }

    document.addEventListener('DOMContentLoaded', init);

    return { state, navigate, toast, api, apiPost, apiPut, sendWS, formatBytes, loadModels };
})();
