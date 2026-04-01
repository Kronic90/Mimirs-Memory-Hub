/* ================================================================
   Visualizations.js — Additional Memory Visualization Modes
   Extends the original VisualizePage to add 4 new visualization types
   ================================================================ */

// Initialize tab switching
document.addEventListener('DOMContentLoaded', () => {
    setupVisualizationTabs();
});

function setupVisualizationTabs() {
    const tabs = document.querySelectorAll('.viz-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            const vizType = e.target.dataset.viz;
            switchVizualizationView(vizType);
        });
    });
}

function switchVizualizationView(vizType) {
    // Update active tab
    document.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-viz="${vizType}"]`).classList.add('active');

    // Hide all views
    document.querySelectorAll('.viz-view').forEach(v => v.style.display = 'none');

    // Show selected view
    const viewEl = document.getElementById(`viz-${vizType}`);
    if (viewEl) {
        viewEl.style.display = 'block';
        
        // Trigger refresh on the original visualization if selecting it
        if (vizType === 'original' && VisualizePage && VisualizePage.init) {
            VisualizePage.init();
        } else if (vizType === 'landscape') {
            loadLandscape3D();
        } else if (vizType === 'mood-timeline') {
            loadMoodTimeline();
        } else if (vizType === 'cherished') {
            loadCherishedWall();
        } else if (vizType === 'chemistry') {
            loadChemistryTimeline();
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 2. MEMORY LANDSCAPE 3D — Immersive Neural Constellation
// ═══════════════════════════════════════════════════════════════

let _landscape3dCleanup = null;

async function loadLandscape3D() {
    try {
        const res = await App.api('/visualization/landscape');
        renderLandscape3D(res);
    } catch (err) {
        console.error('Failed to load landscape:', err);
        document.getElementById('landscape-container').innerHTML = 
            '<p class="text-muted" style="padding:40px;text-align:center;">Failed to load 3D landscape. Check console for errors.</p>';
    }
}

function renderLandscape3D(data) {
    const container = document.getElementById('landscape-container');
    if (!container) return;

    // Cleanup previous
    if (_landscape3dCleanup) { _landscape3dCleanup(); _landscape3dCleanup = null; }
    const existingCanvas = container.querySelector('canvas');
    if (existingCanvas) existingCanvas.remove();
    // Remove old tooltip/legend
    container.querySelectorAll('.landscape-tooltip, .landscape-legend, .landscape-stats').forEach(el => el.remove());

    const width = container.offsetWidth;
    const height = container.offsetHeight || 600;
    const nodes = data.nodes || [];
    const edges = data.edges || [];

    if (nodes.length === 0) {
        container.innerHTML = '<p class="text-muted" style="padding:40px;text-align:center;">No memories yet. Start chatting to build your memory constellation!</p>';
        return;
    }

    // ── Scene setup ──────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x050510, 0.015);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.set(18, 14, 18);
    camera.lookAt(5, 5, 5);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);

    // ── Starfield background ─────────────────────────────────
    const starGeo = new THREE.BufferGeometry();
    const starCount = 1500;
    const starPositions = new Float32Array(starCount * 3);
    const starSizes = new Float32Array(starCount);
    for (let i = 0; i < starCount; i++) {
        starPositions[i * 3]     = (Math.random() - 0.5) * 200;
        starPositions[i * 3 + 1] = (Math.random() - 0.5) * 200;
        starPositions[i * 3 + 2] = (Math.random() - 0.5) * 200;
        starSizes[i] = Math.random() * 1.5 + 0.5;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    starGeo.setAttribute('size', new THREE.BufferAttribute(starSizes, 1));
    const starMat = new THREE.PointsMaterial({
        color: 0x8888cc, size: 0.15, transparent: true, opacity: 0.6, sizeAttenuation: true,
    });
    scene.add(new THREE.Points(starGeo, starMat));

    // ── Lights ───────────────────────────────────────────────
    const ambient = new THREE.AmbientLight(0x1a1a3e, 0.8);
    scene.add(ambient);
    const pointLight = new THREE.PointLight(0x7c3aed, 1.0, 50);
    pointLight.position.set(5, 12, 5);
    scene.add(pointLight);
    const pointLight2 = new THREE.PointLight(0x3b82f6, 0.6, 40);
    pointLight2.position.set(10, 5, 10);
    scene.add(pointLight2);
    const rimLight = new THREE.DirectionalLight(0xec4899, 0.3);
    rimLight.position.set(-10, 8, -5);
    scene.add(rimLight);

    // ── Grid (subtle, stylised) ──────────────────────────────
    const gridHelper = new THREE.GridHelper(12, 12, 0x1a1a3e, 0x111128);
    gridHelper.position.y = -0.5;
    scene.add(gridHelper);

    // ── Axis labels (floating text using sprites) ────────────
    function makeTextSprite(text, color) {
        const cvs = document.createElement('canvas');
        cvs.width = 256; cvs.height = 64;
        const c = cvs.getContext('2d');
        c.font = 'bold 28px system-ui, sans-serif';
        c.fillStyle = color;
        c.textAlign = 'center';
        c.fillText(text, 128, 40);
        const tex = new THREE.CanvasTexture(cvs);
        const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.7 });
        const sprite = new THREE.Sprite(mat);
        sprite.scale.set(3, 0.75, 1);
        return sprite;
    }
    const xLabel = makeTextSprite('Vividness →', '#a78bfa');
    xLabel.position.set(6, -1.2, 0);
    scene.add(xLabel);
    const yLabel = makeTextSprite('↑ Importance', '#34d399');
    yLabel.position.set(-1.5, 6, 0);
    scene.add(yLabel);
    const zLabel = makeTextSprite('Stability →', '#60a5fa');
    zLabel.position.set(0, -1.2, 6);
    scene.add(zLabel);

    // ── Color palette ────────────────────────────────────────
    const colorMap = {
        episodic:     { base: 0x7c3aed, emissive: 0x5b21b6 },
        social:       { base: 0x3b82f6, emissive: 0x1d4ed8 },
        huginn:       { base: 0xf59e0b, emissive: 0xd97706 },
        volva:        { base: 0x8b5cf6, emissive: 0x6d28d9 },
        conversation: { base: 0x6366f1, emissive: 0x4338ca },
        visual:       { base: 0x14b8a6, emissive: 0x0d9488 },
    };

    // ── Create memory nodes ──────────────────────────────────
    const meshes = [];
    const nodeGroup = new THREE.Group();
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    nodes.forEach((node, i) => {
        const colors = colorMap[node.color] || colorMap.episodic;
        const importance = (node.importance || 5) / 10;
        const baseRadius = 0.08 + importance * 0.18;
        const isCherished = node.is_cherished;
        const isAnchor = node.is_anchor;
        const isFlashbulb = node.is_flashbulb;

        // Core sphere
        const geo = new THREE.SphereGeometry(baseRadius, 24, 24);
        const mat = new THREE.MeshPhongMaterial({
            color: colors.base,
            emissive: colors.emissive,
            emissiveIntensity: isCherished ? 0.7 : isFlashbulb ? 0.9 : 0.35,
            transparent: true,
            opacity: 0.9,
            shininess: 80,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(node.x, node.y, node.z);
        mesh.userData = { index: i, node };
        nodeGroup.add(mesh);
        meshes.push(mesh);

        // Outer glow shell for cherished/anchor/flashbulb
        if (isCherished || isAnchor || isFlashbulb) {
            const glowColor = isCherished ? 0xec4899 : isAnchor ? 0x10b981 : 0xef4444;
            const glowGeo = new THREE.SphereGeometry(baseRadius * 2.2, 16, 16);
            const glowMat = new THREE.MeshBasicMaterial({
                color: glowColor, transparent: true, opacity: 0.08, side: THREE.BackSide,
            });
            const glowMesh = new THREE.Mesh(glowGeo, glowMat);
            glowMesh.position.copy(mesh.position);
            nodeGroup.add(glowMesh);
            mesh.userData.glowMesh = glowMesh;
            mesh.userData.glowColor = glowColor;
        }

        // Ring for anchor memories
        if (isAnchor) {
            const ringGeo = new THREE.RingGeometry(baseRadius * 1.6, baseRadius * 1.9, 32);
            const ringMat = new THREE.MeshBasicMaterial({
                color: 0x10b981, transparent: true, opacity: 0.5, side: THREE.DoubleSide,
            });
            const ring = new THREE.Mesh(ringGeo, ringMat);
            ring.position.copy(mesh.position);
            ring.lookAt(camera.position);
            nodeGroup.add(ring);
            mesh.userData.ring = ring;
        }
    });
    scene.add(nodeGroup);

    // ── Create edges (neural connections) ────────────────────
    const edgeLineColors = {
        entity:    0x3b82f6, lexical: 0x7c3aed,
        temporal:  0xf59e0b, emotional: 0xec4899,
    };
    edges.forEach(edge => {
        if (edge.source >= nodes.length || edge.target >= nodes.length) return;
        const srcNode = nodes[edge.source];
        const tgtNode = nodes[edge.target];
        const lineGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(srcNode.x, srcNode.y, srcNode.z),
            new THREE.Vector3(tgtNode.x, tgtNode.y, tgtNode.z),
        ]);
        const lineColor = edgeLineColors[edge.type] || 0x444466;
        const lineMat = new THREE.LineBasicMaterial({
            color: lineColor,
            transparent: true,
            opacity: Math.min(0.5, edge.strength * 0.6),
            linewidth: 1,
        });
        scene.add(new THREE.Line(lineGeo, lineMat));
    });

    // ── Floating entity labels ───────────────────────────────
    const entityPositions = {};
    nodes.forEach(n => {
        if (n.entity) {
            if (!entityPositions[n.entity]) entityPositions[n.entity] = { xs: [], ys: [], zs: [] };
            entityPositions[n.entity].xs.push(n.x);
            entityPositions[n.entity].ys.push(n.y);
            entityPositions[n.entity].zs.push(n.z);
        }
    });
    Object.entries(entityPositions).forEach(([name, pos]) => {
        const cx = pos.xs.reduce((a, b) => a + b, 0) / pos.xs.length;
        const cy = Math.max(...pos.ys) + 0.8;
        const cz = pos.zs.reduce((a, b) => a + b, 0) / pos.zs.length;
        const label = makeTextSprite(name, '#60a5fa');
        label.position.set(cx, cy, cz);
        label.scale.set(2, 0.5, 1);
        scene.add(label);
    });

    // ── Tooltip div ──────────────────────────────────────────
    const tooltip = document.createElement('div');
    tooltip.className = 'landscape-tooltip';
    tooltip.style.cssText = 'position:absolute;display:none;pointer-events:none;' +
        'background:rgba(9,9,11,0.92);border:1px solid rgba(124,58,237,0.3);' +
        'border-radius:8px;padding:10px 14px;font-size:12px;color:#e4e4e7;' +
        'max-width:280px;z-index:100;backdrop-filter:blur(8px);' +
        'box-shadow:0 4px 20px rgba(0,0,0,0.5);';
    container.appendChild(tooltip);

    // ── Legend ────────────────────────────────────────────────
    const legend = document.createElement('div');
    legend.className = 'landscape-legend';
    legend.style.cssText = 'position:absolute;bottom:12px;left:12px;' +
        'background:rgba(9,9,11,0.8);border:1px solid rgba(255,255,255,0.08);' +
        'border-radius:8px;padding:10px 14px;font-size:11px;color:#a1a1aa;' +
        'backdrop-filter:blur(8px);line-height:1.8;';
    const legendItems = [
        { color: '#7c3aed', label: 'Episodic' },
        { color: '#3b82f6', label: 'Social' },
        { color: '#f59e0b', label: 'Huginn insight' },
        { color: '#8b5cf6', label: 'Völva dream' },
        { color: '#6366f1', label: 'Conversation' },
        { color: '#ec4899', label: '♥ Cherished' },
        { color: '#10b981', label: '⚓ Anchor' },
        { color: '#ef4444', label: '⚡ Flashbulb' },
    ];
    legend.innerHTML = '<div style="font-weight:600;margin-bottom:4px;color:#e4e4e7;">Memory Types</div>' +
        legendItems.map(l =>
            `<div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${l.color};margin-right:6px;"></span>${l.label}</div>`
        ).join('');
    container.appendChild(legend);

    // ── Stats overlay ────────────────────────────────────────
    const statsEl = document.createElement('div');
    statsEl.className = 'landscape-stats';
    statsEl.style.cssText = 'position:absolute;top:12px;right:12px;' +
        'background:rgba(9,9,11,0.8);border:1px solid rgba(255,255,255,0.08);' +
        'border-radius:8px;padding:10px 14px;font-size:11px;color:#a1a1aa;' +
        'backdrop-filter:blur(8px);';
    const cherishedCount = nodes.filter(n => n.is_cherished).length;
    const anchorCount = nodes.filter(n => n.is_anchor).length;
    statsEl.innerHTML = `<div style="font-weight:600;color:#e4e4e7;margin-bottom:4px;">Neural Constellation</div>` +
        `<div>${nodes.length} memories · ${edges.length} connections</div>` +
        (cherishedCount ? `<div style="color:#ec4899;">♥ ${cherishedCount} cherished</div>` : '') +
        (anchorCount ? `<div style="color:#10b981;">⚓ ${anchorCount} anchored</div>` : '');
    container.appendChild(statsEl);

    // ── OrbitControls (if available) or manual ───────────────
    let controls = null;
    if (typeof THREE.OrbitControls !== 'undefined') {
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.target.set(5, 5, 5);
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.5;
    }

    // ── Animation ────────────────────────────────────────────
    let animId = null;
    const clock = new THREE.Clock();
    let hoveredMesh = null;

    function animate() {
        animId = requestAnimationFrame(animate);
        const elapsed = clock.getElapsedTime();

        // Pulse cherished memories
        meshes.forEach(m => {
            const nd = m.userData.node;
            if (nd && nd.is_cherished) {
                const pulse = 0.5 + Math.sin(elapsed * 2 + m.userData.index) * 0.3;
                m.material.emissiveIntensity = pulse;
                if (m.userData.glowMesh) {
                    m.userData.glowMesh.material.opacity = 0.04 + Math.sin(elapsed * 2 + m.userData.index) * 0.04;
                }
            }
            // Rotate anchor rings to face camera
            if (m.userData.ring) {
                m.userData.ring.lookAt(camera.position);
            }
        });

        // Gentle light movement
        pointLight.position.x = 5 + Math.sin(elapsed * 0.3) * 3;
        pointLight.position.z = 5 + Math.cos(elapsed * 0.3) * 3;

        // Star twinkle
        starMat.opacity = 0.5 + Math.sin(elapsed) * 0.15;

        if (controls) {
            controls.update();
        } else {
            // Simple auto-rotate fallback
            const rotSpeed = 0.0004;
            camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), rotSpeed);
            camera.lookAt(5, 5, 5);
        }

        renderer.render(scene, camera);
    }
    animate();

    // ── Raycasting for hover ─────────────────────────────────
    function onMouseMove(e) {
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(meshes);

        if (intersects.length > 0) {
            const hit = intersects[0].object;
            if (hoveredMesh !== hit) {
                // Restore previous
                if (hoveredMesh) {
                    hoveredMesh.scale.set(1, 1, 1);
                }
                hoveredMesh = hit;
                hoveredMesh.scale.set(1.4, 1.4, 1.4);
            }
            const nd = hit.userData.node;
            const badges = [];
            if (nd.is_cherished) badges.push('<span style="color:#ec4899;">♥ Cherished</span>');
            if (nd.is_anchor) badges.push('<span style="color:#10b981;">⚓ Anchor</span>');
            if (nd.is_flashbulb) badges.push('<span style="color:#ef4444;">⚡ Flashbulb</span>');
            tooltip.innerHTML =
                `<div style="margin-bottom:6px;font-weight:600;color:#e4e4e7;">${escapeHtml(nd.content)}</div>` +
                `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:4px;">` +
                `<span>😊 ${nd.emotion}</span>` +
                `<span>⭐ Imp: ${nd.importance}</span>` +
                `<span>✨ Viv: ${(nd.x || 0).toFixed(1)}</span>` +
                `</div>` +
                (badges.length ? `<div style="margin-top:4px;">${badges.join(' ')}</div>` : '') +
                (nd.entity ? `<div style="color:#60a5fa;margin-top:4px;">👤 ${escapeHtml(nd.entity)}</div>` : '');
            tooltip.style.display = 'block';
            tooltip.style.left = (e.clientX - rect.left + 16) + 'px';
            tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
            renderer.domElement.style.cursor = 'pointer';
        } else {
            if (hoveredMesh) {
                hoveredMesh.scale.set(1, 1, 1);
                hoveredMesh = null;
            }
            tooltip.style.display = 'none';
            renderer.domElement.style.cursor = 'grab';
        }
    }
    renderer.domElement.addEventListener('mousemove', onMouseMove);

    // ── Manual rotation fallback if no OrbitControls ──────────
    if (!controls) {
        let isDragging = false;
        let prevX = 0, prevY = 0;
        let doRotate = true;

        renderer.domElement.addEventListener('mousedown', (e) => {
            isDragging = true;
            doRotate = false;
            prevX = e.clientX;
            prevY = e.clientY;
        });
        renderer.domElement.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const deltaX = e.clientX - prevX;
                camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), deltaX * 0.005);
                camera.lookAt(5, 5, 5);
                prevX = e.clientX;
                prevY = e.clientY;
            }
        });
        renderer.domElement.addEventListener('mouseup', () => {
            isDragging = false;
            setTimeout(() => { doRotate = true; }, 2000);
        });

        // Scroll zoom
        renderer.domElement.addEventListener('wheel', (e) => {
            e.preventDefault();
            const dir = new THREE.Vector3();
            camera.getWorldDirection(dir);
            camera.position.addScaledVector(dir, e.deltaY * -0.01);
        }, { passive: false });
    }

    // ── Resize ───────────────────────────────────────────────
    function onResize() {
        const w = container.offsetWidth;
        const h = container.offsetHeight || 600;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
    }
    window.addEventListener('resize', onResize);

    // ── Cleanup function ─────────────────────────────────────
    _landscape3dCleanup = () => {
        if (animId) cancelAnimationFrame(animId);
        renderer.domElement.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('resize', onResize);
        renderer.dispose();
    };
}

