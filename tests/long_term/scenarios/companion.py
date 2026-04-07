"""
Companion Preset — Year-Long Scenario
======================================
Simulates a user who uses Mimir as a daily emotional companion.

Covers: daily check-ins, emotional range, relationship tracking,
memory recall over months, neurochemistry stability, consolidation,
cherished memory persistence, social impressions, deep conversations.
"""

from __future__ import annotations
from tests.long_term.harness import (
    SimulationHarness, DAILY_GREETINGS, EMOTIONAL_CONVERSATIONS,
    SOCIAL_INTERACTIONS, REMINDER_CONVERSATIONS, DEEP_PERSONAL_TOPICS,
    TOPIC_CONVERSATIONS, parse_tags,
)


def run_companion_year(harness: SimulationHarness) -> None:
    """Execute a full year of companion-preset usage."""
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  WEEK 1: Getting to know each other
    # ══════════════════════════════════════════
    _week1_intro(h)

    # ══════════════════════════════════════════
    #  WEEKS 2-4: Building rapport
    # ══════════════════════════════════════════
    _weeks2_4_rapport(h)

    # ══════════════════════════════════════════
    #  MONTH 2-3: Deeper conversations, life events
    # ══════════════════════════════════════════
    _months2_3_deepening(h)

    # ══════════════════════════════════════════
    #  MONTH 4-6: Regular usage patterns
    # ══════════════════════════════════════════
    _months4_6_regular(h)

    # ══════════════════════════════════════════
    #  MONTH 7-9: Stress period, emotional test
    # ══════════════════════════════════════════
    _months7_9_stress(h)

    # ══════════════════════════════════════════
    #  MONTH 10-12: Recovery, reflection, year-end
    # ══════════════════════════════════════════
    _months10_12_resolution(h)

    h.snapshot("year_end")


# ─────────────────────────────────────────
#  Week 1 — Introduction phase
# ─────────────────────────────────────────

def _week1_intro(h: SimulationHarness):
    # Day 1: First interaction
    h.process(
        "Hi there! I'm Scott. I just started using this app.",
        "Welcome, Scott! I'm excited to get to know you. Tell me about yourself! "
        "<remember emotion=\"happy\" importance=\"7\" why=\"first conversation\" anchor=\"true\">"
        "User's name is Scott — first interaction</remember>"
    )

    # Day 1: Share basics
    h.advance_hours(2)
    h.process(
        "I'm a software developer. I like gaming and hiking on weekends.",
        "Great to know! Software dev who enjoys the outdoors and gaming — nice balance! "
        "<remember emotion=\"curious\" importance=\"6\" why=\"personal profile\">"
        "Scott is a software developer, enjoys gaming and hiking on weekends</remember>"
    )

    # Day 1: Evening
    h.advance_hours(6)
    h.process(
        "Had a long day at work. Feeling tired but okay.",
        "Sounds like you need some rest! Don't forget to take care of yourself. "
        "<remember emotion=\"tired\" importance=\"4\" why=\"daily check-in\">"
        "Scott had a long day at work, feeling tired</remember>"
    )

    h.sleep_cycle(8)

    # Day 2
    h.process(*DAILY_GREETINGS[0])
    h.advance_hours(4)
    h.process(
        "I'm working on a really cool AI project at work.",
        "That sounds fascinating! What kind of AI project? "
        "<remember emotion=\"excited\" importance=\"7\" why=\"work interest\">"
        "Scott working on an AI project at work</remember>"
    )
    h.sleep_cycle(8)

    # Days 3-7: Light daily usage
    for day in range(3, 8):
        greeting = DAILY_GREETINGS[day % len(DAILY_GREETINGS)]
        h.process(*greeting)
        if day == 5:
            h.process(*EMOTIONAL_CONVERSATIONS["happy"][0])
        h.advance_hours(8)
        h.sleep_cycle(8)

    h.snapshot("week_1")

    # CHECKPOINT: Verify basics remembered
    h.assert_recall("What is the user's name?", "Scott", label="week1_name_recall")
    h.assert_recall("user's hobbies", "gaming", label="week1_hobby_recall")
    h.assert_recall("user's job", "software developer", label="week1_job_recall")
    h.assert_memory_count(min_count=5, label="week1_memory_count")
    h.assert_chemistry_stable("week1_chemistry")


