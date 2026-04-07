"""
Year-Long Simulation Orchestrator
===================================
Runs all preset-specific year-long scenarios and collects unified metrics.

Each scenario exercises 365 simulated days of usage for a specific preset,
testing memory recall, chemistry stability, and feature correctness
at multiple checkpoints throughout the year.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness, MetricsCollector

# Scenario imports
from tests.long_term.scenarios.companion import run_companion_year
from tests.long_term.scenarios.agent import run_agent_year
from tests.long_term.scenarios.character import run_character_year
from tests.long_term.scenarios.writer import run_writer_year
from tests.long_term.scenarios.assistant import run_assistant_year
from tests.long_term.scenarios.multi_agent import run_multi_agent_scenario


# ═══════════════════════════════════════════════════════════════
#  Individual year tests
# ═══════════════════════════════════════════════════════════════

def test_companion_year():
    """Full year test: Companion preset — daily emotional support."""
    with SimulationHarness("companion_year", preset_name="companion") as h:
        try:
            run_companion_year(h)
            h.metrics.record("scenario_completed", True, "Companion year finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


def test_agent_year():
    """Full year test: Agent preset — project management, solutions."""
    with SimulationHarness("agent_year", preset_name="agent") as h:
        try:
            run_agent_year(h)
            h.metrics.record("scenario_completed", True, "Agent year finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


def test_character_year():
    """Full year test: Character preset — roleplay, narrative arcs."""
    with SimulationHarness("character_year", preset_name="character") as h:
        try:
            run_character_year(h)
            h.metrics.record("scenario_completed", True, "Character year finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


def test_writer_year():
    """Full year test: Writer preset — novel collaboration."""
    with SimulationHarness("writer_year", preset_name="writer") as h:
        try:
            run_writer_year(h)
            h.metrics.record("scenario_completed", True, "Writer year finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


def test_assistant_year():
    """Full year test: Assistant preset — scheduling, task tracking."""
    with SimulationHarness("assistant_year", preset_name="assistant") as h:
        try:
            run_assistant_year(h)
            h.metrics.record("scenario_completed", True, "Assistant year finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


def test_multi_agent():
    """Multi-agent memory isolation test."""
    with SimulationHarness("multi_agent", preset_name="companion") as h:
        try:
            run_multi_agent_scenario(h)
            h.metrics.record("scenario_completed", True, "Multi-agent test finished")
        except Exception as e:
            h.metrics.record("scenario_completed", False,
                            f"Crashed: {e}\n{traceback.format_exc()}")
            h.metrics.errors.append(str(e))
        h.snapshot("final")
        return h.metrics


# ═══════════════════════════════════════════════════════════════
#  Collect all year tests
# ═══════════════════════════════════════════════════════════════

ALL_YEAR_TESTS = [
    ("Companion Year", test_companion_year),
    ("Agent Year", test_agent_year),
    ("Character Year", test_character_year),
    ("Writer Year", test_writer_year),
    ("Assistant Year", test_assistant_year),
    ("Multi-Agent Isolation", test_multi_agent),
]
