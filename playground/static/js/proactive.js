/**
 * Proactive Agent page — project management, task board, live activity log.
 */
const ProactivePage = (() => {
    let _initialized = false;
    let _ws = null;
    let _projects = [];
    let _selectedProjectId = null;
    let _tasks = [];
    let _editingProjectId = null;  // null = new, string = editing
    let _editingTaskId = null;

    const ALL_TOOLS = [
        'read_file', 'write_file', 'list_directory', 'search_files', 'grep_files',
        'web_search', 'fetch_page', 'http_request', 'shell_exec', 'run_code',
        'datetime', 'json_parse', 'diff_files', 'regex_replace', 'pdf_read',
        'csv_query', 'screenshot', 'clipboard', 'open_app', 'system_info', 'weather',
    ];

    const TOOL_LABELS = {
        read_file: '📄 Read File', write_file: '✏️ Write File',
        list_directory: '📁 List Dir', search_files: '🔍 Search Files',
        grep_files: '🔎 Grep', web_search: '🌐 Web Search',
        fetch_page: '🌍 Fetch Page', http_request: '📡 HTTP Request',
        shell_exec: '💻 Shell', run_code: '▶️ Run Code',
        datetime: '🕐 DateTime', json_parse: '📋 JSON Parse',
        diff_files: '📊 Diff', regex_replace: '🔧 Regex Replace',
        pdf_read: '📑 PDF Read', csv_query: '📈 CSV Query',
        screenshot: '📸 Screenshot', clipboard: '📎 Clipboard',
        open_app: '🚀 Open App', system_info: '💾 System Info',
        weather: '🌤️ Weather',
    };

    const STATUS_ICONS = {
        proposed: '💡', approved: '✅', in_progress: '⚡',
        paused: '⏸️', review: '👀', completed: '✔️',
        failed: '❌', cancelled: '🚫',
    };

    const PRIORITY_COLORS = {
        low: 'var(--text-muted)', medium: 'var(--text-secondary)',
        high: 'var(--warning)', urgent: 'var(--error)',
    };

    // ── WebSocket ──────────────────────────────────────────────

    function connectWS() {
        if (_ws && _ws.readyState <= 1) return;
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        _ws = new WebSocket(`${proto}://${location.host}/ws/agent`);
        _ws.onopen = () => console.log('[ProactiveAgent] WS connected');
        _ws.onclose = () => setTimeout(connectWS, 3000);
        _ws.onmessage = (evt) => {
            const msg = JSON.parse(evt.data);
            handleWSMessage(msg);
        };
    }

    function sendWS(data) {
        if (_ws && _ws.readyState === 1) {
            _ws.send(JSON.stringify(data));
        }
    }

    function handleWSMessage(msg) {
        switch (msg.type) {
            case 'agent_status_update':
                updateStatusUI(msg);
                break;
            case 'agent_status':
                updateAgentActivity(msg);
                break;
            case 'agent_log':
                appendLogEntry(msg);
                break;
            case 'agent_task_complete':
                App.toast(`Task complete: ${msg.summary?.substring(0, 80)}`, 'success');
                if (_selectedProjectId === msg.project_id) loadTasks(msg.project_id);
                break;
            case 'agent_approval_needed':
                App.toast(`Agent needs approval — ${msg.reason}`, 'warning');
                appendLogEntry({ action: 'approval_needed', detail: msg.reason, timestamp: Date.now() / 1000 });
                break;
            case 'agent_error':
                App.toast(`Agent error: ${msg.error}`, 'error');
                break;
        }
    }

    // ── Status UI ──────────────────────────────────────────────

    function updateStatusUI(status) {
        const badge = document.getElementById('agent-status-badge');
        const select = document.getElementById('agent-mode-select');
        const btn = document.getElementById('btn-agent-toggle');

        select.value = status.mode || 'off';

        if (status.mode === 'off') {
            badge.textContent = '⏸ Off';
            badge.style.color = 'var(--text-muted)';
            btn.textContent = 'Start';
            btn.className = 'btn btn-primary';
        } else if (status.paused) {
            badge.textContent = '⏸ Paused';
            badge.style.color = 'var(--warning)';
            btn.textContent = 'Resume';
            btn.className = 'btn btn-primary';
        } else {
            const modeLabel = status.mode === 'observer' ? '👁️ Observing' : '⚡ Working';
            badge.textContent = modeLabel;
            badge.style.color = 'var(--success)';
            btn.textContent = 'Stop';
            btn.className = 'btn btn-secondary';
        }

        // Update sidebar indicator
        updateSidebarIndicator(status);
    }

    function updateSidebarIndicator(status) {
        let indicator = document.getElementById('proactive-nav-indicator');
        const navItem = document.querySelector('[data-page="proactive"]');
        if (!navItem) return;

        if (!indicator) {
            indicator = document.createElement('span');
            indicator.id = 'proactive-nav-indicator';
            indicator.style.cssText = 'width:6px;height:6px;border-radius:50%;margin-left:auto;';
            navItem.style.display = 'flex';
            navItem.style.alignItems = 'center';
            navItem.appendChild(indicator);
        }

        if (status.mode === 'off') {
            indicator.style.background = 'transparent';
        } else if (status.paused) {
            indicator.style.background = 'var(--warning)';
        } else {
            indicator.style.background = 'var(--success)';
        }
    }

    function updateAgentActivity(msg) {
        const el = document.getElementById('agent-activity-status');
        if (msg.status === 'working') {
            el.textContent = `Working: ${msg.task_title}`;
            el.style.color = 'var(--success)';
        } else {
            el.textContent = 'Idle';
            el.style.color = '';
        }
    }

    function appendLogEntry(msg) {
        const log = document.getElementById('agent-log');
        // Clear placeholder
        if (log.querySelector('.text-muted')) log.innerHTML = '';

        const entry = document.createElement('div');
        entry.className = 'agent-log-entry';
        const time = new Date((msg.timestamp || Date.now() / 1000) * 1000);
        const timeStr = time.toLocaleTimeString();
        const icon = msg.action === 'tool_call' ? '🔧'
            : msg.action === 'thinking' ? '🧠'
            : msg.action === 'completed' || msg.action === 'observation_complete' ? '✅'
            : msg.action === 'failed' ? '❌'
            : msg.action === 'approval_needed' ? '⚠️'
            : msg.action === 'paused' ? '⏸️' : '📋';

        entry.innerHTML = `
            <span class="log-time">${timeStr}</span>
            <span class="log-icon">${icon}</span>
            <span class="log-detail">${esc(msg.detail || msg.action)}</span>
        `;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight;

        // Keep log manageable
        while (log.children.length > 200) log.removeChild(log.firstChild);
    }

    // ── Projects ───────────────────────────────────────────────

    async function loadProjects() {
        try {
            _projects = await App.api('/agent/projects');
        } catch { _projects = []; }
        renderProjectList();
    }

    function renderProjectList() {
        const el = document.getElementById('project-list');
        if (!_projects.length) {
            el.innerHTML = '<p class="text-muted" style="padding:12px;font-size:0.85rem;">No projects yet. Create one to get started.</p>';
            return;
        }
        el.innerHTML = '';
        _projects.forEach(p => {
            const card = document.createElement('div');
            card.className = 'project-card' + (p.id === _selectedProjectId ? ' selected' : '');
            const budgetPct = p.daily_token_budget > 0
                ? Math.round((p.tokens_used_today || 0) / p.daily_token_budget * 100)
                : 0;
            card.innerHTML = `
                <div class="project-card-name">${esc(p.name)}</div>
                <div class="project-card-meta text-muted">${esc(p.folder)}</div>
                <div class="project-card-budget">
                    <div class="budget-bar"><div class="budget-fill" style="width:${budgetPct}%"></div></div>
                    <span class="text-muted" style="font-size:0.72rem;">${budgetPct}% budget</span>
                </div>
            `;
            card.addEventListener('click', () => selectProject(p.id));
            card.addEventListener('dblclick', () => editProject(p.id));
            el.appendChild(card);
        });
    }

    function selectProject(projectId) {
        _selectedProjectId = projectId;
        renderProjectList();
        document.getElementById('tasks-section').style.display = '';
        const proj = _projects.find(p => p.id === projectId);
        document.getElementById('task-project-name').textContent = proj ? `— ${proj.name}` : '';
        hideEditors();
        loadTasks(projectId);
        loadLogs(projectId);
    }

    function showProjectEditor(project) {
        hideEditors();
        const editor = document.getElementById('project-editor');
        editor.style.display = '';
        document.getElementById('project-editor-title').textContent = project ? 'Edit Project' : 'New Project';
        document.getElementById('project-name').value = project ? project.name : '';
        document.getElementById('project-folder').value = project ? project.folder : '';
        document.getElementById('project-desc').value = project ? project.description : '';
        document.getElementById('project-budget').value = project ? project.daily_token_budget : 50000;
        document.getElementById('btn-delete-project').style.display = project ? '' : 'none';
        _editingProjectId = project ? project.id : null;

        // Render tools grid
        const toolsEl = document.getElementById('project-tools');
        const enabledTools = project ? project.tools_enabled : {};
        toolsEl.innerHTML = '';
        ALL_TOOLS.forEach(tool => {
            const checked = project ? (enabledTools[tool] !== false) : true;
            const label = document.createElement('label');
            label.className = 'tool-toggle';
            label.innerHTML = `
                <input type="checkbox" data-tool="${tool}" ${checked ? 'checked' : ''}>
                <span>${TOOL_LABELS[tool] || tool}</span>
            `;
            toolsEl.appendChild(label);
        });
    }

    function editProject(projectId) {
        const proj = _projects.find(p => p.id === projectId);
        if (proj) showProjectEditor(proj);
    }

    async function saveProject() {
        const name = document.getElementById('project-name').value.trim();
        const folder = document.getElementById('project-folder').value.trim();
        const desc = document.getElementById('project-desc').value.trim();
        const budget = parseInt(document.getElementById('project-budget').value) || 50000;

        if (!name) return App.toast('Project name is required', 'error');
        if (!folder) return App.toast('Working folder is required', 'error');

        // Gather tool states
        const toolsEnabled = {};
        document.querySelectorAll('#project-tools input[type=checkbox]').forEach(cb => {
            toolsEnabled[cb.dataset.tool] = cb.checked;
        });

        try {
            if (_editingProjectId) {
                await App.apiPut(`/agent/projects/${_editingProjectId}`, {
                    name, folder, description: desc, daily_token_budget: budget, tools_enabled: toolsEnabled,
                });
                App.toast('Project updated', 'success');
            } else {
                const result = await App.apiPost('/agent/projects', {
                    name, folder, description: desc, daily_token_budget: budget, tools_enabled: toolsEnabled,
                });
                if (result.error) return App.toast(result.error, 'error');
                _selectedProjectId = result.id;
                App.toast('Project created', 'success');
            }
        } catch (e) {
            // Extract server error message from "HTTP 400: {json}" format
            let msg = 'Failed to save project';
            try {
                const match = e.message?.match(/HTTP \d+: (.*)/);
                if (match) {
                    const body = JSON.parse(match[1]);
                    if (body.error) msg = body.error;
                }
            } catch {}
            return App.toast(msg, 'error');
        }

        hideEditors();
        await loadProjects();
        if (_selectedProjectId) selectProject(_selectedProjectId);
    }

    async function deleteCurrentProject() {
        if (!_editingProjectId) return;
        if (!confirm('Delete this project and all its tasks?')) return;
        await fetch(`/api/agent/projects/${_editingProjectId}`, { method: 'DELETE' });
        _selectedProjectId = null;
        _editingProjectId = null;
        hideEditors();
        document.getElementById('tasks-section').style.display = 'none';
        App.toast('Project deleted', 'success');
        loadProjects();
    }

    // ── Tasks ──────────────────────────────────────────────────

    async function loadTasks(projectId) {
        try {
            _tasks = await App.api(`/agent/projects/${projectId}/tasks`);
        } catch { _tasks = []; }
        renderTaskList();
    }

    function renderTaskList() {
        const el = document.getElementById('task-list');
        if (!_tasks.length) {
            el.innerHTML = '<p class="text-muted" style="padding:12px;font-size:0.85rem;">No tasks. Add one to get started.</p>';
            return;
        }

        // Sort: in_progress first, then by priority
        const priorityOrder = { urgent: 0, high: 1, medium: 2, low: 3 };
        const statusOrder = { in_progress: 0, approved: 1, proposed: 2, paused: 3, review: 4, completed: 5, failed: 6, cancelled: 7 };
        const sorted = [..._tasks].sort((a, b) =>
            (statusOrder[a.status] || 9) - (statusOrder[b.status] || 9)
            || (priorityOrder[a.priority] || 9) - (priorityOrder[b.priority] || 9)
        );

        el.innerHTML = '';
        sorted.forEach(t => {
            const card = document.createElement('div');
            card.className = 'task-card';
            if (t.status === 'completed') card.style.opacity = '0.6';
            const icon = STATUS_ICONS[t.status] || '📋';
            const budgetPct = t.token_budget > 0 ? Math.round((t.tokens_used || 0) / t.token_budget * 100) : 0;

            let actions = '';
            if (t.status === 'proposed') {
                actions = `<button class="btn btn-sm btn-primary" onclick="ProactivePage.approveTask('${t.id}')">Approve</button>`;
            }
            if (['proposed', 'approved', 'paused', 'review'].includes(t.status)) {
                actions += ` <button class="btn btn-sm btn-secondary" onclick="ProactivePage.removeTask('${t.id}')">✕</button>`;
            }

            card.innerHTML = `
                <div class="task-card-header">
                    <span class="task-icon">${icon}</span>
                    <span class="task-title">${esc(t.title)}</span>
                    <span class="task-priority" style="color:${PRIORITY_COLORS[t.priority] || ''}">${t.priority}</span>
                </div>
                ${t.description ? `<div class="task-desc text-muted">${esc(t.description).substring(0, 120)}</div>` : ''}
                ${t.result ? `<div class="task-result">${esc(t.result).substring(0, 200)}</div>` : ''}
                <div class="task-card-footer">
                    <span class="text-muted" style="font-size:0.72rem;">${t.status} · ${budgetPct}% tokens</span>
                    <div class="task-actions">${actions}</div>
                </div>
            `;
            el.appendChild(card);
        });
    }

    function showTaskEditor(task) {
        hideEditors();
        const editor = document.getElementById('task-editor');
        editor.style.display = '';
        document.getElementById('task-editor-title').textContent = task ? 'Edit Task' : 'New Task';
        document.getElementById('task-title').value = task ? task.title : '';
        document.getElementById('task-desc').value = task ? task.description : '';
        document.getElementById('task-priority').value = task ? task.priority : 'medium';
        document.getElementById('task-budget').value = task ? task.token_budget : 4096;
        _editingTaskId = task ? task.id : null;
    }

    async function saveTask() {
        if (!_selectedProjectId) return;
        const title = document.getElementById('task-title').value.trim();
        const desc = document.getElementById('task-desc').value.trim();
        const priority = document.getElementById('task-priority').value;
        const budget = parseInt(document.getElementById('task-budget').value) || 4096;

        if (!title) return App.toast('Task title is required', 'error');

        try {
            if (_editingTaskId) {
                await App.apiPut(`/agent/projects/${_selectedProjectId}/tasks/${_editingTaskId}`, {
                    title, description: desc, priority, token_budget: budget,
                });
            } else {
                await App.apiPost(`/agent/projects/${_selectedProjectId}/tasks`, {
                    title, description: desc, priority, token_budget: budget,
                });
            }
            App.toast('Task saved', 'success');
        } catch {
            return App.toast('Failed to save task', 'error');
        }

        hideEditors();
        loadTasks(_selectedProjectId);
    }

    async function approveTask(taskId) {
        if (!_selectedProjectId) return;
        await fetch(`/api/agent/projects/${_selectedProjectId}/tasks/${taskId}/approve`, { method: 'POST' });
        App.toast('Task approved', 'success');
        loadTasks(_selectedProjectId);
    }

    async function removeTask(taskId) {
        if (!_selectedProjectId) return;
        await fetch(`/api/agent/projects/${_selectedProjectId}/tasks/${taskId}`, { method: 'DELETE' });
        loadTasks(_selectedProjectId);
    }

    // ── Logs ───────────────────────────────────────────────────

    async function loadLogs(projectId) {
        try {
            const logs = await App.api(`/agent/projects/${projectId}/logs?limit=50`);
            const logEl = document.getElementById('agent-log');
            if (logs.length) {
                logEl.innerHTML = '';
                logs.forEach(l => appendLogEntry(l));
            }
        } catch {}
    }

    // ── Helpers ────────────────────────────────────────────────

    function hideEditors() {
        document.getElementById('project-editor').style.display = 'none';
        document.getElementById('task-editor').style.display = 'none';
        _editingProjectId = null;
    }

    function esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    }

    function formatInterval(seconds) {
        if (seconds < 60) return seconds + 's';
        if (seconds < 3600) return Math.round(seconds / 60) + ' min';
        return (seconds / 3600).toFixed(1) + ' hr';
    }

    // ── Init ───────────────────────────────────────────────────

    function init() {
        if (!_initialized) {
            // Controls
            document.getElementById('btn-agent-toggle').addEventListener('click', () => {
                const modeSelect = document.getElementById('agent-mode-select');
                const currentMode = modeSelect.value;
                // Toggle: if running, stop. If stopped, start.
                const badge = document.getElementById('agent-status-badge');
                if (badge.textContent.includes('Off') || badge.textContent.includes('⏸ Off')) {
                    const mode = currentMode === 'off' ? 'agent' : currentMode;
                    sendWS({ type: 'start', mode });
                } else if (badge.textContent.includes('Paused')) {
                    sendWS({ type: 'resume' });
                } else {
                    sendWS({ type: 'stop' });
                }
            });

            document.getElementById('agent-mode-select').addEventListener('change', (e) => {
                sendWS({ type: 'set_mode', mode: e.target.value });
            });

            // Interval slider
            const slider = document.getElementById('agent-interval');
            const label = document.getElementById('agent-interval-label');
            slider.addEventListener('input', () => {
                label.textContent = formatInterval(parseInt(slider.value));
            });
            slider.addEventListener('change', () => {
                sendWS({ type: 'set_interval', interval: parseInt(slider.value) });
            });

            // Project buttons
            document.getElementById('btn-new-project').addEventListener('click', () => showProjectEditor(null));
            document.getElementById('btn-save-project').addEventListener('click', saveProject);
            document.getElementById('btn-cancel-project').addEventListener('click', hideEditors);
            document.getElementById('btn-delete-project').addEventListener('click', deleteCurrentProject);

            // Task buttons
            document.getElementById('btn-new-task').addEventListener('click', () => showTaskEditor(null));
            document.getElementById('btn-save-task').addEventListener('click', saveTask);
            document.getElementById('btn-cancel-task').addEventListener('click', hideEditors);

            _initialized = true;
        }

        connectWS();
        loadProjects();

        // Fetch initial status
        App.api('/agent/status').then(status => updateStatusUI(status)).catch(() => {});
    }

    return { init, approveTask, removeTask };
})();

window.ProactivePage = ProactivePage;
