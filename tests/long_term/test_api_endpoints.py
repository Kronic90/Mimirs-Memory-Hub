"""
API Endpoint Tests
===================
Tests all REST API endpoints without a running server,
using FastAPI's TestClient for synchronous testing.

Covers: settings, memory APIs, characters, conversations,
TTS/STT status, presets, task management.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness, MetricsCollector


def _get_test_client():
    """Create a FastAPI TestClient without starting a server."""
    try:
        from fastapi.testclient import TestClient
        from playground.server import app
        return TestClient(app)
    except Exception as e:
        return None


def test_api_settings():
    """Test: GET/PUT /api/settings."""
    metrics = MetricsCollector("api_settings")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "Could not create TestClient")
        return metrics

    # GET settings
    r = client.get("/api/settings")
    metrics.record("get_settings_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("settings_has_backend",
                       "active_backend" in data,
                       f"Keys: {list(data.keys())[:10]}")

    return metrics


def test_api_presets():
    """Test: GET /api/presets."""
    metrics = MetricsCollector("api_presets")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/presets")
    metrics.record("get_presets_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("presets_is_dict", isinstance(data, dict),
                       f"Type: {type(data).__name__}")
        if isinstance(data, dict):
            expected = ["companion", "agent", "character", "writer", "assistant"]
            for name in expected:
                metrics.record(f"preset_{name}", name in data,
                               f"'{name}' in presets: {name in data}")

    return metrics


def test_api_memory_stats():
    """Test: GET /api/memory/stats."""
    metrics = MetricsCollector("api_memory_stats")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/stats")
    metrics.record("memory_stats_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("stats_has_total",
                       "total_reflections" in data,
                       f"Keys: {list(data.keys())[:10]}")

    return metrics


def test_api_memory_recall():
    """Test: POST /api/memory/recall."""
    metrics = MetricsCollector("api_memory_recall")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.post("/api/memory/recall", json={"query": "test query", "limit": 5})
    metrics.record("recall_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("recall_is_list",
                       isinstance(data, list),
                       f"Type: {type(data).__name__}")

    return metrics


def test_api_memory_remember():
    """Test: POST /api/memory/remember."""
    metrics = MetricsCollector("api_memory_remember")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.post("/api/memory/remember", json={
        "content": "API test memory",
        "emotion": "curious",
        "importance": 5,
    })
    metrics.record("remember_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_memory_browse():
    """Test: GET /api/memory/browse with pagination."""
    metrics = MetricsCollector("api_memory_browse")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/browse", params={"offset": 0, "limit": 10})
    metrics.record("browse_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_memory_mood():
    """Test: GET /api/memory/mood."""
    metrics = MetricsCollector("api_memory_mood")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/mood")
    metrics.record("mood_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("mood_has_label", "mood_label" in data,
                       f"Keys: {list(data.keys())[:8]}")

    return metrics


def test_api_memory_chemistry():
    """Test: GET /api/memory/chemistry."""
    metrics = MetricsCollector("api_memory_chemistry")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/chemistry")
    metrics.record("chemistry_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_memory_export():
    """Test: GET /api/memory/export."""
    metrics = MetricsCollector("api_memory_export")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/export")
    metrics.record("export_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_characters():
    """Test: GET /api/characters."""
    metrics = MetricsCollector("api_characters")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/characters")
    metrics.record("characters_status", r.status_code == 200,
                   f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        metrics.record("characters_is_collection",
                       isinstance(data, (list, dict)),
                       f"Type: {type(data).__name__}, count: {len(data) if isinstance(data, (list, dict)) else 'N/A'}")

    return metrics


def test_api_conversations():
    """Test: GET /api/conversations."""
    metrics = MetricsCollector("api_conversations")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/conversations")
    metrics.record("conversations_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_tts_status():
    """Test: GET /api/tts/status."""
    metrics = MetricsCollector("api_tts_status")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/tts/status")
    metrics.record("tts_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_stt_status():
    """Test: GET /api/stt/status."""
    metrics = MetricsCollector("api_stt_status")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/stt/status")
    metrics.record("stt_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_tasks():
    """Test: GET /api/tasks."""
    metrics = MetricsCollector("api_tasks")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/tasks")
    metrics.record("tasks_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_memory_emotions():
    """Test: GET /api/memory/emotions."""
    metrics = MetricsCollector("api_memory_emotions")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/emotions")
    metrics.record("emotions_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


def test_api_memory_filters():
    """Test: GET /api/memory/filters."""
    metrics = MetricsCollector("api_memory_filters")
    client = _get_test_client()
    if not client:
        metrics.record("client_ready", False, "No client")
        return metrics

    r = client.get("/api/memory/filters")
    metrics.record("filters_status", r.status_code == 200,
                   f"Status: {r.status_code}")

    return metrics


# ═══════════════════════════════════════════════════════════════
#  Collect all tests
# ═══════════════════════════════════════════════════════════════

ALL_API_TESTS = [
    ("Settings API", test_api_settings),
    ("Presets API", test_api_presets),
    ("Memory Stats API", test_api_memory_stats),
    ("Memory Recall API", test_api_memory_recall),
    ("Memory Remember API", test_api_memory_remember),
    ("Memory Browse API", test_api_memory_browse),
    ("Memory Mood API", test_api_memory_mood),
    ("Memory Chemistry API", test_api_memory_chemistry),
    ("Memory Export API", test_api_memory_export),
    ("Memory Emotions API", test_api_memory_emotions),
    ("Memory Filters API", test_api_memory_filters),
    ("Characters API", test_api_characters),
    ("Conversations API", test_api_conversations),
    ("TTS Status API", test_api_tts_status),
    ("STT Status API", test_api_stt_status),
    ("Tasks API", test_api_tasks),
]
