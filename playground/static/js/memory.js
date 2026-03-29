/* ================================================================
   Memory.js — Full memory browser with edit, delete, filters
   ================================================================ */

const MemoryPage = (() => {
    let initialized = false;
    let currentOffset = 0;
    const PAGE_SIZE = 30;

    // ── Load stats ───────────────────────────────────────────────
    async function loadStats() {
        const grid = document.getElementById('stats-grid');
        try {
            const stats = await App.api('/memory/stats');
            const cards = [
                { label: 'Memories', value: stats.total_reflections || 0, icon: '🧠' },
                { label: 'Mood', value: stats.mood || '—', icon: '😊' },
                { label: 'Flashbulbs', value: stats.flashbulb_count || 0, icon: '⚡' },
                { label: 'Anchors', value: stats.anchor_count || 0, icon: '⚓' },
                { label: 'Cherished', value: stats.cherished_count || 0, icon: '💎' },
                { label: 'Social', value: (stats.social_entities || []).length, icon: '👥' },
                { label: 'Lessons', value: stats.total_lessons || 0, icon: '📚' },
                { label: 'Tasks', value: stats.active_tasks || 0, icon: '📋' },
                { label: 'Yggdrasil', value: stats.yggdrasil_edges || 0, icon: '🌳' },
                { label: 'Insights', value: stats.huginn_insights || 0, icon: '🔮' },
            ];
            grid.innerHTML = '';
            cards.forEach(c => {
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.innerHTML = `<div class="stat-icon">${c.icon}</div>
                    <div class="stat-info"><div class="stat-value">${c.value}</div>
                    <div class="stat-label">${c.label}</div></div>`;
                grid.appendChild(card);
            });
        } catch {
            grid.innerHTML = '<p class="text-muted">Could not load stats.</p>';
        }
    }

    // ── Load chemistry bars ──────────────────────────────────────
    async function loadChemistry() {
        try {
            const mood = await App.api('/memory/mood');
            const dash = document.getElementById('chemistry-dashboard');
            const moodLabel = document.getElementById('chem-mood-label');
            if (moodLabel) {
                moodLabel.textContent = mood.mood_label || 'neutral';
                moodLabel.className = 'chem-mood mood-' + (mood.mood_label || 'neutral');
            }
            const barsEl = document.getElementById('chem-bars');
            if (barsEl && mood.chemistry && mood.chemistry.levels) {
                const levels = mood.chemistry.levels;
                const colors = {
                    dopamine: '#fbbf24', serotonin: '#60a5fa',
                    oxytocin: '#f472b6', norepinephrine: '#f97316',
                    endorphin: '#34d399'
                };
                barsEl.innerHTML = '';
                for (const [name, val] of Object.entries(levels)) {
                    const pct = Math.min(100, Math.max(0, val * 100));
                    const label = name.slice(0, 3).toUpperCase();
                    barsEl.innerHTML += `
                        <div class="chem-bar-row">
                            <span class="chem-label" title="${name}">${label}</span>
                            <div class="chem-bar-track">
                                <div class="chem-bar-fill" style="width:${pct}%;background:${colors[name] || '#7c3aed'}"></div>
                            </div>
                            <span class="chem-val">${val.toFixed(2)}</span>
                        </div>`;
                }
                if (mood.chemistry.description) {
                    barsEl.innerHTML += `<div class="chem-desc text-muted">${esc(mood.chemistry.description)}</div>`;
                }
                dash.style.display = '';
            } else {
                dash.style.display = 'none';
            }
        } catch {
            document.getElementById('chemistry-dashboard').style.display = 'none';
        }
    }

    // ── Load filter options ──────────────────────────────────────
    async function loadFilters() {
        try {
            const f = await App.api('/memory/filters');
            const emSel = document.getElementById('filter-emotion');
            const srcSel = document.getElementById('filter-source');
            emSel.innerHTML = '<option value="">All emotions</option>';
            (f.emotions || []).forEach(e => {
                emSel.innerHTML += `<option value="${esc(e)}">${esc(e)}</option>`;
            });
            srcSel.innerHTML = '<option value="">All sources</option>';
            (f.sources || []).forEach(s => {
                srcSel.innerHTML += `<option value="${esc(s)}">${esc(s)}</option>`;
            });
        } catch {}
    }

    // ── Browse memories (paginated) ──────────────────────────────
    async function browseMemories(offset) {
        if (offset === undefined) offset = currentOffset;
        currentOffset = offset;

        const emotion = document.getElementById('filter-emotion').value;
        const source = document.getElementById('filter-source').value;
        const sort = document.getElementById('filter-sort').value;
        const minImp = document.getElementById('filter-importance').value;

        const results = document.getElementById('memory-results');
        results.innerHTML = '<p class="text-muted">Loading…</p>';

        try {
            const params = new URLSearchParams({
                offset, limit: PAGE_SIZE, sort,
                emotion, source, min_importance: minImp,
            });
            const data = await App.api('/memory/browse?' + params);
            renderMemories(data.memories || [], false);
            updatePager(data.total, data.offset, data.limit);
        } catch {
            results.innerHTML = '<p class="text-muted" style="color:var(--error)">Failed to load.</p>';
        }
    }

    // ── Search/recall ────────────────────────────────────────────
    async function searchMemories() {
        const query = document.getElementById('memory-search-input').value.trim();
        if (!query) return browseMemories(0);

        const results = document.getElementById('memory-results');
        results.innerHTML = '<p class="text-muted">Searching…</p>';

        try {
            const memories = await App.apiPost('/memory/recall', { context: query, limit: 30 });
            renderMemories(memories || [], true);
            document.getElementById('memory-pager').style.display = 'none';
        } catch {
            results.innerHTML = '<p class="text-muted" style="color:var(--error)">Search failed.</p>';
        }
    }

    // ── Render memory cards ──────────────────────────────────────
    function renderMemories(memories, isSearch) {
        const results = document.getElementById('memory-results');
        results.innerHTML = '';

        if (!memories.length) {
            results.innerHTML = '<p class="text-muted">No memories found.</p>';
            return;
        }

        memories.forEach(m => {
            const card = document.createElement('div');
            card.className = 'memory-card emotion-' + (m.emotion || 'neutral');

            const idx = m._index;
            const isCherished = m.cherished;
            const isAnchor = m.anchor;

            const badges = [];
            if (m.is_flashbulb) badges.push('<span class="mem-badge flashbulb">⚡ flashbulb</span>');
            if (isCherished) badges.push('<span class="mem-badge cherished">💎 cherished</span>');
            if (isAnchor) badges.push('<span class="mem-badge anchor">⚓ anchor</span>');

            card.innerHTML = `
                <div class="memory-card-body">
                    <div class="memory-card-content">${esc(m.content || m.gist || '')}</div>
                    <div class="memory-card-badges">${badges.join('')}</div>
                </div>
                <div class="memory-card-meta">
                    <span class="mem-emotion">${esc(m.emotion || '—')}</span>
                    <span>imp: <strong>${m.importance || '—'}</strong></span>
                    <span>src: ${esc(m.source || '—')}</span>
                    ${m.vividness !== undefined ? `<span>vivid: ${m.vividness}</span>` : ''}
                    <span>${m.timestamp ? new Date(m.timestamp).toLocaleDateString() : ''}</span>
                </div>
                ${idx >= 0 && !isSearch ? `
                <div class="memory-card-actions">
                    <button class="btn-sm-action" onclick="MemoryPage.editMemory(${idx}, '${esc(m.emotion || 'neutral')}', ${m.importance || 5})" title="Edit">✏️</button>
                    <button class="btn-sm-action" onclick="MemoryPage.toggleCherish(${idx})" title="${isCherished ? 'Uncherish' : 'Cherish'}">${isCherished ? '💎' : '🤍'}</button>
                    <button class="btn-sm-action" onclick="MemoryPage.toggleAnchor(${idx})" title="${isAnchor ? 'Unanchor' : 'Anchor'}">${isAnchor ? '⚓' : '🔗'}</button>
                    <button class="btn-sm-action btn-danger" onclick="MemoryPage.deleteMemory(${idx})" title="Delete">🗑️</button>
                </div>` : ''}`;
            results.appendChild(card);
        });
    }

    // ── Pager ────────────────────────────────────────────────────
    function updatePager(total, offset, limit) {
        const pager = document.getElementById('memory-pager');
        const info = document.getElementById('pager-info');
        const end = Math.min(offset + limit, total);
        info.textContent = `${offset + 1}–${end} of ${total}`;
        document.getElementById('btn-prev-page').disabled = offset === 0;
        document.getElementById('btn-next-page').disabled = end >= total;
        pager.style.display = total > limit ? '' : 'none';
    }

    // ── Actions ──────────────────────────────────────────────────
    async function deleteMemory(idx) {
        if (!confirm('Delete this memory permanently?')) return;
        try {
            await fetch('/api/memory/' + idx, { method: 'DELETE' });
            App.toast('Memory deleted', 'success');
            browseMemories();
            loadStats();
        } catch { App.toast('Delete failed', 'error'); }
    }

    async function toggleCherish(idx) {
        try {
            const r = await App.apiPost('/memory/' + idx + '/cherish', {});
            App.toast(r.cherished ? 'Cherished ✨' : 'Uncherished', 'info');
            browseMemories();
            loadStats();
        } catch { App.toast('Failed', 'error'); }
    }

    async function toggleAnchor(idx) {
        try {
            const r = await App.apiPost('/memory/' + idx + '/anchor', {});
            App.toast(r.anchored ? 'Anchored ⚓' : 'Unanchored', 'info');
            browseMemories();
            loadStats();
        } catch { App.toast('Failed', 'error'); }
    }

    function editMemory(idx, currentEmotion, currentImp) {
        const emotion = prompt('Emotion:', currentEmotion);
        if (emotion === null) return;
        const impStr = prompt('Importance (1-10):', String(currentImp));
        if (impStr === null) return;
        const importance = parseInt(impStr);
        if (isNaN(importance) || importance < 1 || importance > 10) {
            App.toast('Importance must be 1-10', 'error'); return;
        }
        fetch('/api/memory/' + idx, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emotion, importance }),
        }).then(r => r.json()).then(() => {
            App.toast('Memory updated', 'success');
            browseMemories();
        }).catch(() => App.toast('Update failed', 'error'));
    }

    // ── Export ────────────────────────────────────────────────────
    async function exportMemories() {
        try {
            const memories = await App.api('/memory/export');
            const blob = new Blob([JSON.stringify(memories, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'mimir_memories.json';
            a.click(); URL.revokeObjectURL(url);
            App.toast(`Exported ${memories.length} memories`, 'success');
        } catch { App.toast('Export failed', 'error'); }
    }

    // ── Sleep ────────────────────────────────────────────────────
    async function triggerSleep() {
        App.toast('Running sleep consolidation…', 'info');
        try {
            await App.apiPost('/memory/sleep', {});
            App.toast('Consolidation complete', 'success');
            loadStats(); loadChemistry();
        } catch { App.toast('Consolidation failed', 'error'); }
    }

    // ── Huginn ───────────────────────────────────────────────────
    async function runHuginn() {
        App.toast('Running Huginn pattern detection…', 'info');
        try {
            const insights = await App.apiPost('/memory/huginn', {});
            const el = document.getElementById('insight-results');
            if (Array.isArray(insights) && insights.length > 0 && !insights[0].error) {
                el.innerHTML = '<h3>🔮 Huginn Insights</h3>' +
                    insights.map(i => `<div class="insight-card">
                        <div>${esc(i.content || i.gist || JSON.stringify(i))}</div>
                    </div>`).join('');
                el.style.display = '';
            } else {
                App.toast('No new insights found', 'info');
            }
            loadStats();
        } catch { App.toast('Huginn failed', 'error'); }
    }

    // ── Dream ────────────────────────────────────────────────────
    async function runDream() {
        App.toast('Running Völva dream synthesis…', 'info');
        try {
            const dreams = await App.apiPost('/memory/dream', {});
            const el = document.getElementById('insight-results');
            if (Array.isArray(dreams) && dreams.length > 0 && !dreams[0].error) {
                el.innerHTML = '<h3>💭 Völva Dreams</h3>' +
                    dreams.map(d => `<div class="insight-card dream">
                        <div>${esc(d.content || d.gist || JSON.stringify(d))}</div>
                    </div>`).join('');
                el.style.display = '';
            } else {
                App.toast('No dreams produced', 'info');
            }
            loadStats();
        } catch { App.toast('Dream failed', 'error'); }
    }

    // ── Reflect ──────────────────────────────────────────────────
    async function runReflect() {
        App.toast('Reflecting on memories…', 'info');
        try {
            const result = await App.apiPost('/memory/reflect', {});
            const el = document.getElementById('insight-results');
            if (result.reflection) {
                el.innerHTML = '<h3>🌀 Self-Reflection</h3>' +
                    `<div class="insight-card reflect">${esc(result.reflection)}</div>`;
                el.style.display = '';
                App.toast('Reflection stored', 'success');
            } else if (result.error) {
                App.toast('Reflect: ' + result.error, 'error');
            } else {
                App.toast('No reflection generated (check LLM is loaded)', 'info');
            }
            loadStats();
        } catch { App.toast('Reflect failed', 'error'); }
    }

    // ── AI Curate ────────────────────────────────────────────────
    async function runAICurate() {
        const instruction = prompt(
            'Optional curation instruction (leave blank for organic):',
            ''
        );
        if (instruction === null) return;
        App.toast('AI curating memories…', 'info');
        try {
            const result = await App.apiPost('/memory/edit', { instruction });
            if (result.error) {
                App.toast('Curate: ' + result.error, 'error');
            } else {
                const { promoted = 0, demoted = 0, forgotten = 0, updated = 0 } = result;
                App.toast(
                    `Done — promoted: ${promoted}, demoted: ${demoted}, ` +
                    `forgotten: ${forgotten}, updated: ${updated}`,
                    'success'
                );
                browseMemories(0);
                loadStats();
            }
        } catch { App.toast('AI curate failed', 'error'); }
    }

    // ── Social Impressions ───────────────────────────────────────
    async function loadSocialImpressions() {
        const el = document.getElementById('social-list');
        if (!el) return;
        try {
            const impressions = await App.api('/memory/social');
            if (!impressions.length) {
                el.innerHTML = '<p class="text-muted">No social impressions yet.</p>';
                return;
            }
            el.innerHTML = impressions.map(m => `
                <div class="memory-card emotion-${esc(m.emotion || 'neutral')}">
                    <div class="memory-card-body">
                        <strong>${esc(m.entity || m.entity_key || '—')}</strong>
                        <div class="memory-card-content">${esc(m.gist || m.content || '')}</div>
                    </div>
                    <div class="memory-card-meta">
                        <span class="mem-emotion">${esc(m.emotion || '—')}</span>
                        <span>${m.timestamp ? new Date(m.timestamp).toLocaleDateString() : ''}</span>
                    </div>
                </div>`).join('');
        } catch {
            el.innerHTML = '<p class="text-muted">Could not load.</p>';
        }
    }

    async function addSocialImpression() {
        const entity = document.getElementById('social-entity').value.trim();
        const content = document.getElementById('social-content').value.trim();
        const emotion = document.getElementById('social-emotion').value || 'neutral';
        const importance = parseInt(document.getElementById('social-importance').value) || 5;
        if (!entity || !content) { App.toast('Entity and content required', 'error'); return; }
        try {
            await App.apiPost('/memory/social', { entity, content, emotion, importance, why_saved: 'user-added social impression' });
            App.toast(`Impression about "${entity}" saved`, 'success');
            document.getElementById('social-content').value = '';
            loadSocialImpressions();
        } catch { App.toast('Failed to save impression', 'error'); }
    }

    // ── Lessons ──────────────────────────────────────────────────
    async function loadLessons() {
        const el = document.getElementById('lessons-list');
        if (!el) return;
        try {
            const lessons = await App.api('/memory/lessons');
            if (!lessons.length) {
                el.innerHTML = '<p class="text-muted">No lessons yet.</p>';
                return;
            }
            el.innerHTML = lessons.map(l => `
                <div class="lesson-card ${l.failures > 0 ? 'zeigarnik-active' : ''}">
                    <div class="lesson-topic">${esc(l.topic)}</div>
                    <div class="lesson-strategy">${esc(l.strategy || l.context_trigger || '')}</div>
                    <div class="lesson-meta">
                        <span>imp: ${l.importance}</span>
                        ${l.failures > 0 ? `<span class="zeigarnik-badge">⚠️ ${l.failures} unresolved</span>` : ''}
                    </div>
                </div>`).join('');
        } catch {
            el.innerHTML = '<p class="text-muted">Could not load.</p>';
        }
    }

    async function addLesson() {
        const topic = document.getElementById('lesson-topic').value.trim();
        const trigger = document.getElementById('lesson-trigger').value.trim();
        const strategy = document.getElementById('lesson-strategy').value.trim();
        const importance = parseInt(document.getElementById('lesson-importance').value) || 5;
        if (!topic || !strategy) { App.toast('Topic and strategy required', 'error'); return; }
        try {
            await App.apiPost('/memory/lessons', { topic, context_trigger: trigger, strategy, importance });
            App.toast('Lesson added', 'success');
            document.getElementById('lesson-topic').value = '';
            document.getElementById('lesson-trigger').value = '';
            document.getElementById('lesson-strategy').value = '';
            loadLessons();
            loadStats();
        } catch { App.toast('Failed to add lesson', 'error'); }
    }

    // ── Reminders ────────────────────────────────────────────────
    async function loadReminders() {
        const el = document.getElementById('reminders-list');
        if (!el) return;
        try {
            const reminders = await App.api('/memory/reminders');
            if (!reminders.length) {
                el.innerHTML = '<p class="text-muted">No reminders set.</p>';
                return;
            }
            el.innerHTML = reminders.map(r => `
                <div class="reminder-card ${r.is_due ? 'reminder-due' : ''}">
                    <div class="reminder-text">${esc(r.text)}</div>
                    <div class="reminder-meta">
                        ${r.is_due ? '🔔 DUE NOW' : '⏰ ' + new Date(r.trigger_at).toLocaleString()}
                    </div>
                </div>`).join('');
        } catch {
            el.innerHTML = '<p class="text-muted">Could not load.</p>';
        }
    }

    // ── Visual Memories ────────────────────────────────────────────────────
    async function loadVisualMemories() {
        const el = document.getElementById('visual-memories-grid');
        if (!el) return;
        try {
            const memories = await App.api('/memory/visual');
            if (!memories.length) {
                el.innerHTML = '<p class="text-muted">No visual memories saved yet.</p>';
                return;
            }
            el.innerHTML = '';
            memories.forEach(m => {
                const card = document.createElement('div');
                card.className = 'visual-memory-card';

                const img = document.createElement('img');
                img.src = '/api/memory/visual/' + m.visual_hash;
                img.className = 'vm-thumb';
                img.alt = m.visual_description || 'visual memory';
                img.loading = 'lazy';

                const overlay = document.createElement('div');
                overlay.className = 'vm-overlay';
                overlay.innerHTML = `
                    <div class="vm-desc">${esc(m.visual_description || '')}</div>
                    <div class="vm-meta">${esc(m.emotion || 'neutral')} ·
                        imp ${m.importance || 5} ·
                        ${m.timestamp ? new Date(m.timestamp).toLocaleDateString() : ''}
                    </div>`;

                card.appendChild(img);
                card.appendChild(overlay);
                el.appendChild(card);
            });
        } catch {
            el.innerHTML = '<p class="text-muted">Could not load visual memories.</p>';
        }
    }

    async function addReminder() {
        const text = document.getElementById('reminder-text').value.trim();
        const hours = parseFloat(document.getElementById('reminder-hours').value) || 24;
        if (!text) { App.toast('Reminder text required', 'error'); return; }
        try {
            await App.apiPost('/memory/reminders', { text, hours });
            App.toast(`Reminder set for ${hours}h`, 'success');
            document.getElementById('reminder-text').value = '';
            loadReminders();
        } catch { App.toast('Failed to set reminder', 'error'); }
    }

    // ── Tasks & Projects ─────────────────────────────────────────
    async function loadTasks() {
        const el = document.getElementById('tasks-list');
        const badge = document.getElementById('project-overview-badge');
        if (!el) return;
        try {
            const [tasks, overview] = await Promise.all([
                App.api('/tasks'),
                App.api('/project/overview'),
            ]);
            if (badge) {
                const parts = [];
                if (overview.project) parts.push(overview.project);
                parts.push(`${overview.tasks_active || 0} active`);
                parts.push(`${overview.tasks_completed || 0} done`);
                parts.push(`${overview.solutions_stored || 0} solutions`);
                badge.textContent = parts.join(' · ');
            }
            if (!tasks.length) {
                el.innerHTML = '<p class="text-muted">No tasks yet. Create tasks manually or let the Agent create them via &lt;task&gt; tags.</p>';
                return;
            }
            el.innerHTML = tasks.map(t => {
                const statusIcon = t.status === 'active' ? '🔵' : t.status === 'completed' ? '✅' : '❌';
                const actions = t.status === 'active' ? `
                    <button class="btn-sm-action" onclick="MemoryPage.completeTask('${esc(t.task_id)}')" title="Complete">✅</button>
                    <button class="btn-sm-action" onclick="MemoryPage.failTask('${esc(t.task_id)}')" title="Fail">❌</button>
                ` : '';
                return `<div class="organic-item">
                    <div style="flex:1;">
                        <span>${statusIcon}</span>
                        <strong>${esc(t.description)}</strong>
                        ${t.project ? `<span class="text-muted" style="font-size:0.8em;margin-left:8px;">[${esc(t.project)}]</span>` : ''}
                        <span class="text-muted" style="font-size:0.8em;margin-left:8px;">priority: ${t.priority}</span>
                        ${t.outcome ? `<span class="text-muted" style="font-size:0.8em;margin-left:8px;">→ ${esc(t.outcome)}</span>` : ''}
                    </div>
                    <div style="display:flex;gap:4px;">${actions}</div>
                </div>`;
            }).join('');
        } catch {
            el.innerHTML = '<p class="text-muted">Could not load tasks.</p>';
        }
    }

    async function addTask() {
        const desc = document.getElementById('task-description').value.trim();
        const priority = parseInt(document.getElementById('task-priority').value) || 5;
        const project = document.getElementById('task-project').value.trim();
        if (!desc) { App.toast('Task description required', 'error'); return; }
        try {
            const result = await App.apiPost('/tasks', { description: desc, priority, project });
            App.toast(`Task created: ${result.task_id.slice(0, 8)}`, 'success');
            document.getElementById('task-description').value = '';
            loadTasks();
        } catch { App.toast('Failed to create task', 'error'); }
    }

    async function completeTask(taskId) {
        const outcome = prompt('Outcome (optional):');
        if (outcome === null) return;
        try {
            await App.apiPost(`/tasks/${taskId}/complete`, { outcome });
            App.toast('Task completed', 'success');
            loadTasks();
            loadStats();
        } catch { App.toast('Failed to complete task', 'error'); }
    }

    async function failTask(taskId) {
        const reason = prompt('Failure reason (optional):');
        if (reason === null) return;
        try {
            await App.apiPost(`/tasks/${taskId}/fail`, { reason });
            App.toast('Task marked as failed', 'info');
            loadTasks();
            loadStats();
        } catch { App.toast('Failed to update task', 'error'); }
    }

    async function setProject() {
        const name = document.getElementById('task-project').value.trim();
        try {
            const result = await App.apiPost('/project/active', { name });
            App.toast(result.message || 'Project set', 'success');
            loadTasks();
        } catch { App.toast('Failed to set project', 'error'); }
    }

    // ── Solutions ──────────────────────────────────────────────────
    async function addSolution() {
        const problem = document.getElementById('solution-problem').value.trim();
        const solution = document.getElementById('solution-content').value.trim();
        const importance = parseInt(document.getElementById('solution-importance').value) || 5;
        if (!problem || !solution) { App.toast('Both problem and solution required', 'error'); return; }
        try {
            await App.apiPost('/solutions', { problem, solution, importance });
            App.toast('Solution recorded', 'success');
            document.getElementById('solution-problem').value = '';
            document.getElementById('solution-content').value = '';
            loadTasks();
        } catch { App.toast('Failed to record solution', 'error'); }
    }

    async function searchSolutions() {
        const problem = document.getElementById('solution-search').value.trim();
        if (!problem) { App.toast('Enter a problem to search for', 'error'); return; }
        const el = document.getElementById('solutions-list');
        try {
            const results = await App.apiPost('/solutions/search', { problem, top_k: 5 });
            if (!results.length) {
                el.innerHTML = '<p class="text-muted">No matching solutions found.</p>';
                return;
            }
            el.innerHTML = results.map(s => `<div class="organic-item">
                <div style="flex:1;">
                    <strong>Problem:</strong> ${esc(s.problem)}<br>
                    <strong>Solution:</strong> ${esc(s.solution)}
                    <span class="text-muted" style="font-size:0.8em;margin-left:8px;">
                        imp: ${s.importance} · used: ${s.reuse_count || 0}x
                    </span>
                </div>
            </div>`).join('');
        } catch { App.toast('Search failed', 'error'); }
    }

    // ── Escape ───────────────────────────────────────────────────
    function esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        if (!initialized) {
            document.getElementById('btn-sleep').addEventListener('click', triggerSleep);
            document.getElementById('btn-run-huginn').addEventListener('click', runHuginn);
            document.getElementById('btn-run-dream').addEventListener('click', runDream);
            document.getElementById('btn-export-memories').addEventListener('click', exportMemories);
            document.getElementById('btn-memory-search').addEventListener('click', searchMemories);
            document.getElementById('btn-browse-memories').addEventListener('click', () => browseMemories(0));
            document.getElementById('memory-search-input').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') searchMemories();
            });
            document.getElementById('btn-prev-page').addEventListener('click', () => {
                browseMemories(Math.max(0, currentOffset - PAGE_SIZE));
            });
            document.getElementById('btn-next-page').addEventListener('click', () => {
                browseMemories(currentOffset + PAGE_SIZE);
            });
            // Filter changes auto-refresh
            ['filter-emotion', 'filter-source', 'filter-sort', 'filter-importance'].forEach(id => {
                document.getElementById(id).addEventListener('change', () => browseMemories(0));
            });
            // New organic controls
            document.getElementById('btn-reflect')?.addEventListener('click', runReflect);
            document.getElementById('btn-ai-curate')?.addEventListener('click', runAICurate);
            document.getElementById('btn-add-social')?.addEventListener('click', addSocialImpression);
            document.getElementById('btn-add-lesson')?.addEventListener('click', addLesson);
            document.getElementById('btn-add-reminder')?.addEventListener('click', addReminder);
            document.getElementById('btn-refresh-visual')?.addEventListener('click', loadVisualMemories);
            // Task/project controls
            document.getElementById('btn-add-task')?.addEventListener('click', addTask);
            document.getElementById('btn-set-project')?.addEventListener('click', setProject);
            document.getElementById('btn-refresh-tasks')?.addEventListener('click', loadTasks);
            document.getElementById('btn-add-solution')?.addEventListener('click', addSolution);
            document.getElementById('btn-search-solutions')?.addEventListener('click', searchSolutions);
            initialized = true;
        }
        loadStats();
        loadChemistry();
        loadFilters();
        browseMemories(0);
        loadSocialImpressions();
        loadLessons();
        loadReminders();
        loadVisualMemories();
        loadTasks();
    }

    return {
        init, editMemory, deleteMemory, toggleCherish, toggleAnchor,
        runReflect, runAICurate, loadSocialImpressions, loadLessons, loadReminders,
        loadVisualMemories, loadTasks, addTask, completeTask, failTask,
        setProject, addSolution, searchSolutions
    };
})();
