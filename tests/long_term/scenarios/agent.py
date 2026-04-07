"""
Agent Preset — Year-Long Scenario
==================================
Simulates a user using Mimir as a task-focused coding/work assistant.

Covers: task management, solution patterns, project tracking, code help,
tool calls, multi-project workflows, long-term knowledge retention.
"""

from __future__ import annotations
from tests.long_term.harness import (
    SimulationHarness, AGENT_TASK_CONVERSATIONS,
    TOPIC_CONVERSATIONS, TASK_CONVERSATIONS,
)


def run_agent_year(harness: SimulationHarness) -> None:
    h = harness
    h.snapshot("day_0_start")

    # ══════════════════════════════════════════
    #  WEEK 1-2: Project Setup & Initial Tasks
    # ══════════════════════════════════════════

    # Day 1: Start a project
    h.process(
        "Let's start a new project called 'DataPipeline'. I need to build an ETL system.",
        "Great! Let me set that up for you.\n"
        "<task action=\"start\" priority=\"9\" project=\"DataPipeline\">Design ETL pipeline architecture</task>\n"
        "<remember emotion=\"focused\" importance=\"7\" why=\"new project kickoff\">"
        "Started DataPipeline project — building ETL system</remember>"
    )

    task1 = h.start_task("Design ETL architecture", priority=9, project="DataPipeline")

    h.advance_hours(4)
    h.process(
        "The data sources are PostgreSQL and a REST API. We need to load into BigQuery.",
        "Understood. PostgreSQL → transform → BigQuery, with REST API as secondary source.\n"
        "<remember emotion=\"focused\" importance=\"8\" why=\"technical requirements\">"
        "DataPipeline: PostgreSQL + REST API → BigQuery ETL</remember>\n"
        "<solution problem=\"ETL source variety\" importance=\"7\">"
        "Use Apache Airflow for orchestration with custom operators per source type</solution>"
    )

    h.advance_hours(2)
    h.process(
        "How should we handle data validation?",
        "I'd recommend a validation layer using Great Expectations or Pydantic schemas:\n"
        "```python\n"
        "from pydantic import BaseModel, validator\n\n"
        "class DataRecord(BaseModel):\n"
        "    id: int\n"
        "    value: float\n"
        "    timestamp: str\n\n"
        "    @validator('value')\n"
        "    def value_positive(cls, v):\n"
        "        if v < 0:\n"
        "            raise ValueError('must be positive')\n"
        "        return v\n"
        "```\n"
        "<solution problem=\"data validation in ETL\" importance=\"8\">"
        "Use Pydantic models for schema validation at ingestion stage</solution>"
    )

    h.sleep_cycle(8)

    # Days 3-14: Regular work sessions
    work_topics = [
        ("I need to write unit tests for the data transformations.",
         "Here's a test structure using pytest:\n```python\ndef test_transform_normalizes():\n    raw = {'val': '100'}\n    result = transform(raw)\n    assert result['val'] == 100.0\n```\n"
         "<task action=\"start\" priority=\"7\" project=\"DataPipeline\">Write unit tests for transformations</task>"),
        ("The REST API has rate limits. How do we handle that?",
         "Use exponential backoff with a rate limiter.\n"
         "<solution problem=\"API rate limits\" importance=\"7\">Implement exponential backoff with configurable retry count and jitter</solution>"),
        ("I found a bug — duplicate records slipping through.",
         "Classic ETL issue. Add a dedup stage using content hashing.\n"
         "<solution problem=\"duplicate records in ETL\" importance=\"8\">Hash-based dedup using MD5 of key fields at transformation stage</solution>"),
        ("Tests are passing. Ready to deploy to staging.",
         "<task action=\"complete\" id=\"last\">Unit tests completed and passing</task>\n"
         "<task action=\"start\" priority=\"8\" project=\"DataPipeline\">Deploy to staging environment</task>"),
        ("Staging deployment succeeded! Moving to production next week.",
         "Excellent progress! <task action=\"complete\" id=\"last\">Staging deployment successful</task>\n"
         "<remember emotion=\"satisfied\" importance=\"8\" why=\"project milestone\">DataPipeline deployed to staging successfully</remember>"),
    ]

    for i, (user, asst) in enumerate(work_topics):
        h.advance_hours(4 + (i % 3))
        h.process(user, asst)
        if i % 2 == 0:
            h.sleep_cycle(8)

    h.snapshot("week_2")
    h.assert_recall("DataPipeline architecture", "ETL",
                    label="week2_project_recall")
    h.assert_recall("data validation approach", "Pydantic",
                    label="week2_solution_recall")

    # ══════════════════════════════════════════
    #  MONTH 2: Second project, cross-referencing
    # ══════════════════════════════════════════

    h.advance_days(14)

    h.process(
        "Starting a new project: 'MonitorDash' — a real-time monitoring dashboard.",
        "Let me set that up!\n"
        "<task action=\"start\" priority=\"9\" project=\"MonitorDash\">Build monitoring dashboard MVP</task>\n"
        "<remember emotion=\"focused\" importance=\"7\" why=\"new project\">"
        "Started MonitorDash project — real-time monitoring dashboard</remember>"
    )
    h.start_task("Build monitoring dashboard frontend", priority=8, project="MonitorDash")

    h.advance_hours(6)
    h.process(
        "The dashboard should show DataPipeline metrics too. Can you reference the schema we designed?",
        "Absolutely! From the DataPipeline project, you used Pydantic models with PostgreSQL and BigQuery. "
        "We can expose those validation metrics via a simple API endpoint."
    )

    # Regular work for month 2
    for day in range(20):
        if day % 3 == 0:
            h.process(
                "Status update on MonitorDash — making progress on the frontend.",
                "Good to hear! Let me know if you need help with any components."
            )
        h.advance_hours(10)
        h.sleep_cycle(8)

    h.snapshot("month_2")

    # ══════════════════════════════════════════
    #  MONTH 3-6: Ongoing project work
    # ══════════════════════════════════════════

    solutions_planted = [
        ("How do I handle WebSocket reconnection?",
         "Use reconnecting-websocket library with exponential backoff.\n"
         "<solution problem=\"WebSocket reconnection\" importance=\"7\">"
         "Apply reconnecting-websocket with max 5 retries and exponential backoff</solution>"),
        ("Database migrations are getting complex.",
         "Use Alembic with auto-revision and downgrade scripts.\n"
         "<solution problem=\"database migration management\" importance=\"8\">"
         "Alembic for migrations with auto-generation and known-good downgrade paths</solution>"),
        ("CI/CD is slow — builds take 20 minutes.",
         "Parallelize test suites and add Docker layer caching.\n"
         "<solution problem=\"slow CI/CD builds\" importance=\"7\">"
         "Parallel test execution + Docker layer caching cuts build time by ~60%</solution>"),
        ("How should we structure the API authentication?",
         "JWT with refresh tokens and short-lived access tokens.\n"
         "<solution problem=\"API authentication\" importance=\"9\">"
         "JWT with 15-min access tokens + 7-day refresh tokens + revocation list</solution>"),
    ]

    for month in range(4):  # months 3-6
        h.advance_days(5)
        if month < len(solutions_planted):
            h.process(*solutions_planted[month])

        for day in range(25):
            if day % 4 == 0:
                h.process(
                    "Quick question about the codebase.",
                    "Sure, what do you need?"
                )
            h.advance_hours(10)
            h.sleep_cycle(8)

        h.snapshot(f"month_{month + 3}")

    # MONTH 6 CHECKPOINT
    h.assert_recall("DataPipeline ETL architecture", "ETL",
                    label="month6_datapipeline_recall")
    h.assert_recall("MonitorDash monitoring dashboard", "dashboard",
                    label="month6_monitordash_recall")
    h.assert_recall("API rate limits solution", "backoff",
                    label="month6_solution_backoff")
    h.assert_recall("duplicate records dedup", "dedup",
                    label="month6_solution_dedup")
    h.assert_memory_count(min_count=15, label="month6_memory_count")

    # ══════════════════════════════════════════
    #  MONTH 7-12: Long-term pattern recognition
    # ══════════════════════════════════════════

    h.process(
        "Starting third project: 'MLServing' — ML model serving infrastructure.",
        "<task action=\"start\" priority=\"9\" project=\"MLServing\">Design ML serving architecture</task>\n"
        "<remember emotion=\"focused\" importance=\"8\" why=\"third major project\">"
        "Started MLServing project — ML model serving infrastructure</remember>"
    )

    h.advance_days(30)

    h.process(
        "MLServing needs data validation too, like DataPipeline. What did we use?",
        "You used Pydantic models for schema validation at the ingestion stage in DataPipeline. "
        "The same pattern would work great for ML feature validation."
    )

    # Continue light usage
    for month in range(6):  # months 7-12
        for day in range(25):
            if day % 5 == 0:
                h.process(
                    "Working on MLServing. Everything's going well.",
                    "Great to hear! Keep up the good work."
                )
            h.advance_hours(10)
            h.sleep_cycle(8)
        h.snapshot(f"month_{month + 7}")

    # ══════════════════════════════════════════
    #  FINAL YEAR-END ASSERTIONS
    # ══════════════════════════════════════════

    # Project knowledge retention
    h.assert_recall("DataPipeline ETL", "ETL", label="FINAL_datapipeline")
    h.assert_recall("monitoring dashboard project", "MonitorDash",
                    label="FINAL_monitordash")
    h.assert_recall("MLServing", "ML", label="FINAL_mlserving")

    # Solutions should persist
    h.assert_recall("data validation approach", "Pydantic",
                    label="FINAL_pydantic_solution")
    h.assert_recall("API authentication design", "JWT",
                    label="FINAL_jwt_solution")
    h.assert_recall("CI/CD optimization", "parallel",
                    label="FINAL_cicd_solution")

    # Technical details from early conversations
    h.assert_recall("ETL data sources", "BigQuery",
                    label="FINAL_bigquery_detail")
    h.assert_recall("duplicate handling", "hash",
                    label="FINAL_dedup_detail")

    h.assert_memory_count(min_count=20, label="FINAL_memory_count")
    h.assert_chemistry_stable("FINAL_chemistry")
