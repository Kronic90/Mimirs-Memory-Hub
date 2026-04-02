/* ================================================================
   Models.js — Model browser & management
   ================================================================ */

const ModelsPage = (() => {
    let initialized = false;
    let scanDirs = [];

    // ── Tab switching ────────────────────────────────────────────
    function setupTabs() {
        document.querySelectorAll('.models-tabs .tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.models-tabs .tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const panel = document.getElementById('tab-' + tab.dataset.tab);
                if (panel) panel.classList.add('active');

                if (tab.dataset.tab === 'ollama') loadOllamaModels();
                if (tab.dataset.tab === 'local') loadScanDirs();
            });
        });
    }

    // ── Ollama models ────────────────────────────────────────────
    async function loadOllamaModels() {
        const status = document.getElementById('ollama-status');
        const list = document.getElementById('ollama-models-list');

        status.textContent = 'Checking Ollama…';
        status.style.borderLeftColor = '';

        try {
            const check = await App.api('/models/ollama/available');
            if (!check.available) {
                status.textContent = 'Ollama is not running. Start it with: ollama serve';
                status.style.borderLeft = '3px solid var(--warning)';
                list.innerHTML = '';
                return;
            }

            status.textContent = 'Ollama is running ✓';
            status.style.borderLeft = '3px solid var(--success)';

            const data = await App.api('/models');
            list.innerHTML = '';

            if (data.models && data.models.length > 0) {
                data.models.forEach(m => {
                    const card = document.createElement('div');
                    card.className = 'model-card';
                    card.innerHTML = `
                        <div class="model-info">
                            <div class="model-name">${esc(m.name || m.id)}</div>
                            <div class="model-meta">
                                ${m.parameters || ''} · ${App.formatBytes(m.size)} · ${m.quantization || ''}
                            </div>
                        </div>
                        <div class="model-actions">
                            <button class="btn btn-secondary" onclick="ModelsPage.useModel('${esc(m.id)}')">Use</button>
                        </div>`;
                    list.appendChild(card);
                });
            } else {
                list.innerHTML = '<p class="text-muted">No models installed. Pull one below.</p>';
            }
        } catch (e) {
            status.textContent = 'Could not connect to Ollama.';
            status.style.borderLeft = '3px solid var(--error)';
        }
    }

    function useModel(modelId) {
        App.state.model = modelId;
        App.state.backend = 'ollama';
        document.getElementById('backend-select').value = 'ollama';
        const select = document.getElementById('model-select');
        let found = false;
        for (const opt of select.options) {
            if (opt.value === modelId) { found = true; break; }
        }
        if (!found) {
            const opt = document.createElement('option');
            opt.value = modelId;
            opt.textContent = modelId;
            select.appendChild(opt);
        }
        select.value = modelId;
        App.apiPut('/settings', { active_model: modelId, active_backend: 'ollama' });
        App.toast('Model set: ' + modelId, 'success');
        App.navigate('chat');
    }

    // ── Ollama pull ──────────────────────────────────────────────
    async function pullOllama() {
        const input = document.getElementById('ollama-pull-input');
        const name = input.value.trim();
        if (!name) return;

        App.toast('Pulling ' + name + '…', 'info');
        try {
            const resp = await fetch('/api/models');
            App.toast('Pull request sent. Check Ollama logs for progress.', 'info');
            setTimeout(() => loadOllamaModels(), 5000);
        } catch (e) {
            App.toast('Pull failed: ' + e.message, 'error');
        }
    }

    // ── HuggingFace search ───────────────────────────────────────
    async function searchHF() {
        const input = document.getElementById('hf-search-input');
        const query = input.value.trim();
        const results = document.getElementById('hf-results');

        results.innerHTML = '<p class="text-muted">Searching…</p>';

        try {
            const models = await App.api('/models/hf/search?q=' + encodeURIComponent(query));
            results.innerHTML = '';

            if (Array.isArray(models) && models.length > 0) {
                models.forEach(m => {
                    const card = document.createElement('div');
                    card.className = 'model-card';
                    card.innerHTML = `
                        <div class="model-info">
                            <div class="model-name">${esc(m.name)}</div>
                            <div class="model-meta">
                                ${esc(m.author)} · ⬇ ${(m.downloads || 0).toLocaleString()} · ♥ ${m.likes || 0}
                            </div>
                        </div>
                        <div class="model-actions">
                            <button class="btn btn-secondary" onclick="ModelsPage.viewRepo('${esc(m.repo_id)}')">Files</button>
                        </div>`;
                    results.appendChild(card);
                });
            } else {
                results.innerHTML = '<p class="text-muted">No GGUF models found.</p>';
            }
        } catch (e) {
            results.innerHTML = '<p class="text-muted" style="color:var(--error)">Search failed.</p>';
        }
    }

    async function viewRepo(repoId) {
        const results = document.getElementById('hf-results');
        results.innerHTML = '<p class="text-muted">Loading files…</p>';

        try {
            const files = await App.api('/models/hf/files?repo_id=' + encodeURIComponent(repoId));
            results.innerHTML = `<p style="margin-bottom:12px;"><strong>${esc(repoId)}</strong> — GGUF files:</p>`;
            const backBtn = document.createElement('button');
            backBtn.className = 'btn btn-secondary';
            backBtn.style.marginBottom = '12px';
            backBtn.textContent = '← Back to results';
            backBtn.onclick = searchHF;
            results.appendChild(backBtn);

            if (Array.isArray(files) && files.length > 0) {
                files.forEach(f => {
                    const card = document.createElement('div');
                    card.className = 'model-card';
                    const btnId = 'dl-' + f.filename.replace(/[^a-zA-Z0-9]/g, '_');
                    card.innerHTML = `
                        <div class="model-info">
                            <div class="model-name">${esc(f.filename)}</div>
                            <div class="model-meta">${App.formatBytes(f.size)}</div>
                            <div class="download-progress" id="prog-${btnId}" style="display:none;">
                                <div class="progress-bar"><div class="progress-fill" id="fill-${btnId}"></div></div>
                                <div class="progress-text" id="text-${btnId}"></div>
                            </div>
                        </div>
                        <div class="model-actions">
                            <button class="btn btn-primary" id="${btnId}"
                                onclick="ModelsPage.downloadHF('${esc(f.repo_id)}', '${esc(f.filename)}', '${btnId}')">
                                Download
                            </button>
                        </div>`;
                    results.appendChild(card);
                });
            } else {
                results.innerHTML += '<p class="text-muted">No GGUF files found in this repo.</p>';
            }
        } catch {
            results.innerHTML = '<p class="text-muted" style="color:var(--error)">Could not load files.</p>';
        }
    }

    async function downloadHF(repoId, filename, btnId) {
        const btn = document.getElementById(btnId);
        const prog = document.getElementById('prog-' + btnId);
        const fill = document.getElementById('fill-' + btnId);
        const text = document.getElementById('text-' + btnId);

        btn.disabled = true;
        btn.textContent = 'Starting…';
        prog.style.display = 'block';

        try {
            const resp = await App.apiPost('/models/hf/download', {
                repo_id: repoId,
                filename: filename,
            });

            if (resp.status === 'exists') {
                btn.textContent = '✓ Already downloaded';
                text.textContent = resp.path;
                fill.style.width = '100%';
                App.toast(filename + ' already downloaded', 'info');
                return;
            }

            btn.textContent = 'Downloading…';
            // Poll real progress from status endpoint
            let checks = 0;
            const maxChecks = 1200; // 20 minutes at 1s intervals
            const pollInterval = setInterval(async () => {
                checks++;
                try {
                    const status = await App.api('/models/hf/download/status');
                    const prog_data = status[filename];
                    if (prog_data) {
                        if (prog_data.status === 'complete') {
                            clearInterval(pollInterval);
                            fill.style.width = '100%';
                            text.textContent = 'Downloaded: ' + (prog_data.path || filename);
                            btn.textContent = '✓ Downloaded';
                            App.toast(filename + ' downloaded!', 'success');
                            // Auto-switch to local backend and select this model
                            if (prog_data.path) {
                                useLocalModel(prog_data.path);
                            } else {
                                App.loadModels();
                            }
                            return;
                        } else if (prog_data.status === 'error') {
                            clearInterval(pollInterval);
                            text.textContent = 'Error: ' + (prog_data.error || 'Unknown');
                            btn.textContent = 'Retry';
                            btn.disabled = false;
                            App.toast('Download failed: ' + (prog_data.error || ''), 'error');
                            return;
                        } else if (prog_data.status === 'downloading') {
                            const pct = prog_data.percent || 0;
                            fill.style.width = pct + '%';
                            const dl = prog_data.downloaded || 0;
                            const total = prog_data.total || 0;
                            text.textContent = `${App.formatBytes(dl)} / ${App.formatBytes(total)} (${pct}%)`;
                        }
                    }
                } catch { /* ignore poll errors */ }
                if (checks >= maxChecks) {
                    clearInterval(pollInterval);
                    text.textContent = 'Download may still be in progress. Check Models > Local tab.';
                    btn.textContent = 'Check Local';
                    btn.disabled = false;
                }
            }, 1000);

        } catch (e) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            text.textContent = 'Download failed: ' + (e.message || 'Unknown error');
            App.toast('Download failed', 'error');
        }
    }

    // ── Local GGUF scanner ───────────────────────────────────────

    async function loadScanDirs() {
        try {
            const settings = await App.api('/settings');
            scanDirs = settings.scan_directories || [];
            renderScanDirs();
            // Load cached scan results so user doesn't re-scan every reload
            loadScanCache();
        } catch { /* ignore */ }
    }

    async function loadScanCache() {
        try {
            const models = await App.api('/models/scan/cache');
            if (Array.isArray(models) && models.length > 0) {
                renderScanResults(models);
            }
        } catch { /* ignore */ }
    }

    function renderScanDirs() {
        const list = document.getElementById('scan-dir-list');
        list.innerHTML = '';
        scanDirs.forEach((dir, i) => {
            const tag = document.createElement('span');
            tag.className = 'scan-dir-tag';
            tag.innerHTML = `${esc(dir)} <button class="remove-dir" onclick="ModelsPage.removeScanDir(${i})">×</button>`;
            list.appendChild(tag);
        });
    }

    async function addScanDir() {
        const input = document.getElementById('scan-dir-input');
        const dir = input.value.trim();
        if (!dir) return;

        if (!scanDirs.includes(dir)) {
            scanDirs.push(dir);
        }
        const resp = await App.apiPost('/models/scan/dirs', { directories: scanDirs });
        if (resp.directories) {
            scanDirs = resp.directories;
        }
        input.value = '';
        renderScanDirs();
        App.toast('Directory added', 'success');
    }

    async function removeScanDir(index) {
        scanDirs.splice(index, 1);
        await App.apiPost('/models/scan/dirs', { directories: scanDirs });
        renderScanDirs();
    }

    async function scanPC() {
        const status = document.getElementById('scan-status');
        const list = document.getElementById('local-models-list');
        const btn = document.getElementById('btn-scan-pc');

        btn.disabled = true;
        btn.textContent = '⏳ Scanning…';
        status.style.display = 'block';
        status.textContent = 'Scanning your computer for GGUF files. This may take a moment…';
        status.style.borderLeft = '3px solid var(--info)';
        list.innerHTML = '';

        try {
            const models = await App.api('/models/scan');
            status.style.display = 'none';

            if (Array.isArray(models) && models.length > 0) {
                renderScanResults(models);
                App.toast('Found ' + models.length + ' GGUF file(s)', 'success');
            } else {
                list.innerHTML = '<p class="text-muted">No GGUF files found. Try adding directories above.</p>';
            }
        } catch (e) {
            status.textContent = 'Scan failed: ' + (e.message || 'Unknown error');
            status.style.borderLeft = '3px solid var(--error)';
        }
        btn.disabled = false;
        btn.textContent = '🔍 Scan for GGUF files';
    }

    function renderScanResults(models) {
        const list = document.getElementById('local-models-list');
        list.innerHTML = '';
        models.forEach(m => {
            const card = document.createElement('div');
            card.className = 'model-card';
            card.innerHTML = `
                <div class="model-info">
                    <div class="model-name">${esc(m.filename)}</div>
                    <div class="model-meta">${App.formatBytes(m.size)} · ${esc(m.parent_dir)}</div>
                </div>
                <div class="model-actions">
                    <button class="btn btn-secondary" onclick="ModelsPage.useLocalModel('${esc(m.path).replace(/\\/g, '\\\\')}')">Use</button>
                </div>`;
            list.appendChild(card);
        });
    }

    function useLocalModel(filePath) {
        App.state.model = filePath;
        App.state.backend = 'local';
        document.getElementById('backend-select').value = 'local';
        const select = document.getElementById('model-select');
        const name = filePath.split(/[\\/]/).pop();
        let found = false;
        for (const opt of select.options) {
            if (opt.value === filePath) { found = true; break; }
        }
        if (!found) {
            const opt = document.createElement('option');
            opt.value = filePath;
            opt.textContent = '\uD83D\uDCBE ' + name;
            select.appendChild(opt);
        }
        select.value = filePath;
        App.apiPut('/settings', { active_model: filePath, active_backend: 'local' });
        App.toast('Local model set: ' + name, 'success');
        App.navigate('chat');
    }

    // ── API Keys save ────────────────────────────────────────────
    async function saveAPIKeys() {
        console.log('=== Saving API Keys (using label-based lookup) ===');
        
        // Alternative approach: find inputs by their label text instead of ID
        function getInputByLabel(labelText) {
            const labels = Array.from(document.querySelectorAll('label'));
            const label = labels.find(l => l.textContent.trim() === labelText);
            if (!label) {
                console.error(`Label not found: "${labelText}"`);
                return null;
            }
            // Find input after this label (within form-group)
            const formGroup = label.closest('.form-group');
            if (!formGroup) {
                console.error(`Form group not found for label: "${labelText}"`);
                return null;
            }
            const input = formGroup.querySelector('input');
            console.log(`Found input for "${labelText}":`, input, 'value:', input?.value);
            return input;
        }
        
        const domValues = {
            'openai': getInputByLabel('OpenAI API Key')?.value?.trim() || '',
            'anthropic': getInputByLabel('Anthropic API Key')?.value?.trim() || '',
            'google': getInputByLabel('Google Gemini API Key')?.value?.trim() || '',
            'openrouter': getInputByLabel('OpenRouter API Key')?.value?.trim() || '',
            'vllm-url': getInputByLabel('vLLM Server URL')?.value?.trim() || '',
            'vllm-key': getInputByLabel('vLLM API Key (optional)')?.value?.trim() || '',
            'compat-url': getInputByLabel('Server URL')?.value?.trim() || '',
            'compat-key': getInputByLabel('API Key (optional)')?.value?.trim() || '',
            'custom-url': getInputByLabel('Custom Endpoint URL')?.value?.trim() || '',
            'custom-key': getInputByLabel('Custom Endpoint API Key (optional)')?.value?.trim() || '',
        };
        
        console.log('DOM field values:', {
            openai: domValues['openai'] ? `[${domValues['openai'].length} chars]` : '(empty)',
            anthropic: domValues['anthropic'] ? `[${domValues['anthropic'].length} chars]` : '(empty)',
            google: domValues['google'] ? `[${domValues['google'].length} chars]` : '(empty)',
            openrouter: domValues['openrouter'] ? `[${domValues['openrouter'].length} chars]` : '(empty)',
            vllm_url: domValues['vllm-url'] ? domValues['vllm-url'] : '(empty)',
            compat_url: domValues['compat-url'] ? domValues['compat-url'] : '(empty)',
            custom_url: domValues['custom-url'] ? domValues['custom-url'] : '(empty)',
            custom_key: domValues['custom-key'] ? `[${domValues['custom-key'].length} chars]` : '(empty)',
        });

        const backends = {};
        const fields = [
            ['openai',    'openai'],
            ['anthropic', 'anthropic'],
            ['google',    'google'],
            ['openrouter', 'openrouter'],
            ['custom',    'custom-key'],
        ];
        
        for (const [name, key] of fields) {
            const val = domValues[key];
            if (val) {
                if (!/^[\x20-\x7E]+$/.test(val)) {
                    App.toast(`${name} key contains non-ASCII characters`, 'error');
                    console.error(`${name} validation failed - non-ASCII chars detected`);
                    return;
                }
                if (!backends[name]) backends[name] = {};
                backends[name].api_key = val;
                console.log(`✓ Added ${name}: ${val.substring(0,8)}...${val.substring(val.length-4)}`);
            }
        }
        
        const customUrl = domValues['custom-url'];
        if (customUrl) {
            if (!backends.custom) backends.custom = {};
            backends.custom.base_url = customUrl;
            console.log(`✓ Added custom URL: ${customUrl}`);
        }

        // vLLM server
        const vllmUrl = domValues['vllm-url'];
        const vllmKey = domValues['vllm-key'];
        if (vllmUrl) {
            if (!backends.vllm) backends.vllm = {};
            backends.vllm.base_url = vllmUrl;
            if (vllmKey) backends.vllm.api_key = vllmKey;
            console.log(`✓ Added vLLM URL: ${vllmUrl}`);
        }

        // OpenAI-compatible server
        const compatUrl = domValues['compat-url'];
        const compatKey = domValues['compat-key'];
        if (compatUrl) {
            if (!backends.openai_compat) backends.openai_compat = {};
            backends.openai_compat.base_url = compatUrl;
            if (compatKey) backends.openai_compat.api_key = compatKey;
            console.log(`✓ Added OpenAI-compat URL: ${compatUrl}`);
        }
        
        if (Object.keys(backends).length === 0) {
            App.toast('No keys to save', 'warning');
            console.warn('No keys entered');
            return;
        }
        
        console.log('Sending patch:', backends);
        try {
            const result = await App.apiPut('/settings', { backends });
            console.log('Save successful:', result);
            App.toast('API keys saved', 'success');
            
            // Wait a moment then reload to verify what was actually saved
            setTimeout(async () => {
                try {
                    const settings = await App.api('/settings');
                    console.log('Verification - backends after save:', {
                        openai: settings.backends?.openai?.api_key ? `[masked or stored]` : '(empty)',
                        anthropic: settings.backends?.anthropic?.api_key ? `[masked or stored]` : '(empty)',
                        google: settings.backends?.google?.api_key ? `[masked or stored]` : '(empty)',
                        openrouter: settings.backends?.openrouter?.api_key ? `[masked or stored]` : '(empty)',
                        vllm: settings.backends?.vllm?.base_url || '(empty)',
                        openai_compat: settings.backends?.openai_compat?.base_url || '(empty)',
                    });
                } catch (e) {
                    console.error('Could not verify save:', e);
                }
            }, 1000);
            
            App.loadModels();
        } catch (e) {
            console.error('Save failed:', e);
            App.toast('Failed to save API keys', 'error');
        }
    }

    // ── Escape HTML ──────────────────────────────────────────────
    function esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        if (!initialized) {
            setupTabs();

            document.getElementById('btn-ollama-pull').addEventListener('click', pullOllama);
            document.getElementById('ollama-pull-input').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') pullOllama();
            });
            document.getElementById('btn-hf-search').addEventListener('click', searchHF);
            document.getElementById('hf-search-input').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') searchHF();
            });
            document.getElementById('btn-save-keys').addEventListener('click', saveAPIKeys);
            document.getElementById('btn-scan-pc').addEventListener('click', scanPC);
            document.getElementById('btn-add-scan-dir').addEventListener('click', addScanDir);
            document.getElementById('scan-dir-input').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') addScanDir();
            });

            // mmproj / VL model path
            const mmProjInput = document.getElementById('local-mmproj-path');
            const mmProjSave  = document.getElementById('btn-save-mmproj');
            if (mmProjInput && mmProjSave) {
                // Pre-fill saved value
                App.api('/settings').then(s => {
                    mmProjInput.value = s?.backends?.local?.mmproj_path || '';
                }).catch(() => {});
                mmProjSave.addEventListener('click', async () => {
                    try {
                        await App.apiPut('/settings', {
                            backends: { local: { mmproj_path: mmProjInput.value.trim() } }
                        });
                        App.toast('mmproj path saved', 'success');
                        App.loadVisionModels();
                    } catch { App.toast('Failed to save mmproj path', 'error'); }
                });
            }

            // Scan for mmproj files button
            const btnScanMmproj = document.getElementById('btn-scan-mmproj');
            const mmProjResults = document.getElementById('mmproj-scan-results');
            if (btnScanMmproj && mmProjResults) {
                btnScanMmproj.addEventListener('click', async () => {
                    btnScanMmproj.disabled = true;
                    btnScanMmproj.textContent = '⏳ Scanning…';
                    mmProjResults.innerHTML = '';
                    try {
                        const results = await App.api('/models/mmproj/scan');
                        if (results && results.length > 0) {
                            results.forEach(m => {
                                const row = document.createElement('div');
                                row.style.cssText = 'display:flex;gap:8px;align-items:center;margin-bottom:4px;padding:4px 8px;background:var(--surface);border-radius:6px;font-size:0.85rem;';
                                row.innerHTML = `
                                    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${m.path}">${m.filename}</span>
                                    <span class="text-muted">${App.formatBytes(m.size)}</span>
                                    <button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:0.78rem;">Use</button>
                                `;
                                row.querySelector('button').addEventListener('click', () => {
                                    const mmInput = document.getElementById('local-mmproj-path');
                                    if (mmInput) mmInput.value = m.path;
                                    App.apiPut('/settings', {
                                        backends: { local: { mmproj_path: m.path } }
                                    }).then(() => {
                                        App.toast('mmproj set: ' + m.filename, 'success');
                                        App.loadVisionModels();
                                    });
                                });
                                mmProjResults.appendChild(row);
                            });
                        } else {
                            mmProjResults.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">No mmproj files found. Download one alongside your VL model.</p>';
                        }
                    } catch {
                        mmProjResults.innerHTML = '<p style="color:var(--error);font-size:0.82rem;">Scan failed</p>';
                    }
                    btnScanMmproj.disabled = false;
                    btnScanMmproj.textContent = '🔍 Scan';
                });
            }

            initialized = true;
        }
        loadOllamaModels();
    }

    return { init, useModel, viewRepo, downloadHF, removeScanDir, useLocalModel };
})();