// ═══════════════════════════════════════════════════════════════
// 3. MOOD TIMELINE
// ═══════════════════════════════════════════════════════════════

let moodChartInstance = null;

async function loadMoodTimeline() {
    try {
        const res = await App.api('/visualization/mood-history');
        renderMoodTimeline(res.history || []);
    } catch (err) {
        console.error('Failed to load mood timeline:', err);
    }
}

function renderMoodTimeline(history) {
    const ctx = document.getElementById('mood-chart');
    if (!ctx) return;

    if (moodChartInstance) moodChartInstance.destroy();

    const labels = history.map((_, i) => `Turn ${i + 1}`);
    const pleasantness = history.map(h => (h.pad?.[0] || 0) + 5);
    const arousal = history.map(h => (h.pad?.[1] || 0) + 5);
    const dominance = history.map(h => (h.pad?.[2] || 0) + 5);

    moodChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '😊 Pleasantness',
                    data: pleasantness,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 3,
                },
                {
                    label: '⚡ Arousal',
                    data: arousal,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 3,
                },
                {
                    label: '👑 Dominance',
                    data: dominance,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#e4e4e7', font: { size: 12 } },
                    position: 'top',
                },
                filler: { propagate: true },
            },
            scales: {
                y: {
                    min: 0, max: 10,
                    ticks: { color: '#a1a1aa' },
                    grid: { color: 'rgba(100, 100, 150, 0.1)' },
                },
                x: {
                    ticks: { color: '#a1a1aa' },
                    grid: { color: 'rgba(100, 100, 150, 0.1)' },
                },
            },
        },
    });
}

