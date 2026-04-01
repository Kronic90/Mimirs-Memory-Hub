/* ================================================================
   Visualize.js — Memory graph visualization on Canvas
   Shows memories as glowing nodes with edges, vividness-based sizing,
   type-based coloring, and interactive hover/click details.
   ================================================================ */

const VisualizePage = (() => {
    let initialized = false;
    let graphData = null;
    let nodesLayout = [];
    let canvas, ctx;
    let width, height;
    let hoveredNode = null;
    let selectedNode = null;
    let animFrame = null;
    let filter = 'all';
    let camX = 0, camY = 0, camZoom = 1;
    let dragging = false, dragStartX = 0, dragStartY = 0;

    // Colors for memory types
    const COLORS = {
        episodic:   { fill: '#7c3aed', glow: 'rgba(124,58,237,',  label: 'Episodic' },
        social:     { fill: '#3b82f6', glow: 'rgba(59,130,246,',  label: 'Social' },
        huginn:     { fill: '#f59e0b', glow: 'rgba(245,158,11,',  label: 'Huginn' },
        volva:      { fill: '#8b5cf6', glow: 'rgba(139,92,246,',  label: 'Völva' },
        flashbulb:  { fill: '#ef4444', glow: 'rgba(239,68,68,',   label: 'Flashbulb' },
        cherished:  { fill: '#ec4899', glow: 'rgba(236,72,153,',  label: 'Cherished' },
        anchor:     { fill: '#10b981', glow: 'rgba(16,185,129,',  label: 'Anchor' },
        task:       { fill: '#06b6d4', glow: 'rgba(6,182,212,',   label: 'Task' },
        lesson:     { fill: '#f97316', glow: 'rgba(249,115,22,',  label: 'Lesson' },
        conversation: { fill: '#6366f1', glow: 'rgba(99,102,241,', label: 'Conversation' },
    };

    // Edge type colors
    const EDGE_COLORS = {
        entity:    'rgba(59,130,246,0.3)',
        lexical:   'rgba(124,58,237,0.15)',
        temporal:  'rgba(245,158,11,0.25)',
        emotional: 'rgba(236,72,153,0.3)',
    };

    function getNodeColor(node) {
        if (node._type === 'lesson') return COLORS.lesson;
        if (node._type === 'task') return COLORS.task;
        if (node.is_cherished) return COLORS.cherished;
        if (node.is_flashbulb) return COLORS.flashbulb;
        if (node.is_anchor) return COLORS.anchor;
        if (node.source === 'huginn') return COLORS.huginn;
        if (node.source === 'volva') return COLORS.volva;
        if (node.source === 'social' || node.entity) return COLORS.social;
        if (node.source === 'conversation') return COLORS.conversation;
        return COLORS.episodic;
    }

    function matchesFilter(node) {
        if (filter === 'all') return true;
        if (filter === 'cherished') return node.is_cherished;
        if (filter === 'flashbulb') return node.is_flashbulb;
        if (filter === 'anchor') return node.is_anchor;
        if (filter === 'task') return node._type === 'task';
        if (filter === 'social') return node.source === 'social' || !!node.entity;
        if (filter === 'huginn') return node.source === 'huginn';
        if (filter === 'volva') return node.source === 'volva';
        return true;
    }

    // ── Layout: force-directed simulation ────────────────────────
    function layoutNodes(data) {
        const nodes = [];
        const totalNodes = (data.nodes?.length || 0) + (data.lessons?.length || 0) + (data.tasks?.length || 0);

        // Calculate layout radius based on node count
        const layoutRadius = Math.max(300, Math.sqrt(totalNodes) * 50);

        // Build entity map for social clustering — each entity gets its own sub-angle
        const entityNames = [];
        (data.nodes || []).forEach(n => {
            if ((n.source === 'social' || n.entity) && n.entity) {
                if (!entityNames.includes(n.entity)) entityNames.push(n.entity);
            }
        });
        const entityAngleMap = {};
        const socialBaseAngle = -Math.PI * 0.15;
        const socialArcSpan = Math.min(Math.PI * 0.7, entityNames.length * 0.35);
        entityNames.forEach((name, idx) => {
            entityAngleMap[name] = socialBaseAngle + (idx / Math.max(entityNames.length - 1, 1)) * socialArcSpan;
        });

        // Place memory nodes
        (data.nodes || []).forEach((n, i) => {
            // Cluster by type — angle offset per type
            let clusterAngle = 0;
            const isSocial = n.source === 'social' || (n.entity && n.entity.length > 0);
            if (isSocial && n.entity && entityAngleMap[n.entity] != null) {
                // Each entity gets its own tight sub-cluster
                clusterAngle = entityAngleMap[n.entity];
            } else if (isSocial) {
                clusterAngle = 0;
            } else if (n.source === 'huginn') clusterAngle = Math.PI * 0.4;
            else if (n.source === 'volva') clusterAngle = Math.PI * 0.8;
            else if (n.source === 'conversation') clusterAngle = Math.PI * 1.2;
            else clusterAngle = Math.PI * 1.6;

            // Cherished/flashbulb/anchor get inner ring
            let radius = layoutRadius;
            if (n.is_cherished || n.is_flashbulb) radius *= 0.4;
            else if (n.is_anchor) radius *= 0.6;
            else radius *= (0.5 + Math.random() * 0.5);

            // Social memories cluster tighter around their entity angle
            const jitter = isSocial ? 0.3 : 1.0;
            const posJitter = isSocial ? 30 : 60;
            const angle = clusterAngle + (Math.random() - 0.5) * jitter;
            const x = Math.cos(angle) * radius + (Math.random() - 0.5) * posJitter;
            const y = Math.sin(angle) * radius + (Math.random() - 0.5) * 60;

            // Size based on vividness (0-10 scale, map to 4-24px)
            const normViv = Math.min(n.vividness / 10, 1);
            const baseSize = 4 + normViv * 20;
            const size = Math.max(4, Math.min(24, baseSize));

            nodes.push({
                ...n,
                _type: 'memory',
                x, y,
                vx: 0, vy: 0,
                size,
                opacity: Math.max(0.15, normViv),
            });
        });

        // Place lessons in their own cluster
        (data.lessons || []).forEach((l, i) => {
            const angle = Math.PI * -0.3 + (i / Math.max(data.lessons.length, 1)) * 0.6;
            const radius = layoutRadius * 0.8;
            const normLessViv = Math.min(l.vividness / 10, 1);
            nodes.push({
                ...l,
                _type: 'lesson',
                x: Math.cos(angle) * radius + (Math.random() - 0.5) * 40,
                y: Math.sin(angle) * radius - layoutRadius * 0.3 + (Math.random() - 0.5) * 40,
                vx: 0, vy: 0,
                size: 8 + normLessViv * 10,
                opacity: Math.max(0.3, normLessViv),
                content: `[Lesson] ${l.topic}: ${l.strategy}`,
            });
        });

        // Place tasks
        (data.tasks || []).forEach((t, i) => {
            const angle = Math.PI * 1.0 + (i / Math.max(data.tasks.length, 1)) * 0.6;
            const radius = layoutRadius * 0.7;
            nodes.push({
                ...t,
                _type: 'task',
                x: Math.cos(angle) * radius + (Math.random() - 0.5) * 40,
                y: Math.sin(angle) * radius + (Math.random() - 0.5) * 40,
                vx: 0, vy: 0,
                size: 10,
                opacity: t.status === 'active' ? 1.0 : 0.4,
                content: `[Task] ${t.description}`,
            });
        });

        // Simple force simulation (repulsion + edge attraction)
        for (let iter = 0; iter < 80; iter++) {
            // Repulsion
            for (let i = 0; i < nodes.length; i++) {
                for (let j = i + 1; j < nodes.length; j++) {
                    const dx = nodes[j].x - nodes[i].x;
                    const dy = nodes[j].y - nodes[i].y;
                    const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
                    const force = 800 / (dist * dist);
                    const fx = (dx / dist) * force;
                    const fy = (dy / dist) * force;
                    nodes[i].vx -= fx;
                    nodes[i].vy -= fy;
                    nodes[j].vx += fx;
                    nodes[j].vy += fy;
                }
            }

            // Edge attraction
            if (data.edges) {
                data.edges.forEach(e => {
                    if (e.source < nodes.length && e.target < nodes.length) {
                        const a = nodes[e.source];
                        const b = nodes[e.target];
                        const dx = b.x - a.x;
                        const dy = b.y - a.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist > 80) {
                            const force = (dist - 80) * 0.01 * e.strength;
                            const fx = (dx / dist) * force;
                            const fy = (dy / dist) * force;
                            a.vx += fx;
                            a.vy += fy;
                            b.vx -= fx;
                            b.vy -= fy;
                        }
                    }
                });
            }

            // Apply velocities with damping
            const damping = 0.85;
            nodes.forEach(n => {
                n.x += n.vx;
                n.y += n.vy;
                n.vx *= damping;
                n.vy *= damping;
            });
        }

        return nodes;
    }

    // ── Rendering ────────────────────────────────────────────────
    let glowPhase = 0;

    function draw() {
        if (!ctx) return;
        glowPhase += 0.02;
        ctx.clearRect(0, 0, width, height);

        ctx.save();
        ctx.translate(width / 2 + camX, height / 2 + camY);
        ctx.scale(camZoom, camZoom);

        const visibleNodes = nodesLayout.filter(matchesFilter);
        const visibleIds = new Set(visibleNodes.map(n => n.id));

        // Draw edges
        if (graphData?.edges) {
            graphData.edges.forEach(e => {
                const a = nodesLayout[e.source];
                const b = nodesLayout[e.target];
                if (!a || !b) return;
                if (!visibleIds.has(a.id) && !visibleIds.has(b.id)) return;

                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.strokeStyle = EDGE_COLORS[e.type] || 'rgba(255,255,255,0.05)';
                ctx.lineWidth = Math.max(0.5, e.strength * 2);
                ctx.stroke();
            });
        }

        // Draw lesson-memory connections
        if (graphData?.lessons) {
            const lessonStartIdx = (graphData.nodes?.length || 0);
            graphData.lessons.forEach((l, i) => {
                if (l.source_idx != null && l.source_idx < nodesLayout.length) {
                    const lessonNode = nodesLayout[lessonStartIdx + i];
                    const srcNode = nodesLayout[l.source_idx];
                    if (lessonNode && srcNode) {
                        ctx.beginPath();
                        ctx.moveTo(lessonNode.x, lessonNode.y);
                        ctx.lineTo(srcNode.x, srcNode.y);
                        ctx.strokeStyle = 'rgba(249,115,22,0.2)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([4, 4]);
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                }
            });
        }

        // Draw social entity group bubbles
        const entityGroups = {};
        visibleNodes.forEach(node => {
            if ((node.source === 'social' || node.entity) && node.entity) {
                if (!entityGroups[node.entity]) entityGroups[node.entity] = [];
                entityGroups[node.entity].push(node);
            }
        });
        const entityColorPalette = [
            'rgba(59,130,246,', 'rgba(16,185,129,', 'rgba(236,72,153,',
            'rgba(245,158,11,', 'rgba(139,92,246,', 'rgba(6,182,212,',
            'rgba(249,115,22,', 'rgba(234,179,8,',
        ];
        let entityColorIdx = 0;
        Object.entries(entityGroups).forEach(([entity, members]) => {
            if (members.length < 1) return;
            // Compute bounding circle
            let cx = 0, cy = 0;
            members.forEach(m => { cx += m.x; cy += m.y; });
            cx /= members.length;
            cy /= members.length;
            let maxDist = 0;
            members.forEach(m => {
                const d = Math.sqrt((m.x - cx) ** 2 + (m.y - cy) ** 2);
                if (d > maxDist) maxDist = d;
            });
            const bubbleRadius = maxDist + 40;
            const eColor = entityColorPalette[entityColorIdx % entityColorPalette.length];
            entityColorIdx++;

            // Filled bubble background
            const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, bubbleRadius);
            gradient.addColorStop(0, eColor + '0.06)');
            gradient.addColorStop(1, eColor + '0.01)');
            ctx.beginPath();
            ctx.arc(cx, cy, bubbleRadius, 0, Math.PI * 2);
            ctx.fillStyle = gradient;
            ctx.fill();

            // Dashed ring
            ctx.beginPath();
            ctx.arc(cx, cy, bubbleRadius, 0, Math.PI * 2);
            ctx.strokeStyle = eColor + '0.25)';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([6, 4]);
            ctx.stroke();
            ctx.setLineDash([]);

            // Entity label
            ctx.font = 'bold 12px system-ui, sans-serif';
            ctx.fillStyle = eColor + '0.7)';
            ctx.textAlign = 'center';
            ctx.fillText(entity, cx, cy - bubbleRadius - 8);
        });

        // Draw nodes
        visibleNodes.forEach(node => {
            const color = getNodeColor(node);
            const isHovered = hoveredNode === node;
            const isSelected = selectedNode === node;
            const size = node.size * (isHovered ? 1.3 : 1);

            // Glow effect — cherished pulse, flashbulb bright, faded dim
            const normOpacity = Math.min(node.opacity, 1);
            const glowIntensity = node.is_cherished
                ? 0.5 + Math.sin(glowPhase * 2) * 0.2
                : node.is_flashbulb
                    ? 0.6
                    : normOpacity * 0.3;

            // Outer glow
            if (glowIntensity > 0.1) {
                const gradient = ctx.createRadialGradient(
                    node.x, node.y, size * 0.5,
                    node.x, node.y, size * 3
                );
                gradient.addColorStop(0, color.glow + (glowIntensity * 0.6) + ')');
                gradient.addColorStop(1, color.glow + '0)');
                ctx.beginPath();
                ctx.arc(node.x, node.y, size * 3, 0, Math.PI * 2);
                ctx.fillStyle = gradient;
                ctx.fill();
            }

            // Node body
            ctx.beginPath();
            ctx.arc(node.x, node.y, size, 0, Math.PI * 2);
            ctx.fillStyle = color.fill;
            ctx.globalAlpha = node.opacity;
            ctx.fill();
            ctx.globalAlpha = 1;

            // Border for special types
            if (node.is_cherished || node.is_flashbulb || node.is_anchor || isSelected) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, size + 2, 0, Math.PI * 2);
                ctx.strokeStyle = isSelected ? '#ffffff' : color.fill;
                ctx.lineWidth = isSelected ? 2 : 1.5;
                ctx.stroke();
            }

            // Anchor diamond marker
            if (node.is_anchor && node._type === 'memory') {
                ctx.save();
                ctx.translate(node.x, node.y - size - 6);
                ctx.rotate(Math.PI / 4);
                ctx.fillStyle = COLORS.anchor.fill;
                ctx.fillRect(-3, -3, 6, 6);
                ctx.restore();
            }

            // Label for hovered/selected
            if (isHovered || isSelected) {
                const label = (node.content || '').substring(0, 50);
                ctx.font = '11px system-ui, sans-serif';
                ctx.fillStyle = '#e4e4e7';
                ctx.textAlign = 'center';
                ctx.fillText(label + (label.length >= 50 ? '…' : ''), node.x, node.y + size + 16);
            }
        });

        ctx.restore();
        animFrame = requestAnimationFrame(draw);
    }

    // ── Interaction ──────────────────────────────────────────────
    function getNodeAt(clientX, clientY) {
        const rect = canvas.getBoundingClientRect();
        const mx = (clientX - rect.left - width / 2 - camX) / camZoom;
        const my = (clientY - rect.top - height / 2 - camY) / camZoom;

        let closest = null;
        let closestDist = Infinity;

        nodesLayout.filter(matchesFilter).forEach(node => {
            const dx = node.x - mx;
            const dy = node.y - my;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < node.size + 5 && dist < closestDist) {
                closest = node;
                closestDist = dist;
            }
        });
        return closest;
    }

    function showTooltip(node, e) {
        const tip = document.getElementById('viz-tooltip');
        if (!node) {
            tip.style.display = 'none';
            return;
        }
        const color = getNodeColor(node);
        const viv = node.vividness != null ? node.vividness.toFixed(1) + '/10' : '';
        let badges = '';
        if (node.is_cherished) badges += '<span class="viz-badge cherished">♥ Cherished</span>';
        if (node.is_flashbulb) badges += '<span class="viz-badge flashbulb">⚡ Flashbulb</span>';
        if (node.is_anchor) badges += '<span class="viz-badge anchor">⚓ Anchor</span>';

        tip.innerHTML = `
            <div class="viz-tip-header" style="border-left:3px solid ${color.fill};">
                <strong>${color.label}</strong> ${badges}
            </div>
            <div class="viz-tip-content">${esc(node.content || '')}</div>
            <div class="viz-tip-meta">
                ${viv ? `Vividness: ${viv}` : ''}
                ${node.emotion ? ` · ${node.emotion}` : ''}
                ${node.importance ? ` · Imp: ${node.importance}` : ''}
            </div>`;
        tip.style.display = 'block';
        tip.style.left = (e.clientX + 16) + 'px';
        tip.style.top = (e.clientY - 10) + 'px';
    }

    function showDetail(node) {
        const panel = document.getElementById('viz-detail');
        const content = document.getElementById('viz-detail-content');
        const color = getNodeColor(node);

        let badges = '';
        if (node.is_cherished) badges += '<span class="viz-badge cherished">♥ Cherished</span>';
        if (node.is_flashbulb) badges += '<span class="viz-badge flashbulb">⚡ Flashbulb</span>';
        if (node.is_anchor) badges += '<span class="viz-badge anchor">⚓ Anchor</span>';

        const viv = node.vividness != null ? node.vividness.toFixed(1) : '?';

        // Find connected memories
        let connections = '';
        if (graphData?.edges && node._type === 'memory') {
            const connected = graphData.edges
                .filter(e => e.source === node.id || e.target === node.id)
                .map(e => {
                    const otherId = e.source === node.id ? e.target : e.source;
                    const other = nodesLayout[otherId];
                    if (!other) return null;
                    return `<span class="viz-connection">${e.type}: ${esc((other.content || '').substring(0, 40))}…</span>`;
                })
                .filter(Boolean)
                .slice(0, 10);
            if (connected.length) {
                connections = `<div class="viz-detail-section"><strong>Connections (${connected.length})</strong>${connected.join('')}</div>`;
            }
        }

        content.innerHTML = `
            <div style="border-left:3px solid ${color.fill}; padding-left:12px; margin-bottom:12px;">
                <div style="font-size:14px; font-weight:600; margin-bottom:4px;">${color.label} ${badges}</div>
                <div style="font-size:13px; color:var(--text); line-height:1.5;">${esc(node.content || '')}</div>
            </div>
            <div class="viz-detail-grid">
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${viv}/10</div>
                    <div class="viz-detail-stat-label">Vividness</div>
                </div>
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${node.importance || '—'}</div>
                    <div class="viz-detail-stat-label">Importance</div>
                </div>
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${node.emotion || '—'}</div>
                    <div class="viz-detail-stat-label">Emotion</div>
                </div>
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${node.stability ? node.stability.toFixed(0) + 'd' : '—'}</div>
                    <div class="viz-detail-stat-label">Stability</div>
                </div>
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${node.access_count || 0}</div>
                    <div class="viz-detail-stat-label">Recalls</div>
                </div>
                <div class="viz-detail-stat">
                    <div class="viz-detail-stat-val">${node.source || '—'}</div>
                    <div class="viz-detail-stat-label">Source</div>
                </div>
            </div>
            ${connections}
            ${node.timestamp ? `<div class="text-muted" style="font-size:11px; margin-top:8px;">Created: ${new Date(node.timestamp).toLocaleString()}</div>` : ''}
        `;
        panel.style.display = 'block';
    }

    function closeDetail() {
        document.getElementById('viz-detail').style.display = 'none';
        selectedNode = null;
    }

    // ── Data loading ─────────────────────────────────────────────
    async function loadGraph() {
        try {
            graphData = await App.api('/memory/graph');
            nodesLayout = layoutNodes(graphData);
            if (!animFrame) draw();
        } catch (e) {
            const container = document.getElementById('viz-container');
            container.innerHTML = '<p class="text-muted" style="padding:40px;text-align:center;">No memories yet. Start chatting to build your memory graph!</p>';
        }
    }

    // ── Setup ────────────────────────────────────────────────────
    function setupCanvas() {
        canvas = document.getElementById('viz-canvas');
        const container = document.getElementById('viz-container');
        ctx = canvas.getContext('2d');

        function resize() {
            width = container.clientWidth;
            height = container.clientHeight || 600;
            canvas.width = width;
            canvas.height = height;
        }
        resize();
        window.addEventListener('resize', resize);

        // Mouse events
        canvas.addEventListener('mousemove', (e) => {
            if (dragging) {
                camX += e.clientX - dragStartX;
                camY += e.clientY - dragStartY;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                return;
            }
            const node = getNodeAt(e.clientX, e.clientY);
            hoveredNode = node;
            canvas.style.cursor = node ? 'pointer' : 'grab';
            showTooltip(node, e);
        });

        canvas.addEventListener('mousedown', (e) => {
            const node = getNodeAt(e.clientX, e.clientY);
            if (node) {
                selectedNode = node;
                showDetail(node);
            } else {
                dragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                canvas.style.cursor = 'grabbing';
            }
        });

        canvas.addEventListener('mouseup', () => {
            dragging = false;
            canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
        });

        canvas.addEventListener('mouseleave', () => {
            hoveredNode = null;
            dragging = false;
            document.getElementById('viz-tooltip').style.display = 'none';
        });

        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            camZoom = Math.max(0.1, Math.min(5, camZoom * delta));
        }, { passive: false });
    }

    function esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }

    function init() {
        if (!initialized) {
            setupCanvas();

            document.getElementById('btn-viz-refresh').addEventListener('click', loadGraph);
            document.getElementById('viz-filter').addEventListener('change', (e) => {
                filter = e.target.value;
            });

            initialized = true;
        }
        loadGraph();
    }

    return { init, closeDetail };
})();