# ─────────────────────────────────────────
#  Weeks 2-4 — Building rapport
# ─────────────────────────────────────────

def _weeks2_4_rapport(h: SimulationHarness):
    # Week 2: More personal conversations
    for day in range(7):
        h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])

        if day == 1:
            h.process(*EMOTIONAL_CONVERSATIONS["curious"][0])
        elif day == 3:
            h.process(*SOCIAL_INTERACTIONS[0])  # Sarah visit
        elif day == 5:
            h.process(*EMOTIONAL_CONVERSATIONS["nostalgic"][0])

        h.advance_hours(10)
        h.sleep_cycle(8)

    h.snapshot("week_2")

    # Week 3: Introduce reminders and deep topics
    for day in range(7):
        h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])

        if day == 0:
            h.process(*REMINDER_CONVERSATIONS[0])
        elif day == 2:
            h.process(*DEEP_PERSONAL_TOPICS[0])  # Lost in life
        elif day == 4:
            h.process(*TOPIC_CONVERSATIONS["relationships"][0])  # Partner

        h.advance_hours(10)
        h.sleep_cycle(8)

    h.snapshot("week_3")

    # Week 4: Mix of emotions
    for day in range(7):
        h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])

        if day == 1:
            h.process(*EMOTIONAL_CONVERSATIONS["sad"][0])  # Feeling down
        elif day == 3:
            h.process(*EMOTIONAL_CONVERSATIONS["excited"][0])  # Japan trip!
        elif day == 5:
            h.process(*DEEP_PERSONAL_TOPICS[1])  # Grandfather's wisdom
        elif day == 6:
            h.process(*SOCIAL_INTERACTIONS[2])  # Mom calling

        h.advance_hours(10)
        h.sleep_cycle(8)

    h.snapshot("month_1")

    # MONTH 1 CHECKPOINT
    h.assert_recall("Japan trip", "Japan", label="month1_japan_recall")
    h.assert_recall("grandfather's teaching", "kind", label="month1_grandfather_recall")
    h.assert_recall("Who is Sarah?", "Sarah", label="month1_sarah_social")
    h.assert_memory_count(min_count=15, label="month1_memory_count")
    h.assert_chemistry_stable("month1_chemistry")


# ─────────────────────────────────────────
#  Months 2-3 — Deepening relationship
# ─────────────────────────────────────────

def _months2_3_deepening(h: SimulationHarness):
    # Month 2: Every other day usage, deeper topics
    for day in range(30):
        if day % 2 == 0:  # Every other day
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])

            topic_key = ["work", "hobbies", "technology", "goals", "health"][day % 5]
            convos = TOPIC_CONVERSATIONS.get(topic_key, [])
            if convos:
                h.process(*convos[day % len(convos)])

        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_2")

    # Month 3: Important life events
    h.process(
        "I just found out we're expecting a baby!",
        "Oh my goodness, congratulations!! That is incredible news! I'm so happy for you! "
        "<remember emotion=\"overjoyed\" importance=\"10\" why=\"life-changing event\" "
        "cherish=\"true\" anchor=\"true\">"
        "Scott and partner are expecting a baby!</remember>"
    )
    h.advance_days(3)
    h.process(
        "We started looking at baby names. What do you think about the name 'Kai'?",
        "Kai is a beautiful name! It has meanings in multiple cultures. "
        "<remember emotion=\"happy\" importance=\"7\" why=\"baby preparation\">"
        "Scott considering baby name 'Kai'</remember>"
    )
    h.advance_days(5)
    h.process(
        "My birthday is coming up next week!",
        "How exciting! Any big plans? "
        "<remember emotion=\"happy\" importance=\"8\" why=\"personal milestone\" cherish=\"true\">"
        "Scott's birthday coming up</remember>"
    )

    # Continue month 3 with regular check-ins
    for day in range(20):
        if day % 3 == 0:
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_3")

    # MONTH 3 CHECKPOINT
    h.assert_recall("baby expecting", "baby", label="month3_baby_recall")
    h.assert_recall("What is Scott's job", "software developer",
                    label="month3_job_still_recalled")
    h.assert_recall("user's hobbies", "gaming",
                    label="month3_hobbies_still_recalled")
    h.assert_chemistry_stable("month3_chemistry")


