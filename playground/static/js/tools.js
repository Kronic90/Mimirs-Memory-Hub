/* ================================================================
   Tools.js — Agent tool permissions & testing
   ================================================================ */

const ToolsPage = (() => {
    let initialized = false;

    async function loadPermissions() {
        try {
            const perms = await App.api('/tools/permissions');
            document.getElementById('perm-file-access').checked = !!perms.file_access;
            document.getElementById('perm-web-search').checked = !!perms.web_search;
            document.getElementById('perm-code-exec').checked = !!perms.code_execution;
            document.getElementById('perm-allowed-paths').value = (perms.allowed_paths || []).join('\n');
            document.getElementById('perm-allowed-sites').value = (perms.allowed_sites || []).join('\n');
        } catch { /* defaults are fine */ }
    }

    async function savePermissions() {
        const perms = {
            file_access: document.getElementById('perm-file-access').checked,
            web_search: document.getElementById('perm-web-search').checked,
            code_execution: document.getElementById('perm-code-exec').checked,
            allowed_paths: document.getElementById('perm-allowed-paths').value
                .split('\n').map(s => s.trim()).filter(Boolean),
            allowed_sites: document.getElementById('perm-allowed-sites').value
                .split('\n').map(s => s.trim()).filter(Boolean),
        };
        await App.apiPut('/tools/permissions', perms);
        App.toast('Tool permissions saved', 'success');
    }

    async function testTool() {
        const toolName = document.getElementById('tool-test-name').value;
        const paramsStr = document.getElementById('tool-test-params').value.trim();
        const resultEl = document.getElementById('tool-test-result');

        let params = {};
        if (paramsStr) {
            try {
                params = JSON.parse(paramsStr);
            } catch {
                App.toast('Invalid JSON in parameters', 'error');
                return;
            }
        }

        resultEl.style.display = 'block';
        resultEl.textContent = 'Running…';

        try {
            const result = await App.apiPost('/tools/execute', {
                tool: toolName,
                params: params,
            });
            resultEl.textContent = JSON.stringify(result, null, 2);
            resultEl.style.borderLeftColor = result.error ? 'var(--error)' : 'var(--success)';
        } catch (e) {
            resultEl.textContent = 'Error: ' + (e.message || 'Unknown');
            resultEl.style.borderLeftColor = 'var(--error)';
        }
    }

    function init() {
        if (!initialized) {
            document.getElementById('btn-save-tools').addEventListener('click', savePermissions);
            document.getElementById('btn-test-tool').addEventListener('click', testTool);
            initialized = true;
        }
        loadPermissions();
    }

    return { init };
})();
