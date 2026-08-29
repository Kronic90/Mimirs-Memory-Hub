"""
Mimir — Custom Agent Integration Example
==========================================

This shows how to wire Mimir's memory system into your own agent loop,
giving it persistent episodic memory, social awareness, task tracking,
procedural learning, and neurochemistry — without needing Mimir's Memory Hub.

    pip install vividmimir[all]

Or pick only what you need:

    pip install vividmimir                    # core (BM25 only, no GPU)
    pip install vividmimir[neurochemistry]    # + VividnessMem
    pip install vividmimir[embedding]         # + VividEmbed (semantic search)
"""

from vividmimir import Mimir


# ── 1. Initialise Mimir ─────────────────────────────────────────────

# Point llm_fn at whatever model you use.  It receives a plain string
# prompt and must return a plain string response.
# This unlocks: decompose_query, edit_memories, reflect, LLM-inferred
# Yggdrasil edges, and richer consolidation during sleep_reset.

def my_llm(prompt: str) -> str:
    """Replace this with your actual LLM call."""
    # Example with llama-cpp-python:
    #   return llm.create_chat_completion(
    #       messages=[{"role": "user", "content": prompt}]
    #   )["choices"][0]["message"]["content"]
    #
    # Example with OpenAI:
    #   return openai.chat.completions.create(
    #       model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    #   ).choices[0].message.content
    raise NotImplementedError("Wire up your LLM here")


mimir = Mimir(
    data_dir="my_agent_memory",   # persists here as JSON
    chemistry=True,               # neurochemistry (dopamine, cortisol, etc.)
    visual=False,                 # set True + install Pillow for image memory
    llm_fn=my_llm,               # optional — unlocks LLM-driven features
)


# ── 2. The Agent Loop ───────────────────────────────────────────────

def agent_turn(user_name: str, user_message: str) -> str:
    """One turn of your agent. Call this from whatever interface you use."""

    # ── 2a. Build the memory context block ──────────────────────────
    # This assembles: current mood, relevant memories, social impressions,
    # active lessons, due reminders, neurochemistry — ready to inject
    # into your system prompt.
    memory_context = mimir.get_context_block(
        current_entity=user_name,
        conversation_context=user_message,
    )

    # ── 2b. Construct your prompt ───────────────────────────────────
    system_prompt = f"""You are a helpful AI assistant with a persistent memory.

{memory_context}

Use the memories above to give personalised, contextually aware responses.
If you remember something relevant, reference it naturally."""

    # Call your LLM here with system_prompt + user_message
    # response = my_llm(...)
    response = "..."  # placeholder

    # ── 2c. Store the exchange as a memory ──────────────────────────
    mimir.remember(
        content=f"{user_name} said: {user_message}",
        emotion="neutral",       # or detect emotion from the message
        importance=5,             # 1-10 scale
        why_saved="conversation",
    )

    # ── 2d. Update mood from the conversation ───────────────────────
    mimir.update_mood(["neutral"])  # pass detected emotions as a list

    # ── 2e. Tick neurochemistry dampening if active ─────────────────
    mimir.tick_dampening()

    # ── 2f. Persist ─────────────────────────────────────────────────
    mimir.save()

    return response


# ── 3. Social Memory ────────────────────────────────────────────────
# Store impressions of people the user mentions.

def note_person(entity: str, observation: str, emotion: str = "neutral"):
    """Store or update an impression of a person."""
    mimir.add_social_impression(
        entity=entity,
        content=observation,
        emotion=emotion,
        importance=6,
        why_saved="social observation",
    )


# ── 4. Task & Project Memory ────────────────────────────────────────
# Full task lifecycle with action logging and solution patterns.

def example_task_workflow():
    """Demonstrate task tracking with procedural memory."""

    # Set active project context
    mimir.set_active_project("website-redesign")

    # Start a task
    task = mimir.start_task(
        description="Migrate database to PostgreSQL",
        priority=8,
        project="website-redesign",
    )

    # Log actions as work progresses
    mimir.log_action(
        task_id=task.task_id,
        action="Created migration script",
        result="Schema converted successfully",
    )

    mimir.log_action(
        task_id=task.task_id,
        action="Ran migration on staging",
        result="",
        error="Foreign key constraint failed on orders table",
        fix="Added CASCADE to user_id reference",
    )

    # Complete or fail the task
    mimir.complete_task(task.task_id, outcome="Migration live on production")
    # or: mimir.fail_task(task.task_id, reason="Blocked by infra team")

    # Record reusable solutions
    mimir.record_solution(
        problem="PostgreSQL migration foreign key errors",
        solution="Check all FK references and add CASCADE where appropriate",
        importance=7,
    )

    # Later, find past solutions for similar problems
    solutions = mimir.find_solutions("database migration constraint error")
    for sol in solutions:
        print(f"  Past fix: {sol.solution}")

    # Track project artifacts
    mimir.track_artifact(
        name="migration_v2.sql",
        artifact_type="file",
        description="Final PostgreSQL migration script",
        importance=7,
    )

    # Get full project overview
    overview = mimir.get_project_overview()
    print(f"  Active tasks: {len(overview.get('active_tasks', []))}")


