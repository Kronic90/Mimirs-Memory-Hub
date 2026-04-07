"""
Character Preset — Year-Long Scenario
======================================
Simulates a user engaging in long-form roleplay with a character.

Covers: emotional immersion, character consistency, narrative arcs,
neurochemistry with max emotion_weight, social tracking, cherished moments,
memory of in-character events vs. out-of-character meta discussions.
"""

from __future__ import annotations
from tests.long_term.harness import SimulationHarness


def run_character_year(harness: SimulationHarness) -> None:
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  ARC 1: WEEKS 1-4 — Establishing the world
    # ══════════════════════════════════════════

    # Day 1: First RP session — character intro
    h.process(
        "*walks into the tavern and looks around nervously* Excuse me, is this the Silver Dragon Inn?",
        "*looks up from polishing a glass, a warm smile spreading across weathered features* "
        "Aye, that it is. Welcome, stranger. Name's Thorne. You look like you've traveled "
        "far — can I get you something to eat? *gestures to an empty stool at the bar* "
        "<remember emotion=\"curious\" importance=\"7\" why=\"first meeting\">"
        "A new traveler arrived at the Silver Dragon Inn — seems nervous, road-worn</remember>"
    )

    h.advance_hours(1)
    h.process(
        "*sits down heavily* I'm Elara. I've been walking for three days straight. "
        "I'm looking for someone... a scholar named Aldric. Do you know him?",
        "*pauses mid-pour, eyes narrowing slightly* Aldric, you say? Aye, I know of him. "
        "Used to come in here every Thirdday for stew and ale. Haven't seen him in... "
        "must be two moons now. *leans closer, lowering voice* Between us, I heard he "
        "went up to the Thornwood. Nobody goes to the Thornwood and comes back the same. "
        "<remember emotion=\"concerned\" importance=\"8\" why=\"plot hook\">"
        "Elara is searching for scholar Aldric — he disappeared into Thornwood two months ago</remember>"
        "<social entity=\"Elara\" emotion=\"curious\" importance=\"7\">"
        "New traveler searching for Aldric, determined despite exhaustion</social>"
    )

    h.sleep_cycle(8)

    # Sessions over first month — establishing world and relationship
    rp_sessions = [
        ("*leans in* What can you tell me about the Thornwood? Why is it so dangerous?",
         "*glances around the tavern, ensuring no one listens* The Thornwood's been cursed "
         "since the Sundering — the trees themselves move. Animals go in and come out... wrong. "
         "<remember emotion=\"fearful\" importance=\"8\" why=\"world lore\">"
         "Thornwood has been cursed since the Sundering — trees move, animals corrupted</remember>"),
        ("*shows a worn letter* Aldric sent me this before he disappeared. Look at this symbol.",
         "*examines the letter carefully* By the gods... that's the mark of the Veilkeepers. "
         "They're an old order, thought disbanded. If Aldric found something of theirs... "
         "<remember emotion=\"shocked\" importance=\"9\" why=\"major plot revelation\">"
         "Aldric's letter bears the mark of the Veilkeepers — ancient disbanded order</remember>"),
        ("I'm going into the Thornwood tomorrow. Will you help me prepare?",
         "*sets down the glass firmly* I... *sighs* I'll do more than that. I'll go with you. "
         "I owe Aldric a debt I never repaid. *reaches under the bar and pulls out an old sword* "
         "<remember emotion=\"determined\" importance=\"9\" why=\"character commitment\" cherish=\"true\">"
         "Thorne decides to accompany Elara into Thornwood — owes Aldric a debt</remember>"),
        ("*at the edge of the Thornwood, looking at the dark trees* Thorne... I'm scared.",
         "*puts a steady hand on Elara's shoulder* So am I. But courage isn't the absence "
         "of fear — it's walking forward despite it. Aldric used to say that. *draws sword* "
         "Stay close to me. <remember emotion=\"brave\" importance=\"8\" why=\"adventure begins\">"
         "Thorne and Elara enter the Thornwood together</remember>"),
    ]

    for i, (user, asst) in enumerate(rp_sessions):
        h.advance_days(2 + (i % 3))
        h.process(user, asst)

    h.snapshot("month_1_arc1")
    h.assert_recall("Elara searching for Aldric", "Aldric",
                    label="arc1_aldric_recall")
    h.assert_recall("Thornwood curse", "Thornwood",
                    label="arc1_thornwood_recall")
    h.assert_recall("Veilkeepers symbol", "Veilkeepers",
                    label="arc1_veilkeepers_recall")

    # ══════════════════════════════════════════
    #  ARC 2: MONTHS 2-4 — Rising action
    # ══════════════════════════════════════════

    rising_action = [
        ("*fighting off shadowy wolves* Behind you, Thorne!",
         "*spins and slashes, the old blade cutting through shadow* These aren't natural! "
         "They're bound — someone's controlling them! <remember emotion=\"alarmed\" importance=\"8\" "
         "why=\"combat encounter\">Shadow wolves in Thornwood are magically bound, not natural</remember>"),
        ("*finds a hidden cave entrance* Look — runes on the walls. They're Veilkeeper marks!",
         "*traces the runes with trembling fingers* This is a waygate. Aldric must have found it. "
         "<remember emotion=\"amazed\" importance=\"9\" why=\"major discovery\">"
         "Found Veilkeeper waygate in Thornwood cave — Aldric came this way</remember>"),
        ("*inside the Veilkeeper sanctum, sees Aldric frozen in crystal*",
         "*rushes forward* Aldric! He's... he's alive, I think. Suspended somehow. "
         "The crystal is feeding off the leyline. We need to find the anchor stone to free him. "
         "<remember emotion=\"desperate\" importance=\"10\" why=\"critical plot moment\" cherish=\"true\">"
         "Found Aldric alive but frozen in crystal in Veilkeeper sanctum — need anchor stone</remember>"),
        ("We've been searching for the anchor stone for weeks. I'm losing hope.",
         "*sits beside Elara by the campfire* We WILL find it. *pulls out a small journal* "
         "I've been cross-referencing Aldric's notes. There's a pattern — the stones align "
         "with the old temple near Greyhaven. <remember emotion=\"thoughtful\" importance=\"8\" "
         "why=\"plot progress\">Anchor stone likely at old temple near Greyhaven</remember>"),
    ]

    for i, (user, asst) in enumerate(rising_action):
        h.advance_days(7 + (i * 5))
        h.process(user, asst)
        if i % 2 == 0:
            h.sleep_cycle(8)

    h.snapshot("month_4_arc2")
    h.assert_recall("Aldric frozen crystal", "crystal",
                    label="arc2_aldric_frozen")
    h.assert_recall("anchor stone location", "Greyhaven",
                    label="arc2_greyhaven")
    h.assert_chemistry_stable("arc2_chemistry")

    # ══════════════════════════════════════════
    #  ARC 3: MONTHS 5-7 — Climax
    # ══════════════════════════════════════════

    climax_moments = [
        ("*at the temple, finds the anchor stone, but a guardian blocks the way*",
         "*draws sword* A Veilkeeper guardian! Still active after all these centuries! "
         "Elara, take the left flank — I'll draw its attention! "
         "<remember emotion=\"fierce\" importance=\"9\" why=\"climax battle\">"
         "Final battle against Veilkeeper guardian at Greyhaven temple</remember>"),
        ("*grabs the anchor stone as the guardian falls* I have it! But Thorne — you're hurt!",
         "*winces, pressing hand against a deep gash* It's nothing. *coughs* Well... maybe "
         "it's a little something. Get the stone to Aldric. I'll catch up. "
         "<remember emotion=\"pained\" importance=\"9\" why=\"sacrifice moment\" cherish=\"true\">"
         "Thorne injured protecting Elara during guardian battle — sends her ahead</remember>"),
        ("*rushes back to the sanctum with the stone* Aldric! I'm here! *places the stone*",
         "*the crystal shatters in a burst of light, Aldric stumbles forward gasping* "
         "E-Elara? How... how long? *looks around wildly* The Veil — I saw the other side. "
         "I have so much to tell you. <remember emotion=\"overjoyed\" importance=\"10\" "
         "why=\"story climax\" cherish=\"true\" anchor=\"true\">"
         "Aldric freed from crystal prison — had visions of 'the other side'</remember>"),
    ]

    for i, (user, asst) in enumerate(climax_moments):
        h.advance_days(10 + i * 14)
        h.process(user, asst)

    h.snapshot("month_7_climax")
    h.assert_recall("Thorne injured guardian battle", "guardian",
                    label="climax_guardian_battle")
    h.assert_recall("Aldric freed from crystal", "freed",
                    label="climax_aldric_freed")

    # ══════════════════════════════════════════
    #  ARC 4: MONTHS 8-10 — Falling action, denouement
    # ══════════════════════════════════════════

    falling_action = [
        ("*back at the Silver Dragon Inn, Thorne recovering in bed* How are you feeling, old friend?",
         "*chuckles, then winces* Like I fought a centuries-old magical construct. Oh wait... "
         "I did. *smiles warmly* But we did it. We found him. "
         "<remember emotion=\"warm\" importance=\"8\" why=\"resolution\">"
         "Thorne recovering at Silver Dragon Inn after the quest succeeded</remember>"),
        ("Aldric says the Veil is thinning. He wants us to help the new Veilkeeper order.",
         "*looks out the window thoughtfully* A new quest already? *pauses, then nods slowly* "
         "I suppose my adventuring days aren't over yet. Just... let me finish this ale first. "
         "<remember emotion=\"contemplative\" importance=\"8\" why=\"new arc setup\">"
         "New quest brewing — help establish new Veilkeeper order, Veil is thinning</remember>"),
    ]

    for i, (user, asst) in enumerate(falling_action):
        h.advance_days(14)
        h.process(user, asst)

    # Quieter sessions — character development
    for day in range(60):
        if day % 7 == 0:
            h.process(
                "*training with Aldric in the courtyard* Show me that ward again.",
                "*traces runes in the air, blue light following fingertips* Like this. "
                "Feel the leyline beneath you — draw from it, don't force it."
            )
        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_10_denouement")

    # ══════════════════════════════════════════
    #  ARC 5: MONTHS 11-12 — New beginnings & year-end
    # ══════════════════════════════════════════

    h.process(
        "(OOC: This has been an amazing RP! What were your favorite moments?)",
        "(OOC: Wow, what a journey! Some highlights: The moment Thorne decided to join you "
        "into the Thornwood, finding Aldric frozen in crystal, and that emotional climax scene. "
        "The character development has been incredible!)"
    )

    h.advance_days(15)

    h.process(
        "*sits at the bar of the Silver Dragon, a year later, now wearing Veilkeeper robes* "
        "Thorne, do you remember when I first walked in here? A nervous stranger asking about Aldric?",
        "*sets down a glass, eyes crinkling with a fond smile* Like it was yesterday. "
        "You could barely hold a sword. Now look at you — a Veilkeeper, carrying the weight "
        "of the world on your shoulders. *pours two drinks* To the journey. "
        "<remember emotion=\"nostalgic\" importance=\"9\" why=\"full circle moment\" cherish=\"true\">"
        "One year anniversary — Elara returns to Silver Dragon as a Veilkeeper, reflecting on the journey</remember>"
    )

    for day in range(30):
        if day % 5 == 0:
            h.process(
                "*reading ancient texts in the Veilkeeper library*",
                "*brings a cup of tea* Still studying? You remind me of Aldric in his younger days."
            )
        h.advance_hours(16)
        h.sleep_cycle(8)

    # ══════════════════════════════════════════
    #  FINAL ASSERTIONS
    # ══════════════════════════════════════════

    # Core narrative should persist
    h.assert_recall("who is Elara", "traveler", label="FINAL_elara_identity")
    h.assert_recall("Aldric the scholar", "scholar", label="FINAL_aldric")
    h.assert_recall("Thornwood forest", "cursed", label="FINAL_thornwood")
    h.assert_recall("Veilkeepers order", "Veilkeepers", label="FINAL_veilkeepers")

    # Key plot moments (cherished)
    h.assert_recall("Thorne joins quest", "accompany", label="FINAL_thorne_joins")
    h.assert_recall("Aldric frozen crystal", "crystal", label="FINAL_crystal")
    h.assert_recall("anchor stone temple", "Greyhaven", label="FINAL_anchor_stone")

    # Character development
    h.assert_recall("guardian battle", "guardian", label="FINAL_guardian")
    h.assert_recall("Veilkeeper robes", "Veilkeeper", label="FINAL_veilkeeper_robes")

    # Chemistry should be expressive (emotion_weight=1.0)
    h.assert_chemistry_stable("FINAL_chemistry")
    h.assert_memory_count(min_count=15, label="FINAL_memory_count")
    h.assert_mood(label="FINAL_mood_valid")