# ─────────────────────────────────────────
#  Months 4-6 — Regular usage patterns
# ─────────────────────────────────────────

def _months4_6_regular(h: SimulationHarness):
    # Simulate less frequent but consistent usage
    emotion_keys = list(EMOTIONAL_CONVERSATIONS.keys())

    for month in range(3):  # months 4, 5, 6
        for week in range(4):
            # 3-4 conversations per week
            for day_offset in [0, 2, 4, 6]:
                h.process(*DAILY_GREETINGS[day_offset % len(DAILY_GREETINGS)])

                # Rotate through different emotional conversations
                emo_idx = (month * 4 + week) % len(emotion_keys)
                emo_key = emotion_keys[emo_idx]
                convos = EMOTIONAL_CONVERSATIONS[emo_key]
                h.process(*convos[week % len(convos)])

                h.advance_hours(16)
                h.sleep_cycle(8)

            # Weekend gap
            h.advance_days(1)

        h.snapshot(f"month_{month + 4}")

    # MONTH 6 CHECKPOINT: Can we still recall early memories?
    h.assert_recall("user's name", "Scott", label="month6_name_recall")
    h.assert_recall("expecting baby", "baby", label="month6_baby_recall")
    h.assert_recall("grandfather kind", "kind", label="month6_grandfather_recall")
    h.assert_recall("Japan trip", "Japan", label="month6_japan_recall")
    h.assert_chemistry_stable("month6_chemistry")
    h.assert_memory_count(min_count=30, label="month6_memory_count")


# ─────────────────────────────────────────
#  Months 7-9 — Stress period
# ─────────────────────────────────────────

def _months7_9_stress(h: SimulationHarness):
    # Month 7: Work stress begins
    h.process(
        "Work has been insane lately. Deadlines everywhere.",
        "That sounds overwhelming. Let's prioritize — what's the most urgent? "
        "<remember emotion=\"stressed\" importance=\"7\" why=\"work pressure\">"
        "Scott overwhelmed with work deadlines</remember>"
    )

    for day in range(14):
        if day % 2 == 0:
            h.process(
                "Another late night. I'm exhausted.",
                "Please take care of yourself. Can you delegate anything? "
                "<remember emotion=\"exhausted\" importance=\"5\" why=\"ongoing stress\">"
                "Scott working late, exhausted from workload</remember>"
            )
        h.advance_hours(16)
        h.sleep_cycle(6)  # Shorter sleep during stress

    h.snapshot("month_7_stress_peak")

    # Month 8: Conflict and sad event
    h.advance_days(7)
    h.process(*EMOTIONAL_CONVERSATIONS["angry"][0])  # Coworker taking credit
    h.advance_days(5)
    h.process(*EMOTIONAL_CONVERSATIONS["sad"][1])  # Pet passed away
    h.advance_days(3)
    h.process(
        "I feel like I'm barely holding it together.",
        "You're going through a lot right now, and it's okay to feel this way. I'm here for you. "
        "<remember emotion=\"overwhelmed\" importance=\"8\" why=\"emotional crisis\">"
        "Scott struggling emotionally — work stress, pet loss, feeling overwhelmed</remember>"
    )

    for day in range(15):
        if day % 3 == 0:
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(7)

    h.snapshot("month_8")

    # Month 9: Starting to recover
    h.process(
        "I talked to my manager about the workload. It's getting better.",
        "I'm so glad you spoke up! That takes courage. <remember emotion=\"relieved\" "
        "importance=\"7\" why=\"positive development\">"
        "Scott addressed workload with manager, situation improving</remember>"
    )
    h.advance_days(7)
    h.process(
        "Went for a long hike this weekend. First time in months. Felt amazing.",
        "That's wonderful! Nature can be so healing. <remember emotion=\"peaceful\" "
        "importance=\"7\" why=\"recovery milestone\">"
        "Scott went hiking again — first time in months, felt amazing</remember>"
    )

    for day in range(20):
        if day % 2 == 0:
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_9")

    # MONTH 9 CHECKPOINT: Verify stress period remembered
    h.assert_recall("work stress deadlines", "deadline",
                    label="month9_stress_recall")
    h.assert_recall("pet passed away", "pet",
                    label="month9_pet_recall")
    h.assert_recall("talked to manager", "manager",
                    label="month9_recovery_recall")
    h.assert_chemistry_stable("month9_chemistry")