# ── 5. Procedural Learning ──────────────────────────────────────────
# Lessons the agent learns from experience — with outcome tracking.

def example_lessons():
    lesson = mimir.add_lesson(
        topic="API rate limiting",
        context_trigger="when calling external APIs in a loop",
        strategy="Add exponential backoff with jitter, start at 1s",
        importance=7,
    )

    # Record how the strategy worked
    mimir.record_outcome(
        lesson_id=lesson.lesson_id,
        action="Applied backoff to Stripe API calls",
        result="success",
        diagnosis="No more 429 errors",
    )

    # Retrieve relevant lessons during future work
    relevant = mimir.retrieve_lessons("hitting rate limits on API")
    for lesson, score in relevant:
        print(f"  [{score:.2f}] {lesson.topic}: {lesson.strategy}")


# ── 6. Volatile Facts ───────────────────────────────────────────────
# Quick entity/attribute/value storage with 12-hour half-life.

mimir.add_fact("user", "timezone", "America/New_York")
mimir.add_fact("user", "current_task", "writing blog post")

facts = mimir.get_facts("user")
for f in facts:
    print(f"  {f.attribute} = {f.value}")


# ── 7. Reminders ────────────────────────────────────────────────────
# Prospective memory — fires after a set time.

mimir.set_reminder("Check if deployment succeeded", hours=2.0)

# Check at the start of each turn
due = mimir.get_due_reminders()
for r in due:
    print(f"  ⏰ Reminder: {r.text}")


# ── 8. Advanced Recall ──────────────────────────────────────────────

# Hybrid BM25 + semantic recall (top 10)
memories = mimir.recall("what projects have I worked on?", limit=10)

# Cross-type unified recall (memories + impressions + facts + lessons)
everything = mimir.recall_unified("database work", limit=8)
# Returns: {"reflections": [...], "impressions": [...], "facts": [...], "lessons": [...]}

# Recall with retrieval-induced forgetting + involuntary recall
memories = mimir.resonate("that conversation about philosophy", limit=5)

# Time-range recall
from datetime import datetime
memories = mimir.recall_period(
    start=datetime(2025, 1, 1),
    end=datetime(2025, 12, 31),
    limit=20,
)

# Temporal context (what's relevant today, upcoming, recent)
temporal = mimir.get_temporal_context()
# Returns: {"today": [...], "upcoming": [...], "recent": [...]}


# ── 9. Neurochemistry Events ────────────────────────────────────────
# Signal life events to modulate encoding, recall, and mood.

mimir.on_event("achievement", intensity=0.8)   # dopamine spike
mimir.on_event("social_bonding", intensity=0.6) # oxytocin
mimir.on_event("threat", intensity=0.5)         # cortisol + norepinephrine
# Event types: achievement, social_bonding, threat, loss, surprise,
#              novelty, routine, conflict, resolution, intimacy


# ── 10. Session Lifecycle ───────────────────────────────────────────
# Call at the start/end of conversations.

def on_session_start():
    """Call when a new conversation begins."""
    mimir.bump_session()

    # Check for due reminders
    for r in mimir.get_due_reminders():
        print(f"Reminder: {r.text}")


def on_session_end():
    """Call when a conversation ends. Runs consolidation."""
    # sleep_reset runs the full between-session cycle:
    #   - Neurochemistry reset
    #   - Muninn (merge duplicates, prune dead memories, strengthen co-activated)
    #   - Huginn (detect patterns, entity arcs, open threads)
    #   - Völva (dream synthesis — cross-theme insight generation)
    #   - Yggdrasil rebuild (memory graph)
    mimir.sleep_reset(hours=8.0)
    mimir.save()


# ── 11. LLM-Powered Features (requires llm_fn) ─────────────────────

# Break a vague query into focused sub-queries
sub_queries = mimir.decompose_query("what's been going on lately?")
# Returns: ["recent work projects", "social interactions this week", ...]

# LLM-driven memory curation
result = mimir.edit_memories("Forget anything about my old address")
# Returns: {"promoted": 0, "demoted": 0, "forgotten": 2, "updated": 0}

# Self-reflection (generates insight from memory patterns)
insight = mimir.reflect()
print(insight)


# ── 12. Inspect System State ────────────────────────────────────────

stats = mimir.stats()
print(f"Total memories:  {stats['total_reflections']}")
print(f"Social entities: {stats['total_social']}")
print(f"Active tasks:    {stats['active_tasks']}")
print(f"Lessons:         {stats['total_lessons']}")
print(f"Current mood:    {stats['mood']}")
print(f"Yggdrasil edges: {stats['yggdrasil_edges']}")
