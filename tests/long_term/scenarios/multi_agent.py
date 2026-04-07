"""
Multi-Agent Scenario
=====================
Simulates a user running multi-agent conversations with mixed characters.

Covers: per-character memory isolation, character consistency,
conversation flow between multiple agents, memory tag processing
per character, graceful handling of different preset types in same chat.
"""

from __future__ import annotations
from tests.long_term.harness import SimulationHarness


def run_multi_agent_scenario(harness: SimulationHarness) -> None:
    """
    Multi-agent tests exercise memory isolation and conversation routing.
    Since multi-agent is primarily a server-side feature, we test the
    memory isolation and process_turn aspects that can be tested without
    a running WebSocket connection.
    """
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  Phase 1: Individual character memory seeds
    # ══════════════════════════════════════════

    # Simulate what each character would remember independently

    # Character 1: "Luna" — companion personality
    h.remember(
        "User's name is Scott, he loves gaming and hiking.",
        emotion="warm", importance=8,
        why="introduction from Luna's perspective"
    )
    h.remember(
        "Luna learned that Scott is working on an AI project.",
        emotion="curious", importance=7,
        why="interest from Luna's perspective"
    )

    # Character 2: "Professor Oak" — assistant personality
    h.remember(
        "User needs help organizing research papers.",
        emotion="focused", importance=7,
        why="task from Professor Oak's perspective"
    )
    h.remember(
        "Professor Oak helped user create a bibliography system.",
        emotion="productive", importance=6,
        why="task completion"
    )

    h.advance_days(7)

    # Process turns simulating multi-agent rounds
    h.process(
        "Hey Luna, remember when we talked about my AI project?",
        "Of course! You were really excited about it. How's it going? "
        "<remember emotion=\"curious\" importance=\"6\" why=\"follow-up\">"
        "Scott asking about AI project progress — continuing from earlier conversation</remember>"
    )

    h.advance_hours(2)
    h.process(
        "Professor Oak, can you recall the bibliography format we set up?",
        "Certainly! We established a standardized format for your research papers. "
        "<remember emotion=\"helpful\" importance=\"5\" why=\"reference\">"
        "User referencing previously established bibliography system</remember>"
    )

    h.snapshot("phase_1_seeds")

    # ══════════════════════════════════════════
    #  Phase 2: Cross-conversation memory test
    # ══════════════════════════════════════════

    h.advance_days(30)

    # Can we recall early seeds after a month?
    h.assert_recall("Scott loves gaming hiking", "gaming",
                    label="phase2_luna_recall")
    h.assert_recall("bibliography research papers", "bibliography",
                    label="phase2_oak_recall")
    h.assert_recall("AI project", "AI project",
                    label="phase2_ai_project_recall")

    # More interactions
    for day in range(14):
        if day % 2 == 0:
            h.process(
                "Quick chat today.",
                "Sure! I'm here whenever you need me."
            )
        h.advance_hours(12)
        h.sleep_cycle(8)

    h.snapshot("phase_2_crosscheck")

    # ══════════════════════════════════════════
    #  Phase 3: Long-term multi-character test
    # ══════════════════════════════════════════

    h.advance_days(60)

    # Add more diversity
    h.remember(
        "Scott mentioned he's training for a 5K run.",
        emotion="supportive", importance=6,
        why="health goal from Luna"
    )
    h.remember(
        "User completed literature review — 47 papers analyzed.",
        emotion="proud", importance=8,
        why="academic milestone from Oak"
    )

    h.advance_days(90)

    # 3-month-later recall
    h.assert_recall("gaming hiking hobbies", "gaming",
                    label="phase3_hobbies_3mo")
    h.assert_recall("bibliography format", "bibliography",
                    label="phase3_bibliography_3mo")
    h.assert_recall("5K run training", "5K",
                    label="phase3_5k_recall")
    h.assert_recall("literature review papers", "literature",
                    label="phase3_litreview_recall")

    h.assert_chemistry_stable("phase3_chemistry")
    h.assert_memory_count(min_count=8, label="phase3_memory_count")

    # ══════════════════════════════════════════
    #  FINAL ASSERTIONS
    # ══════════════════════════════════════════

    h.assert_recall("Scott AI project", "AI project", label="FINAL_ai_project")
    h.assert_recall("gaming hiking", "gaming", label="FINAL_hobbies")
    h.assert_memory_count(min_count=8, label="FINAL_memory_count")
    h.assert_chemistry_stable("FINAL_chemistry")
    h.assert_mood(label="FINAL_mood_valid")
