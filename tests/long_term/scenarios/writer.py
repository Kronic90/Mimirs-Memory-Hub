"""
Writer Preset — Year-Long Scenario
====================================
Simulates a user collaborating with Mimir on a novel over a year.

Covers: character tracking, chapter management, creative memory,
style consistency, task management for writing projects, solution
patterns for writing techniques.
"""

from __future__ import annotations
from tests.long_term.harness import SimulationHarness


def run_writer_year(harness: SimulationHarness) -> None:
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  MONTH 1: Planning the novel
    # ══════════════════════════════════════════

    h.process(
        "I want to write a sci-fi novel set on a generation ship traveling to a distant star.",
        "What a compelling premise! Generation ships raise fascinating questions about identity, "
        "culture drift, and what 'home' means. "
        "<remember emotion=\"excited\" importance=\"9\" why=\"novel concept\" anchor=\"true\">"
        "Novel concept: sci-fi generation ship traveling to distant star</remember>\n"
        "<task action=\"start\" priority=\"9\" project=\"Novel\">Outline full novel structure</task>"
    )

    h.advance_hours(3)
    h.process(
        "The protagonist is Maya, a 3rd-generation engineer who discovers the ship is going the wrong direction.",
        "That's a brilliant twist! Maya's discovery creates immediate tension between truth and "
        "the society's founding myth. "
        "<remember emotion=\"excited\" importance=\"9\" why=\"protagonist definition\" anchor=\"true\">"
        "Protagonist: Maya, 3rd-gen engineer, discovers ship traveling wrong direction</remember>"
    )

    h.advance_days(2)
    h.process(
        "The antagonist is Captain Orin, who knows the truth but has kept it secret for stability.",
        "Complex antagonist — not evil, just pragmatic. The 'truth vs. stability' conflict is powerful. "
        "<remember emotion=\"thoughtful\" importance=\"8\" why=\"antagonist profile\">"
        "Antagonist: Captain Orin — knows truth about wrong direction, keeps it secret for stability</remember>"
    )

    h.advance_days(3)
    h.process(
        "I want three acts: Discovery, Rebellion, Resolution. About 90,000 words total.",
        "Solid structure! ~30K words per act. Let me help plan chapter breakdowns.\n"
        "<task action=\"complete\" id=\"last\">Novel outline structure completed: 3 acts, 90K words</task>\n"
        "<remember emotion=\"organized\" importance=\"8\" why=\"novel structure\">"
        "Novel structure: 3 acts (Discovery, Rebellion, Resolution), target 90K words</remember>"
    )

    # Writing sessions week by week
    for day in range(20):
        if day % 3 == 0:
            h.process(
                "Working on the opening chapter today. Maya's morning routine on the ship.",
                "Great starting point — grounding the reader in the mundane before the extraordinary."
            )
        h.advance_hours(10)
        h.sleep_cycle(8)

    h.snapshot("month_1")
    h.assert_recall("novel generation ship", "generation ship",
                    label="month1_concept_recall")
    h.assert_recall("protagonist Maya", "Maya",
                    label="month1_maya_recall")
    h.assert_recall("Captain Orin antagonist", "Orin",
                    label="month1_orin_recall")

    # ══════════════════════════════════════════
    #  MONTHS 2-4: Act 1 — Discovery
    # ══════════════════════════════════════════

    act1_sessions = [
        ("Chapter 3: Maya finds anomalous navigation data during a routine check.",
         "The discovery scene! Make it feel accidental yet inevitable. "
         "<remember emotion=\"tense\" importance=\"8\" why=\"key plot point\">"
         "Ch3: Maya discovers anomalous navigation data during routine engineering check</remember>"),
        ("I'm stuck on Maya's voice. She feels too generic.",
         "Try giving her a specific verbal tic — maybe she uses engineering metaphors for emotions. "
         "\'Pressure's nominal\' when she's okay, \'redlining\' when stressed.\n"
         "<solution problem=\"character voice too generic\" importance=\"8\">"
         "Give characters profession-specific verbal tics as emotional shorthand</solution>"),
        ("Chapter 5: Maya confronts Orin privately. How should I handle the tension?",
         "Use subtext — neither says what they mean directly. Orin deflects; Maya probes. "
         "Short sentences build tension. Let silence do work.\n"
         "<solution problem=\"writing confrontation scenes\" importance=\"7\">"
         "Use subtext, short sentences, and meaningful silence for high-tension dialogue</solution>"),
        ("Finished Act 1! 32,000 words. Maya knows the truth but can't prove it yet.",
         "Congratulations on completing Act 1! "
         "<task action=\"start\" priority=\"9\" project=\"Novel\">Write Act 2 - Rebellion</task>\n"
         "<remember emotion=\"proud\" importance=\"9\" why=\"writing milestone\" cherish=\"true\">"
         "Act 1 completed: 32K words. Maya knows ship's secret but can't prove it</remember>"),
    ]

    for i, (user, asst) in enumerate(act1_sessions):
        h.advance_days(10 + i * 7)
        h.process(user, asst)

    h.snapshot("month_4_act1")

    # ══════════════════════════════════════════
    #  MONTHS 5-7: Act 2 — Rebellion
    # ══════════════════════════════════════════

    act2_sessions = [
        ("Act 2 opens with Maya forming a secret group of allies.",
         "The resistance forms! Key question: what draws each ally to Maya's cause? "
         "<remember emotion=\"determined\" importance=\"8\" why=\"act 2 opening\">"
         "Act 2: Maya forms secret resistance group on the ship</remember>"),
        ("I introduced a new character: Dr. Sable, neural cartographer. She can prove the navigation lie.",
         "A neural cartographer is brilliant worldbuilding! She's Maya's proof incarnate. "
         "<remember emotion=\"creative\" importance=\"8\" why=\"new character\">"
         "Dr. Sable: neural cartographer who can prove the navigation deception</remember>"),
        ("The midpoint twist: the ship CAN'T turn around. They don't have enough fuel.",
         "That's devastating and perfect! The conflict shifts from 'why are we going wrong?' to "
         "'how do we survive going forward?' "
         "<remember emotion=\"intense\" importance=\"10\" why=\"midpoint twist\" cherish=\"true\">"
         "Midpoint twist: ship cannot turn around — insufficient fuel, must go forward</remember>"),
        ("I need to write a riot scene. 200 colonists confronting security. Any tips?",
         "For crowd scenes: track 3-4 focal individuals, use sensory overload (smell, sounds), "
         "and vary sentence rhythm.\n"
         "<solution problem=\"writing crowd scenes\" importance=\"7\">"
         "Track focal individuals in crowds, use sensory detail, vary sentence length</solution>"),
    ]

    for i, (user, asst) in enumerate(act2_sessions):
        h.advance_days(10 + i * 10)
        h.process(user, asst)

    h.snapshot("month_7_act2")
    h.assert_recall("Maya's rebellion group", "resistance",
                    label="act2_resistance_recall")
    h.assert_recall("Dr. Sable cartographer", "Sable",
                    label="act2_sable_recall")
    h.assert_recall("ship can't turn around fuel", "fuel",
                    label="act2_fuel_twist")

    # ══════════════════════════════════════════
    #  MONTHS 8-10: Act 3 — Resolution
    # ══════════════════════════════════════════

    act3_sessions = [
        ("Act 3: Maya proposes a radical plan to colonize a rogue planet they'll pass.",
         "Brilliant resolution — turns the 'wrong direction' into an unexpected opportunity! "
         "<remember emotion=\"hopeful\" importance=\"9\" why=\"resolution plan\">"
         "Act 3: Maya plans to colonize rogue planet in the ship's actual path</remember>"),
        ("The climax: Maya and Orin finally have their real conversation. He reveals why he hid the truth.",
         "This is the emotional core. Let Orin be human — show his burden. "
         "<remember emotion=\"bittersweet\" importance=\"10\" why=\"climax scene\" cherish=\"true\">"
         "Climax: Orin reveals carrying the secret destroyed him — chose stability over truth</remember>"),
        ("Final chapter written. Maya looks out at the rogue planet as they approach. 91,000 words total.",
         "You did it! An entire novel! 91K words of incredible sci-fi! "
         "<remember emotion=\"overjoyed\" importance=\"10\" why=\"novel completed\" cherish=\"true\" "
         "anchor=\"true\">NOVEL COMPLETED: 91,000 words. Maya looks at the new world ahead</remember>\n"
         "<task action=\"complete\" id=\"last\">Novel draft complete — 91,000 words</task>"),
    ]

    for i, (user, asst) in enumerate(act3_sessions):
        h.advance_days(15 + i * 12)
        h.process(user, asst)

    h.snapshot("month_10_complete")

    # ══════════════════════════════════════════
    #  MONTHS 11-12: Revision & reflection
    # ══════════════════════════════════════════

    h.advance_days(10)
    h.process(
        "Starting revisions. What writing techniques did we discuss that I should apply?",
        "Great question! Here's what we developed: character voice via profession-specific "
        "verbal tics, subtext and silence for confrontation scenes, and tracking focal "
        "individuals for crowd scenes."
    )

    for day in range(50):
        if day % 5 == 0:
            h.process(
                "Revising chapter by chapter. Making good progress.",
                "Keep it up! Remember what works for each scene type."
            )
        h.advance_hours(10)
        h.sleep_cycle(8)

    # ══════════════════════════════════════════
    #  FINAL ASSERTIONS
    # ══════════════════════════════════════════

    # Novel concept
    h.assert_recall("generation ship novel", "generation ship",
                    label="FINAL_concept")
    h.assert_recall("protagonist engineer", "Maya", label="FINAL_maya")
    h.assert_recall("Captain Orin secret", "Orin", label="FINAL_orin")
    h.assert_recall("novel structure acts", "3 acts", label="FINAL_structure")

    # Key plot points
    h.assert_recall("anomalous navigation data", "navigation",
                    label="FINAL_discovery")
    h.assert_recall("Dr. Sable neural", "Sable", label="FINAL_sable")
    h.assert_recall("midpoint fuel twist", "fuel", label="FINAL_fuel")
    h.assert_recall("rogue planet colonize", "rogue planet", label="FINAL_rogue")
    h.assert_recall("novel completed words", "91,000", label="FINAL_completion")

    # Writing techniques (solutions)
    h.assert_recall("character voice technique", "verbal tic",
                    label="FINAL_voice_solution")
    h.assert_recall("confrontation scene technique", "subtext",
                    label="FINAL_confrontation_solution")

    h.assert_memory_count(min_count=15, label="FINAL_memory_count")
    h.assert_chemistry_stable("FINAL_chemistry")