// ═══════════════════════════════════════════════════════════════
// 4. CHERISHED MEMORIES WALL
// ═══════════════════════════════════════════════════════════════

async function loadCherishedWall() {
    try {
        const res = await App.api('/visualization/cherished');
        renderCherishedWall(res.memories || []);
    } catch (err) {
        console.error('Failed to load cherished:', err);
    }
}

function renderCherishedWall(memories) {
    const wall = document.getElementById('cherished-wall');
    if (!wall) return;
    
    wall.innerHTML = '';

    if (memories.length === 0) {
        wall.innerHTML = '<p class="text-muted" style="grid-column: 1/-1; text-align: center; padding: 40px;">No cherished memories yet. Keep building precious moments!</p>';
        return;
    }

    memories.forEach(mem => {
        const card = document.createElement('div');
        card.className = 'cherished-card';
        card.innerHTML = `
            <div class="cherished-card-title">${escapeHtml(mem.content.substring(0, 60))}</div>
            <div class="cherished-card-content">${escapeHtml(mem.content.substring(0, 150))}...</div>
            <div class="cherished-card-meta">
                <div class="cherished-card-stat">💎 Vividness: ${mem.vividness.toFixed(1)}/10</div>
                <div class="cherished-card-stat">⭐ Importance: ${mem.importance}/10</div>
                <div class="cherished-card-stat">😊 ${mem.emotion}</div>
            </div>
        `;
        wall.appendChild(card);
    });
}

