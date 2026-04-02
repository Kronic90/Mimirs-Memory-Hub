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

            // MCP transport toggle
            const transportSel = document.getElementById('mcp-transport');
            if (transportSel) {
                transportSel.addEventListener('change', () => {
                    document.getElementById('mcp-stdio-fields').style.display = transportSel.value === 'stdio' ? '' : 'none';
                    document.getElementById('mcp-sse-fields').style.display = transportSel.value === 'sse' ? '' : 'none';
                });
            }

            // Add MCP server
            document.getElementById('btn-add-mcp')?.addEventListener('click', addMCPServer);

            initialized = true;
        }
        loadPermissions();
        loadMCPServers();
    }

    // ── MCP Server Management ─────────────────────────────────────

    async function loadMCPServers() {
        const list = document.getElementById('mcp-server-list');
        if (!list) return;
        try {
            const data = await App.api('/mcp/servers');
            const servers = data.servers || [];
            if (!servers.length) {
                list.innerHTML = '<p style="opacity:0.5;font-size:0.9em;">No MCP servers configured. Add one below.</p>';
                return;
            }
            list.innerHTML = servers.map(s => `
                <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg-primary);border:1px solid var(--border);border-radius:8px;">
                    <span style="font-size:1.2em;">${s.connected ? '🟢' : '🔴'}</span>
                    <div style="flex:1;">
                        <strong>${_esc(s.name)}</strong>
                        <span style="opacity:0.6;font-size:0.85em;margin-left:6px;">${s.transport}</span>
                        ${s.connected ? `<span style="opacity:0.6;font-size:0.85em;margin-left:6px;">${s.tool_count} tools</span>` : ''}
                        ${s.tools?.length ? `<div style="margin-top:4px;font-size:0.8em;opacity:0.5;">${s.tools.join(', ')}</div>` : ''}
                    </div>
                    <button class="btn btn-secondary" style="padding:4px 10px;font-size:0.8em;" onclick="ToolsPage._reconnectMCP('${_esc(s.name)}')">↻</button>
                    <button class="btn btn-secondary" style="padding:4px 10px;font-size:0.8em;color:var(--error);" onclick="ToolsPage._removeMCP('${_esc(s.name)}')">✕</button>
                </div>
            `).join('');
        } catch { list.innerHTML = ''; }
    }

    async function addMCPServer() {
        const name = document.getElementById('mcp-server-name')?.value?.trim();
        if (!name) { App.toast('Enter a server name', 'error'); return; }

        const transport = document.getElementById('mcp-transport').value;
        const body = { name, transport, enabled: true };

        if (transport === 'stdio') {
            body.command = document.getElementById('mcp-command')?.value?.trim() || '';
            const argsStr = document.getElementById('mcp-args')?.value?.trim() || '';
            body.args = argsStr ? argsStr.split(',').map(s => s.trim()).filter(Boolean) : [];
            if (!body.command) { App.toast('Enter a command', 'error'); return; }
        } else {
            body.url = document.getElementById('mcp-url')?.value?.trim() || '';
            if (!body.url) { App.toast('Enter a URL', 'error'); return; }
        }

        try {
            await App.apiPost('/mcp/servers', body);
            App.toast(`Added MCP server: ${name}`, 'success');
            document.getElementById('mcp-server-name').value = '';
            document.getElementById('mcp-command').value = '';
            document.getElementById('mcp-args').value = '';
            document.getElementById('mcp-url').value = '';
            loadMCPServers();
        } catch (e) {
            App.toast('Failed: ' + (e.message || 'Unknown error'), 'error');
        }
    }

    async function _reconnectMCP(name) {
        try {
            const r = await App.apiPost(`/mcp/servers/${encodeURIComponent(name)}/reconnect`, {});
            App.toast(r.connected ? `${name}: connected (${r.tools} tools)` : `${name}: connection failed`, r.connected ? 'success' : 'error');
            loadMCPServers();
        } catch (e) {
            App.toast('Reconnect failed: ' + e.message, 'error');
        }
    }

    async function _removeMCP(name) {
        if (!confirm(`Remove MCP server "${name}"?`)) return;
        try {
            await App.api(`/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' });
            App.toast(`Removed ${name}`);
            loadMCPServers();
        } catch (e) {
            App.toast('Remove failed: ' + e.message, 'error');
        }
    }

    function _esc(s) {
        const d = document.createElement('div');
        d.textContent = String(s ?? '');
        return d.innerHTML;
    }

    return { init, _reconnectMCP, _removeMCP };
})();