# ─────────────────────────────────────────
#  Months 10-12 — Recovery & year-end
# ─────────────────────────────────────────

def _months10_12_resolution(h: SimulationHarness):
    # Month 10: Back to normal, new interests
    h.process(
        "I've been getting into woodworking! Built my first cutting board.",
        "That's a wonderful new hobby! Woodworking is so satisfying. <remember emotion=\"proud\" "
        "importance=\"7\" why=\"new creative hobby\">Scott started woodworking, built first cutting board</remember>"
    )
    h.advance_days(5)
    h.process(*EMOTIONAL_CONVERSATIONS["proud"][0])  # Marathon

    for day in range(25):
        if day % 2 == 0:
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_10")

    # Month 11: Holiday season
    h.process(
        "Getting ready for the holidays! Lots of family coming over.",
        "How exciting! Big family gathering? <remember emotion=\"excited\" importance=\"7\" "
        "why=\"holiday plans\">Scott preparing for holiday family gathering</remember>"
    )
    h.advance_days(10)
    h.process(
        "Had the best Thanksgiving ever. The baby is growing so fast!",
        "That must have been wonderful with the growing family! "
        "<remember emotion=\"overjoyed\" importance=\"9\" why=\"family milestone\" cherish=\"true\">"
        "Best Thanksgiving ever — baby growing fast, family together</remember>"
    )

    for day in range(20):
        if day % 3 == 0:
            h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(8)

    h.snapshot("month_11")

    # Month 12: Year-end reflection
    h.process(
        "Wow, it's almost a year since we started talking. What a year it's been.",
        "It really has been quite a journey! You've grown so much — new baby, "
        "career challenges, new hobbies, and you came through it all stronger. "
        "<remember emotion=\"reflective\" importance=\"9\" why=\"year anniversary\" "
        "cherish=\"true\">One year anniversary — Scott reflecting on an eventful year</remember>"
    )
    h.advance_days(3)
    h.process(
        "What do you remember about this year? The highlights and tough times?",
        "So much! The baby news was the highlight — absolutely life-changing. "
        "I remember the tough work period too, and how proud I was when you went hiking again."
    )

    for day in range(10):
        h.process(*DAILY_GREETINGS[day % len(DAILY_GREETINGS)])
        h.advance_hours(16)
        h.sleep_cycle(8)

    # ══════════════════════════════════════════
    #  FINAL YEAR-END ASSERTIONS
    # ══════════════════════════════════════════

    # Core identity — should ALWAYS be recalled
    h.assert_recall("user's name", "Scott", label="FINAL_name")
    h.assert_recall("user's job", "software", label="FINAL_job")

    # Cherished memories — must survive the full year
    h.assert_recall("expecting baby", "baby", label="FINAL_baby_cherished")
    h.assert_recall("grandfather teaching kindness", "kind",
                    label="FINAL_grandfather_cherished")
    h.assert_recall("first marathon", "marathon", label="FINAL_marathon")

    # Emotional arc — stress period
    h.assert_recall("work deadline stress", "deadline",
                    label="FINAL_stress_period")
    h.assert_recall("pet passed away", "pet", label="FINAL_pet_loss")

    # Recovery
    h.assert_recall("hiking after months", "hiking",
                    label="FINAL_hiking_recovery")

    # Social impressions
    h.assert_recall("friend Sarah", "Sarah", label="FINAL_sarah")

    # Newer memories
    h.assert_recall("woodworking cutting board", "woodworking",
                    label="FINAL_woodworking")
    h.assert_recall("Thanksgiving family", "Thanksgiving",
                    label="FINAL_thanksgiving")

    # System health checks
    h.assert_chemistry_stable("FINAL_chemistry")
    h.assert_memory_count(min_count=40, label="FINAL_memory_count")
    h.assert_mood(label="FINAL_mood_valid")
