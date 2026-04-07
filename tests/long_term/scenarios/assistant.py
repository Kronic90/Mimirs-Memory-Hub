"""
Assistant Preset — Year-Long Scenario
=======================================
Simulates a user using Mimir as a personal assistant / PA.

Covers: reminders, task tracking, scheduling, organizational skills,
information recall over time, meeting preparation, daily briefings.
"""

from __future__ import annotations
from tests.long_term.harness import SimulationHarness


def run_assistant_year(harness: SimulationHarness) -> None:
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  WEEK 1: Setting up preferences
    # ══════════════════════════════════════════

    h.process(
        "I want you to help me stay organized. I'm terrible at remembering meetings.",
        "I'd be happy to help! I'll keep track of your schedule, reminders, and tasks. "
        "<remember emotion=\"focused\" importance=\"7\" why=\"user preference\" anchor=\"true\">"
        "User needs help staying organized — poor at remembering meetings</remember>"
    )

    h.advance_hours(2)
    h.process(
        "My work schedule is usually 9-5 weekdays. I have a weekly team standup on Mondays at 10am.",
        "Got it — standard 9-5 weekday schedule with Monday 10am standup. "
        "<remember emotion=\"neutral\" importance=\"8\" why=\"routine schedule\" anchor=\"true\">"
        "Work schedule: 9-5 weekdays. Weekly team standup Monday 10am</remember>"
    )

    h.advance_hours(1)
    h.process(
        "I have a dentist appointment next Tuesday at 2pm. Can you remind me?",
        "Of course! I'll remind you.\n<remind in=\"144h\">Dentist appointment at 2pm</remind>\n"
        "<remember emotion=\"neutral\" importance=\"5\" why=\"appointment\">"
        "Dentist appointment next Tuesday 2pm</remember>"
    )

    h.sleep_cycle(8)

    # Days 2-7: Building routine
    daily_tasks = [
        ("What do I have today?",
         "Based on what I know: you have your regular work day 9-5. No special appointments today."),
        ("I need to prepare a report for my boss by Friday.",
         "<task action=\"start\" priority=\"8\" project=\"Work\">Prepare report for boss — due Friday</task>\n"
         "<remind in=\"72h\">Report for boss due today</remind>\n"
         "<remember emotion=\"focused\" importance=\"7\" why=\"work deadline\">"
         "Report due for boss by Friday</remember>"),
        ("Remind me to buy groceries on the way home.",
         "<remind in=\"6h\">Buy groceries on the way home</remind>"),
        ("I finished the report!",
         "Great job getting it done early!\n<task action=\"complete\" id=\"last\">Report completed ahead of deadline</task>"),
        ("My colleague asked me to review her code by next Wednesday.",
         "<task action=\"start\" priority=\"6\" project=\"Work\">Review colleague's code — due next Wednesday</task>\n"
         "<remind in=\"144h\">Code review due for colleague</remind>\n"
         "<remember emotion=\"neutral\" importance=\"5\" why=\"work task\">"
         "Code review for colleague due next Wednesday</remember>"),
    ]

    for i, (user, asst) in enumerate(daily_tasks):
        h.advance_hours(8 + (i % 4))
        h.process(user, asst)
        if i % 2 == 0:
            h.sleep_cycle(8)

    h.snapshot("week_1")
    h.assert_recall("Monday standup", "standup", label="week1_standup_recall")
    h.assert_recall("work schedule", "9-5", label="week1_schedule_recall")

    # ══════════════════════════════════════════
    #  MONTHS 1-3: Regular assistant usage
    # ══════════════════════════════════════════

    monthly_events = {
        1: [
            ("I have a performance review coming up in 2 weeks.",
             "<remind in=\"336h\">Performance review meeting</remind>\n"
             "<remember emotion=\"anxious\" importance=\"8\" why=\"career event\">"
             "Performance review in 2 weeks</remember>"),
            ("My friend's birthday is on March 15th. I need to buy a gift.",
             "<remind in=\"720h\">Buy birthday gift for friend — birthday March 15</remind>\n"
             "<remember emotion=\"neutral\" importance=\"5\" why=\"social obligation\">"
             "Friend's birthday March 15 — need to buy gift</remember>"),
        ],
        2: [
            ("I'm presenting at a conference in April. Need to prepare slides.",
             "<task action=\"start\" priority=\"9\" project=\"Conference\">Prepare conference presentation slides</task>\n"
             "<remember emotion=\"motivated\" importance=\"8\" why=\"career opportunity\">"
             "Conference presentation in April — need to prepare slides</remember>"),
            ("Can you help me outline the presentation? It's about microservices.",
             "Of course! Let me help structure it:\n1. Introduction & problem statement\n"
             "2. Microservices architecture patterns\n3. Case study from your work\n"
             "4. Lessons learned\n5. Q&A\n"
             "<remember emotion=\"focused\" importance=\"7\" why=\"project content\">"
             "Conference presentation topic: microservices architecture</remember>"),
        ],
        3: [
            ("Performance review went great! Got a 15% raise!",
             "Congratulations! That's a fantastic result!\n"
             "<remember emotion=\"proud\" importance=\"9\" why=\"career milestone\" cherish=\"true\">"
             "Got 15% raise at performance review</remember>"),
            ("Conference presentation is ready. 35 slides.",
             "<task action=\"complete\" id=\"last\">Conference presentation completed — 35 slides on microservices</task>\n"
             "<remember emotion=\"satisfied\" importance=\"7\" why=\"task completed\">"
             "Conference presentation ready — 35 slides on microservices</remember>"),
        ],
    }

    for month_num, events in monthly_events.items():
        for user, asst in events:
            h.advance_days(5 + month_num)
            h.process(user, asst)

        # Regular daily check-ins
        for day in range(20):
            if day % 4 == 0:
                h.process(
                    "What's on my agenda today?",
                    "Let me check your tasks and reminders. I'll pull up what's pending."
                )
            h.advance_hours(10)
            h.sleep_cycle(8)

        h.snapshot(f"month_{month_num}")

    h.assert_recall("performance review raise", "15%", label="month3_raise_recall")
    h.assert_recall("conference microservices", "microservices",
                    label="month3_conference_recall")

    # ══════════════════════════════════════════
    #  MONTHS 4-8: Ongoing organizational support
    # ══════════════════════════════════════════

    ongoing_events = [
        ("I'm learning Spanish in my free time. Can you quiz me occasionally?",
         "<remember emotion=\"motivated\" importance=\"6\" why=\"personal development\">"
         "User learning Spanish — wants occasional quizzes</remember>"),
        ("I need to renew my car registration by June 30.",
         "<remind in=\"1440h\">Renew car registration — deadline June 30</remind>\n"
         "<remember emotion=\"neutral\" importance=\"7\" why=\"administrative deadline\">"
         "Car registration renewal deadline: June 30</remember>"),
        ("I got invited to interview at a bigger company. Should I go?",
         "That's exciting! There's no harm in exploring opportunities. "
         "<remember emotion=\"conflicted\" importance=\"8\" why=\"career decision\">"
         "User invited to interview at bigger company — considering options</remember>"),
        ("I decided to stay at my current company. The culture is too good to leave.",
         "That shows real self-awareness about what matters to you! "
         "<remember emotion=\"content\" importance=\"8\" why=\"career decision made\">"
         "User decided to stay at current company — values culture over bigger offer</remember>"),
    ]

    for i, (user, asst) in enumerate(ongoing_events):
        h.advance_days(20 + i * 10)
        h.process(user, asst)

    for month in range(5):  # months 4-8
        for day in range(25):
            if day % 5 == 0:
                h.process(
                    "Daily briefing please.",
                    "Good morning! Here's what I have for today: checking pending tasks and reminders."
                )
            h.advance_hours(10)
            h.sleep_cycle(8)
        h.snapshot(f"month_{month + 4}")

    # ══════════════════════════════════════════
    #  MONTHS 9-12: Year-end planning
    # ══════════════════════════════════════════

    h.process(
        "It's almost year-end. Can you help me plan my goals for next year?",
        "Absolutely! Based on what we've covered this year, here are some categories:\n"
        "- Career: You stayed loyal but keep growing\n"
        "- Learning: Continue Spanish, maybe add another skill\n"
        "- Health & Fitness: Any goals there?\n"
        "- Personal: Maintaining the great work-life balance.\n"
        "<remember emotion=\"reflective\" importance=\"8\" why=\"year-end planning\">"
        "Year-end goal setting discussion — career, learning, health</remember>"
    )

    for day in range(80):
        if day % 6 == 0:
            h.process(
                "Quick status check.",
                "Everything's on track. No overdue tasks or reminders."
            )
        h.advance_hours(10)
        h.sleep_cycle(8)

    # ══════════════════════════════════════════
    #  FINAL ASSERTIONS
    # ══════════════════════════════════════════

    # Core user preferences
    h.assert_recall("work schedule routine", "9-5", label="FINAL_schedule")
    h.assert_recall("Monday standup meeting", "standup", label="FINAL_standup")
    h.assert_recall("needs help organizing", "organized",
                    label="FINAL_org_preference")

    # Key career events
    h.assert_recall("performance review raise", "15%", label="FINAL_raise")
    h.assert_recall("conference presentation", "microservices",
                    label="FINAL_conference")
    h.assert_recall("stayed at company culture", "culture",
                    label="FINAL_company_decision")

    # Personal details
    h.assert_recall("learning Spanish", "Spanish", label="FINAL_spanish")

    h.assert_memory_count(min_count=15, label="FINAL_memory_count")
    h.assert_chemistry_stable("FINAL_chemistry")
