/* ================================================================
   Import.js — Import memories from external files/text
   Parses .txt, .md, .json and sends to Mimir for full reindexing.
   ================================================================ */

const ImportPage = (() => {
    let initialized = false;
    let pendingEntries = [];

    function parseContent(text, format) {
        const entries = [];
        if (format === 'json') {
            try {
                const data = JSON.parse(text);
                // Handle many common JSON formats from different AI systems
                const arr = _extractArray(data);
                arr.forEach(item => {
                    if (typeof item === 'string') {
                        if (item.trim().length > 3) entries.push({ content: item.trim() });
                    } else if (item && typeof item === 'object') {
                        const content = _extractText(item);
                        if (content && content.length > 3) {
                            entries.push({
                                content: content,
                                emotion: item.emotion || item.sentiment || undefined,
                                importance: item.importance || item.priority || item.score || undefined,
                                timestamp: item.timestamp || item.date || item.created_at || item.time || item.created || undefined,
                                why_saved: item.why_saved || item.source || item.reason || item.category || item.type || undefined,
                            });
                        }
                    }
                });
            } catch {
                entries.push({ content: text.trim(), _parseError: 'Invalid JSON, imported as single entry' });
            }
        } else if (format === 'paragraphs') {
            text.split(/\n\s*\n/).forEach(para => {
                const trimmed = para.trim();
                if (trimmed && trimmed.length > 5) {
                    entries.push({ content: trimmed });
                }
            });
        } else {
            // lines
            text.split('\n').forEach(line => {
                const trimmed = line.trim();
                if (trimmed && trimmed.length > 5) {
                    // Skip markdown headers as separators
                    if (trimmed.match(/^#{1,3}\s/) && trimmed.length < 60) return;
                    entries.push({ content: trimmed });
                }
            });
        }
        return entries;
    }

    /** Extract the iterable array from various JSON structures */
    function _extractArray(data) {
        if (Array.isArray(data)) return data;
        // ChatGPT export: {mapping: {id: {message: ...}}}
        if (data.mapping) {
            return Object.values(data.mapping)
                .filter(m => m.message && m.message.content)
                .map(m => {
                    const parts = m.message.content.parts || [];
                    return { content: parts.join('\n'), role: m.message.author?.role };
                })
                .filter(m => m.role !== 'system');
        }
        // Look for common wrapper keys
        for (const key of ['memories', 'entries', 'messages', 'data', 'results', 'items', 'records', 'conversations', 'history', 'core_memory', 'recall_memory', 'archival_memory']) {
            if (Array.isArray(data[key])) return data[key];
        }
        // Single object with content
        if (_extractText(data)) return [data];
        return [];
    }

    /** Extract text content from an object, trying many common field names */
    function _extractText(item) {
        // Direct text fields (most common across AI memory systems)
        for (const key of ['content', 'text', 'body', 'memory', 'entry', 'message', 'summary', 'note', 'description', 'value', 'input', 'output', 'response', 'query', 'human', 'assistant', 'user']) {
            if (typeof item[key] === 'string' && item[key].trim()) return item[key].trim();
        }
        // Nested: item.message.content (ChatGPT style)
        if (item.message && typeof item.message === 'object') {
            if (typeof item.message.content === 'string') return item.message.content.trim();
            if (Array.isArray(item.message.content?.parts)) return item.message.content.parts.join('\n').trim();
        }
        // Conversation turn: combine role + content
        if (item.role && (item.content || item.text)) {
            const txt = (item.content || item.text || '').trim();
            return item.role === 'user' ? `User: ${txt}` : txt;
        }
        return null;
    }

    function detectFormat(filename) {
        if (filename.endsWith('.json')) return 'json';
        if (filename.endsWith('.md')) return 'paragraphs';
        return 'lines';
    }

    function showPreview(entries) {
        pendingEntries = entries;
        const preview = document.getElementById('import-preview');
        const list = document.getElementById('import-preview-list');
        preview.style.display = 'block';

        list.innerHTML = '';
        const maxShow = Math.min(entries.length, 50);
        entries.slice(0, maxShow).forEach((entry, i) => {
            const card = document.createElement('div');
            card.className = 'import-preview-item';
            card.innerHTML = `
                <div class="import-preview-num">${i + 1}</div>
                <div class="import-preview-text">${esc(entry.content.substring(0, 200))}${entry.content.length > 200 ? '…' : ''}</div>
                <button class="btn-icon" onclick="ImportPage.removeEntry(${i})" title="Remove">×</button>
            `;
            list.appendChild(card);
        });
        if (entries.length > maxShow) {
            list.innerHTML += `<p class="text-muted">…and ${entries.length - maxShow} more</p>`;
        }
    }

    function removeEntry(index) {
        pendingEntries.splice(index, 1);
        showPreview(pendingEntries);
    }

    async function handleFileUpload(files) {
        const emotion = document.getElementById('import-emotion').value;
        const importance = parseInt(document.getElementById('import-importance').value) || 5;
        let allEntries = [];

        for (const file of files) {
            const text = await file.text();
            const format = detectFormat(file.name);
            const entries = parseContent(text, format);
            entries.forEach(e => {
                if (!e.emotion) e.emotion = emotion;
                if (!e.importance) e.importance = importance;
                e.why_saved = e.why_saved || `Imported from ${file.name}`;
            });
            allEntries = allEntries.concat(entries);
        }

        if (allEntries.length === 0) {
            App.toast('No memories found in uploaded files', 'error');
            return;
        }

        showPreview(allEntries);
        App.toast(`Parsed ${allEntries.length} memories from ${files.length} file(s)`, 'info');
    }

    function handlePaste() {
        const text = document.getElementById('import-content').value.trim();
        if (!text) {
            App.toast('Paste some content first', 'error');
            return;
        }

        const format = document.getElementById('import-format').value;
        const emotion = document.getElementById('import-emotion').value;
        const importance = parseInt(document.getElementById('import-importance').value) || 5;

        const entries = parseContent(text, format);
        entries.forEach(e => {
            if (!e.emotion) e.emotion = emotion;
            if (!e.importance) e.importance = importance;
            e.why_saved = e.why_saved || 'Pasted import';
        });

        if (entries.length === 0) {
            App.toast('No memories could be parsed from content', 'error');
            return;
        }

        showPreview(entries);
        App.toast(`Parsed ${entries.length} memories`, 'info');
    }

    async function confirmImport() {
        if (pendingEntries.length === 0) {
            App.toast('No memories to import', 'error');
            return;
        }

        const enrich = document.getElementById('import-enrich')?.checked || false;

        const status = document.getElementById('import-status');
        status.style.display = 'block';
        status.textContent = `Importing ${pendingEntries.length} memories into Mimir${enrich ? ' (with AI enrichment)' : ''}…`;
        status.style.borderLeft = '3px solid var(--info)';

        const btn = document.getElementById('btn-import-confirm');
        btn.disabled = true;
        btn.textContent = 'Importing…';

        try {
            // Send in batches of 20
            const batchSize = 20;
            let total = 0;
            for (let i = 0; i < pendingEntries.length; i += batchSize) {
                const batch = pendingEntries.slice(i, i + batchSize);
                const result = await App.apiPost('/memory/import', { entries: batch, enrich: enrich });
                total += result.imported || 0;
                status.textContent = `Imported ${total} / ${pendingEntries.length} memories…`;
            }

            status.textContent = `✓ Successfully imported ${total} memories into Mimir!`;
            status.style.borderLeft = '3px solid var(--success)';
            App.toast(`Imported ${total} memories!`, 'success');
            pendingEntries = [];
            document.getElementById('import-preview').style.display = 'none';
            document.getElementById('import-content').value = '';
        } catch (e) {
            status.textContent = 'Import failed: ' + (e.message || 'Unknown error');
            status.style.borderLeft = '3px solid var(--error)';
            App.toast('Import failed', 'error');
        }

        btn.disabled = false;
        btn.textContent = 'Confirm Import';
    }

    function esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }

    function init() {
        if (!initialized) {
            const dropzone = document.getElementById('import-dropzone');
            const fileInput = document.getElementById('import-file-input');

            dropzone.addEventListener('click', () => fileInput.click());
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = 'var(--accent)';
            });
            dropzone.addEventListener('dragleave', () => {
                dropzone.style.borderColor = '';
            });
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.style.borderColor = '';
                handleFileUpload(e.dataTransfer.files);
            });
            fileInput.addEventListener('change', () => {
                if (fileInput.files.length) handleFileUpload(fileInput.files);
            });

            document.getElementById('btn-import').addEventListener('click', handlePaste);
            document.getElementById('btn-import-confirm').addEventListener('click', confirmImport);

            initialized = true;
        }
    }

    return { init, removeEntry };
})();