// ═══════════════════════════════════════════════════════════════
// 5. NEUROCHEMISTRY OVER TIME
// ═══════════════════════════════════════════════════════════════

let chemistryChartInstance = null;

async function loadChemistryTimeline() {
    try {
        const res = await App.api('/visualization/chemistry-history');
        renderChemistryTimeline(res.history || []);
    } catch (err) {
        console.error('Failed to load chemistry:', err);
    }
}

function renderChemistryTimeline(history) {
    const ctx = document.getElementById('chemistry-chart');
    if (!ctx) return;

    if (chemistryChartInstance) chemistryChartInstance.destroy();

    const labels = history.map((_, i) => `Turn ${i + 1}`);
    const nts = ['dopamine', 'serotonin', 'oxytocin', 'norepinephrine', 'cortisol'];
    const colors = ['#f59e0b', '#06b6d4', '#ec4899', '#3b82f6', '#ef4444'];

    const datasets = nts.map((nt, idx) => ({
        label: nt.charAt(0).toUpperCase() + nt.slice(1),
        data: history.map(h => (h.levels?.[nt] || 0) * 100),
        borderColor: colors[idx],
        backgroundColor: `rgba(${hexToRgb(colors[idx]).r}, ${hexToRgb(colors[idx]).g}, ${hexToRgb(colors[idx]).b}, 0.1)`,
        tension: 0.3,
        fill: true,
        pointRadius: 2,
    }));

    chemistryChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { 
                    labels: { color: '#e4e4e7', font: { size: 12 } },
                    position: 'top',
                },
            },
            scales: {
                y: {
                    min: 0, max: 100,
                    ticks: { color: '#a1a1aa' },
                    grid: { color: 'rgba(100, 100, 150, 0.1)' },
                },
                x: {
                    ticks: { color: '#a1a1aa' },
                    grid: { color: 'rgba(100, 100, 150, 0.1)' },
                },
            },
        },
    });
}

// ─────────────────────────────────────────────────────────────

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
    } : { r: 124, g: 58, b: 237 };
}
