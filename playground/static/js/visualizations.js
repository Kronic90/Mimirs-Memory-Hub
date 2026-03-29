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
// 2. MEMORY LANDSCAPE 3D SCATTERPLOT
// ═══════════════════════════════════════════════════════════════

async function loadLandscape3D() {
    try {
        const res = await App.api('/api/visualization/landscape');
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

    // Clear previous instance
    const existingCanvas = container.querySelector('canvas');
    if (existingCanvas) existingCanvas.remove();

    const width = container.offsetWidth;
    const height = container.offsetHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x09090b);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.set(15, 12, 15);
    camera.lookAt(5, 5, 5);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const pointLight = new THREE.PointLight(0xffffff, 0.4);
    pointLight.position.set(10, 10, 10);
    scene.add(pointLight);

    // Grid
    const gridHelper = new THREE.GridHelper(10, 10, 0x333333, 0x222222);
    scene.add(gridHelper);
    const axesHelper = new THREE.AxesHelper(5);
    scene.add(axesHelper);

    // Color map
    const colorMap = {
        episodic: 0x7c3aed, social: 0x3b82f6, huginn: 0xf59e0b,
        volva: 0x8b5cf6, conversation: 0x6366f1,
    };

    // Add memory nodes
    (data.nodes || []).forEach(node => {
        const color = colorMap[node.color] || 0x7c3aed;
        const size = 0.1 + (Math.min(node.size / 10, 1)) * 0.2;
        const geometry = new THREE.SphereGeometry(size, 16, 16);
        const material = new THREE.MeshPhongMaterial({
            color, emissive: color, emissiveIntensity: 0.3,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(node.x, node.y, node.z);
        scene.add(mesh);
    });

    // Animation
    let doRotate = true;
    function animate() {
        requestAnimationFrame(animate);
        if (doRotate) {
            scene.rotation.x += 0.0002;
            scene.rotation.y += 0.0005;
        }
        renderer.render(scene, camera);
    }
    animate();

    // Mouse controls
    let isDragging = false;
    let prevX = 0, prevY = 0;

    renderer.domElement.addEventListener('mousedown', (e) => {
        isDragging = true;
        doRotate = false;
        prevX = e.clientX;
        prevY = e.clientY;
    });

    renderer.domElement.addEventListener('mousemove', (e) => {
        if (isDragging) {
            const deltaX = e.clientX - prevX;
            const deltaY = e.clientY - prevY;
            camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), deltaX * 0.005);
            prevX = e.clientX;
            prevY = e.clientY;
        }
    });

    renderer.domElement.addEventListener('mouseup', () => {
        isDragging = false;
        doRotate = true;
    });

    // Handle resize
    window.addEventListener('resize', () => {
        const newWidth = container.offsetWidth;
        const newHeight = container.offsetHeight;
        camera.aspect = newWidth / newHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(newWidth, newHeight);
    });
}

// ═══════════════════════════════════════════════════════════════
// 3. MOOD TIMELINE
// ═══════════════════════════════════════════════════════════════

let moodChartInstance = null;

async function loadMoodTimeline() {
    try {
        const res = await App.api('/api/visualization/mood-history');
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
        const res = await App.api('/api/visualization/cherished');
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
        const res = await App.api('/api/visualization/chemistry-history');
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
    const nts = ['dopamine', 'serotonin', 'oxytocin', 'norepinephrine', 'endorphin'];
    const colors = ['#f59e0b', '#06b6d4', '#ec4899', '#3b82f6', '#10b981'];

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
                    min: 0, max: 200,
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
