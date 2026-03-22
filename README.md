# Mímir — The Ultimate Memory Architecture

<p align="center">
  <img src="MimirLogo.png" alt="Mímir Logo" width="300">
</p>

[![PyPI](https://img.shields.io/pypi/v/vividmimir)](https://pypi.org/project/vividmimir/)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Kronic90/Mimir/blob/main/demo_colab.ipynb)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm--NC-blue)](https://polyformproject.org/licenses/noncommercial/1.0.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

> *"Mímir, whose name means 'the rememberer,' was the wisest of the Æsir.
> Even after his death, Odin preserved his head and consulted it for counsel
> and hidden knowledge. He guarded the Well of Wisdom beneath the world-tree
> Yggdrasil — the well whose waters held every memory and every truth that
> had ever been or ever would be. To drink from it, Odin sacrificed his own
> eye, because that is the price wisdom demands."*
>
> — Norse mythology (Prose Edda, Snorri Sturluson c. 1220)

This library carries that name because it aspires to the same role: a single
well of memory that an AI agent can drink from to remember, feel, forget, and
grow — not as a flat key-value store, but as a living, decaying, emotionally
rich episodic mind modelled on real neuroscience.

---

## What Is Mímir?

Mímir is a **~4,500-line Python module** that gives any AI agent a full
episodic, procedural, social, temporal, and visual memory system. It
orchestrates the **Vivid ecosystem** — [VividnessMem](https://pypi.org/project/vividnessmem/)
for neurochemistry and [VividEmbed](https://pypi.org/project/vividembed/) for
semantic retrieval — then layers **twenty-one neuroscience mechanisms** on top.

Memories are not static database rows. They **decay organically**, **drift
emotionally**, get **compressed into gist** over months, and can be
**involuntarily recalled** by stray associations — the same way human memory
actually works.

```
┌─────────────────────────────────────────────────┐
│                   Mímir                         │
│                                                 │
│  ┌───────────┐  ┌────────────┐  ┌───────────┐  │
│  │ Episodic  │  │ Procedural │  │  Social   │  │
│  │ Memories  │  │  Lessons   │  │Impressions│  │
│  └─────┬─────┘  └─────┬──────┘  └─────┬─────┘  │
│        │              │              │          │
│  ┌─────┴──────────────┴──────────────┴─────┐   │
│  │         21 Neuroscience Layers          │   │
│  │  flashbulb · reconsolidation · state-   │   │
│  │  dependent · spreading activation ·     │   │
│  │  RIF · Zeigarnik · involuntary recall · │   │
│  │  temporal gist · episodic time ·        │   │
│  │  visual imagery                         │   │
│  └─────────────────┬───────────────────────┘   │
│                    │                            │
│  ┌─────────────────┴───────────────────────┐   │
│  │        Hybrid Retrieval Bridge          │   │
│  │   BM25 keywords + VividEmbed semantic   │   │
│  │   + Date index → 5-signal re-rank       │   │
│  └─────────────────┬───────────────────────┘   │
│                    │                            │
│  ┌────────────┐  ┌─┴────────────┐              │
│  │VividnessMem│  │  VividEmbed  │              │
│  │ chemistry  │  │  384-d + PAD │              │
│  └────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────┘
```

---

## The Vivid Ecosystem

Mímir is the orchestration layer. The engines underneath are independently
published and pip-installable:

| Package | Role | PyPI |
|---------|------|------|
| **VividnessMem** | Neurochemistry engine — 5 neurotransmitters (dopamine, serotonin, cortisol, oxytocin, norepinephrine), 10 event profiles, 9 cognitive modifiers, emotional firewall, dampening, audit logging | `pip install vividnessmem` |
| **VividEmbed** | Semantic embedding engine — fine-tuned MiniLM producing 389-d hybrid vectors (384-d sentence + 3-d PAD emotion + 2-d meta), emotion-space queries, contradiction detection | `pip install vividembed` |
| **Mímir** | Orchestrator — 21 neuroscience mechanisms, hybrid BM25+semantic retrieval, temporal awareness, visual memory, task branch, encryption at rest, LLM integration, visualization, context-block generation for LLM prompt injection | *(this repo)* |

All three are **optional for each other**. Mímir works standalone (with
graceful fallbacks), but every engine amplifies the others:

- Without VividnessMem → neurochemistry modifiers default to 1.0, no
  emotional audit log
- Without VividEmbed → recall falls back to BM25 keyword search only
- Without Pillow → visual memory falls back to text descriptions
- Without `cryptography` → encryption at rest is disabled, data stored as plaintext JSON

---

## Cross-System Feature Matrix

A complete comparison of capabilities across all three Vivid ecosystem packages.
Every feature listed exists and is tested.

### Core Memory Architecture

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Organic spaced-repetition decay | Yes | — | Yes |
| 60-emotion PAD vector space | Yes | Yes | Yes |
| Memory vividness (0→1 lifecycle) | Yes | — | Yes |
| Importance scoring (1-10) | Yes | Yes | Yes |
| Content-addressable deduplication | Yes | — | Yes |
| `__slots__`-optimised Memory class | Yes | — | Yes (27 slots) |
| Atomic JSON persistence | Yes | Yes | Yes |

### Neurochemistry & Emotion

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| 5 neurotransmitters (DA, 5-HT, CORT, OXT, NE) | Yes (engine) | — | Yes (via VMem) |
| 10 life-event profiles | Yes | — | Yes |
| 9 cognitive modifiers | Yes | — | Yes |
| Emotional firewall (safety limits) | Yes | — | Yes |
| Emotional dampening (self-regulation) | Yes | — | Yes |
| Emotional audit log | Yes | — | Yes |
| Cognitive override (reappraisal) | Yes | — | Yes |
| Mood EMA blending | Yes | — | Yes |
| Emotion drift detection + reframe | — | — | Yes |

### Retrieval

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| BM25 keyword search | — | — | Yes |
| Semantic vector search (389-d) | — | Yes | Yes (via VEmbed) |
| Hybrid BM25 + semantic fusion | — | — | Yes |
| 5-signal re-ranking | — | — | Yes |
| Spreading activation (priming) | — | — | Yes |
| Retrieval-induced forgetting | — | — | Yes |
| Involuntary recall (unbidden) | — | — | Yes |
| State-dependent retrieval (mood) | — | — | Yes |
| Emotion-space queries | — | Yes | Yes |
| Contradiction detection | — | Yes | Yes |

### Neuroscience Mechanisms

| Mechanism | VividnessMem | VividEmbed | Mímir |
|-----------|:---:|:---:|:---:|
| Flashbulb memory (Brown & Kulik 1977) | — | — | Yes |
| Reconsolidation (Nader 2000) | — | — | Yes |
| State-dependent retrieval (Godden & Baddeley 1975) | — | — | Yes |
| Spreading activation (Collins & Loftus 1975) | — | — | Yes |
| Retrieval-induced forgetting (Anderson 1994) | — | — | Yes |
| Zeigarnik effect (Zeigarnik 1927) | — | — | Yes |
| Involuntary memory (Berntsen 2009) | — | — | Yes |
| Temporal gist extraction (Tulving 1972) | — | — | Yes |
| Temporal/episodic dating | — | — | Yes |
| Visual/mental imagery (Kosslyn 1980) | — | — | Yes |
| Huginn — background insight generation | — | — | Yes |
| Muninn — consolidation daemon | — | — | Yes |
| Yggdrasil — memory graph | — | — | Yes |
| Völva's Vision — dream synthesis | — | — | Yes |
| Hippocampal pattern separation (Yassa & Stark 2011) | — | Yes | Yes |
| Narrative arc tracking (Freytag 1863) | — | Yes | Yes |
| Enhanced relational reasoning (LLM-inferred) | — | — | Yes |
| Hierarchical memory organisation | — | — | Yes |
| Mental time travel (Tulving 1985) | — | — | Yes |
| Novelty-modulated encoding (Ranganath & Rainer 2003) | — | — | Yes |
| Enhanced drift analysis (velocity + bias) | — | — | Yes |

### Embedding & Vectors

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Fine-tuned MiniLM (384-d) | — | Yes | Yes (via VEmbed) |
| 3-d PAD emotion dimensions | — | Yes | Yes |
| 2-d meta dimensions (importance + stability) | — | Yes | Yes |
| Emotion-prefix tokenisation | — | Yes | Yes |
| Batch encoding | — | Yes | Yes |
| VividCortex LLM layer | — | Yes | — |
| Hippocampal pattern separation | — | Yes | Yes |
| Narrative arc tracking | — | Yes | Yes |

### Task / Project Management

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Project context switching | Yes | — | Yes |
| Task lifecycle (active → done/failed) | Yes | — | Yes |
| Action logging per task | Yes | — | Yes |
| Solution pattern library | Yes | — | Yes |
| Artifact tracking | Yes | — | Yes |
| Project overview dashboard | Yes | — | Yes |

### LLM Integration

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Query decomposition (vague → focused) | — | Yes (Cortex) | Yes |
| Agentic memory ops (PROMOTE/DEMOTE/FORGET/UPDATE) | — | Yes (Cortex) | Yes |
| LLM-driven reflection & self-analysis | — | Yes (Cortex) | Yes |
| Context block generation for prompt injection | — | — | Yes |

### Visualization

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Memory timeline | — | Yes (VividViz) | Yes |
| Emotion distribution | — | Yes (VividViz) | Yes |
| Importance histogram | — | Yes (VividViz) | Yes |
| Narrative arc distribution | — | Yes (VividViz) | Yes |
| Drift report | — | — | Yes |
| Neurochemistry snapshot | — | — | Yes |
| Yggdrasil graph export | — | — | Yes |
| All-in-one viz payload (`viz_summary()`) | — | — | Yes |

### Security & Persistence

| Feature | VividnessMem | VividEmbed | Mímir |
|---------|:---:|:---:|:---:|
| Encryption at rest (Fernet + PBKDF2) | Yes | — | Yes |
| Atomic file writes (crash-safe) | Yes | Yes | Yes |
| Inverted word index | — | — | Yes |
| Date index for temporal queries | — | — | Yes |
| Visual memory storage (WebP) | — | — | Yes |

---

## The 21 Neuroscience Mechanisms

Every mechanism is grounded in published cognitive science research and
implemented with tuneable constants.

### 1. Flashbulb Memory *(Brown & Kulik 1977)*

High-arousal, high-importance events (importance ≥ 8, emotional arousal ≥ 0.6)
are encoded with permanent stability and vividness floors. They resist all
forms of decay — like how you remember exactly where you were on a major life
event.

### 2. Reconsolidation *(Nader et al 2000)*

Each time a memory is recalled, its emotional colour **drifts 5% toward the
agent's current mood**. Over many retrievals a sad memory can become bittersweet
— unless it's a flashbulb memory, which resists emotional drift.

### 3. State-Dependent Memory *(Godden & Baddeley 1975)*

Memories encoded during a particular emotional state are **easier to retrieve
when the agent is in that same state again**. A 0.3 vividness boost is applied
when the retrieval mood's PAD vector closely matches the encoding mood.

### 4. Spreading Activation *(Collins & Loftus 1975)*

When memories are retrieved, their content words populate a **priming buffer**.
Related concepts get an activation bonus on subsequent queries — simulating the
way thinking about "astronomy" primes "telescope" and "stars". Activation
decays by 0.8× each tick.

### 5. Retrieval-Induced Forgetting *(Anderson 1994)*

Retrieving one memory **actively suppresses** competing memories that share
≥ 70% word overlap. Their stability is reduced by 0.15 — the brain's way
of sharpening recall by inhibiting similar alternatives.

### 6. Zeigarnik Effect *(Zeigarnik 1927)*

Unresolved failures in procedural lessons are **1.5× more vivid** than
resolved ones. Incomplete tasks nag at the mind — ensuring the agent keeps
retrying failed strategies rather than forgetting them.

### 7. Involuntary Recall *(Berntsen 2009)*

On every `resonate()` call there is a **5% chance** that a random distant
memory surfaces unprompted — a Proustian flash. This keeps old memories alive
and creates natural conversational depth.

### 8. Temporal Gist Extraction *(Reyna & Brainerd 1995)*

Memories older than **90 days** are compressed to their first 15 words plus
an emotion tag. Detail fades but the emotional core survives — unless the
memory is a flashbulb, which preserves full detail indefinitely.

### 9. Temporal / Episodic Memory *(Tulving 1972)* + Prospective Memory *(Einstein & McDaniel 1990)*

Full temporal awareness:

- **Date extraction**: Parses ISO dates, US-format dates, written dates
  ("March 15th"), and relative expressions ("tomorrow", "next Tuesday") from
  every stored memory
- **Timeline navigation**: `recall_period(start, end)` retrieves all memories
  created in or mentioning dates within a window
- **Prospective memory**: Future dates with importance ≥ 4 auto-create
  reminders — the agent remembers upcoming events without being told to
- **Ambient salience**: Memories about dates near today get a recall boost
  even when the query doesn't mention dates
- **Temporal clustering**: Memories sharing date references with the query
  get a +0.08 composite-score bonus

### 10. Visual / Mental Imagery *(Kosslyn 1980)* + Dual Coding *(Paivio 1986)*

Content-addressable image storage with biologically-inspired fading:

| Tier | Vividness | What the agent "sees" |
|------|-----------|----------------------|
| **Vivid** | ≥ 0.7 | Full-resolution WebP — the agent can display it |
| **Faded** | 0.3–0.7 | Degraded WebP (quality 30) — a blurry mental image |
| **Gist only** | < 0.3 | Text description only — "I remember a sunset but can't picture it" |

Images are stored as WebP on disk (SHA-256 content-addressed), and the
**agent decides** at conversation time whether to show the image or describe
it based on the fading tier.

**Dual Coding boost**: Memories with attached images get a +0.05 recall bonus
because pictures plus words create richer episodic traces.

**Graceful fallback**: Without Pillow installed (or with `visual=False`),
`remember_visual()` silently stores `[image] {description}` as a plain text
memory.

### 11. Huginn — Thought *(Pattern Detection)*

Odin's raven of Thought scans all memories for emergent patterns the agent
never explicitly stored:

- **Entity sentiment arcs**: When 3+ impressions of a person exist, detects
  emotional trajectory (warming/cooling) and generates an insight
- **Recurring theme clusters**: Finds words appearing in 3+ distinct memories
  and names the pattern with its dominant emotion
- **Open threads**: Detects unresolved intentions ("I should…", "I need to…")
  older than 3 days that were never followed up

All insights are stored as memories with `source="huginn"` and are dedup-aware
(won't regenerate the same insight twice).

### 12. Muninn — Memory *(Consolidation Daemon)*

Odin's raven of Memory performs sleep-time consolidation:

- **Merge near-duplicates**: Memories with Jaccard word overlap ≥ 0.40 are
  merged — the richer version is kept, importance and stability are preserved
- **Prune dead memories**: Memories with vividness < 0.01 are removed (unless
  they are flashbulb, anchor, or cherished)
- **Strengthen co-activated pairs**: Memories created on the same day get a
  stability boost (×1.05) — the brain's way of reinforcing contextual links

### 13. Yggdrasil — The World Tree *(Memory Graph)*

A persistent graph connecting all memories through six edge types:

| Edge Type | Condition | Strength |
|-----------|-----------|----------|
| **Entity** | Same entity reference | 0.8 |
| **Lexical** | Word overlap 0.20–0.55 | Jaccard ratio |
| **Temporal** | Within 3-day window | 1 − (days/3) |
| **Emotional** | Same emotion label | 0.5 |
| **Task-origin** | Co-members of the same task | 0.75 |
| **Caused-lesson** | Memory ↔ lesson it spawned | 0.65 |

Additionally, LLM-**inferred** edges are discovered at encoding time when an
`llm_fn` is provided, and persisted between sessions.

Each node keeps at most 8 edges per type-competition slot, plus additive
cross-hierarchy edges. Query methods:

- `yggdrasil_roots()` — anchor, flashbulb, and importance ≥ 9 memories
- `yggdrasil_branches(memory)` — directly connected memories
- `yggdrasil_traverse(memory, depth=2)` — BFS within N hops
- `yggdrasil_path(a, b)` — shortest path between two memories

During `recall()`, retrieved memories connected to other retrieved memories
via Yggdrasil get a +0.03 bonus each — contextual association boosts recall.

### 14. Völva's Vision *(Dream Synthesis)*

During sleep, the Völva (Norse seeress) samples random memory pairs and
discovers hidden connections:

- **Emotional arcs**: Same keywords with different emotions → "My feelings
  about X shifted from Y to Z"
- **Theme bridges**: Memories 30+ days apart sharing words → long-range
  pattern recognition
- **Temporal clusters**: 3+ memories on the same day → "A lot happened on
  that day"

Dream insights are stored with `source="volva"` and surfaced in the context
block with `[dream]` tags.

### 15. Hippocampal Pattern Separation *(Yassa & Stark 2011)*

When two memories overlap ≥ 80% lexically but are **not identical**, the system
nudges their importance apart by ±1. This mirrors how the hippocampus
orthogonalises similar-but-distinct experiences to prevent interference during
retrieval.

### 16. Narrative Arc Tracking *(Freytag 1863)*

Every memory is automatically classified into a narrative position — **setup**,
**rising**, **climax**, **falling**, **resolution**, or **denouement** — using
keyword analysis and emotional arousal. This allows the system to understand
where each memory sits in the story of a conversation or relationship.

### 17. Enhanced Relational Reasoning *(LLM-Inferred Edges)*

When an `llm_fn` is provided, every new memory triggers an implicit
relationship discovery pass. The LLM examines the new memory alongside recent
memories and identifies conceptual links that pure lexical or temporal overlap
would miss — for example connecting "bought hiking boots" to "planning a
Saturday trip" even though they share no words.

Discovered edges are stored in a persistent `inferred_edges.json` and loaded
into Yggdrasil on every rebuild. Batch enrichment is available via
`enrich_yggdrasil(batch_size)` for backfilling existing memories.

### 18. Hierarchical Memory Organisation *(Cross-Hierarchy Linking)*

Episodic memories, procedural lessons, and task records now form a unified
knowledge graph instead of three siloed stores:

- **Lesson → Memory**: Every lesson tracks the `source_memory_idx` of the
  episodic memory that caused it. Yggdrasil creates `caused_lesson` edges
  between them.
- **Task → Memory**: `start_task()`, `complete_task()`, and `fail_task()` all
  record which memory indices they created, stored in `TaskRecord._memory_indices`.
  Yggdrasil creates `task_origin` edges between co-task memories.
- **Cross-hierarchy reinforcement**: When a lesson succeeds via
  `record_outcome()`, its origin memory receives a 15% stability boost —
  the brain's way of strengthening the episode that taught you something.

### 19. Mental Time Travel *(Tulving 1985)*

The `relive(memory)` method recreates the subjective experience of a past
event:

1. **Touch** — the memory's access count and vividness are updated
2. **Mood restoration** — the agent's mood is blended 60% toward the encoding
   mood, recreating the emotional state at the time of the original experience
3. **Neurochemistry trigger** — matching neurochemical events are fired
   (excitement → `achievement`, fear → `threat`, etc.)
4. **Spreading activation** — Yggdrasil activates connected memories, priming
   contextual recall
5. **Experiential context** — returns a rich dict: gist, emotion,
   original emotion, encoding mood, restored mood, arc position, flashbulb
   status, drift history, connected memories, vividness

This allows an agent to genuinely re-experience past episodes rather than
merely retrieving their text.

### 20. Novelty-Modulated Encoding *(Ranganath & Rainer 2003)*

New memories are compared against the 20 most recent memories for lexical
overlap. Highly novel memories (average similarity < 0.85) receive a **1.3×
importance boost** — the brain pays more attention to genuinely new
information. Redundant memories (similarity > 0.40) receive a **0.85×
importance penalty**. Each memory's novelty score is stored on the Memory
object for introspection.

### 21. Enhanced Drift Analysis *(Velocity + Cognitive Bias)*

Extends basic reconsolidation drift detection with two additional signals:

- **Drift velocity**: Tracks the last 5 touches of each memory to compute
  how fast its emotion is shifting — distinguishing "slowly warming" from
  "rapidly destabilising"
- **Cognitive bias detection**: When 75%+ of an entity's memories share the
  same emotional valence, a bias alert is surfaced — helping the agent
  recognise lopsided perspectives before they crystallise

Both are exposed via `drift_analysis()` which returns velocity vectors and
bias alerts alongside the standard drift report.

---

### Migration from VividnessMem

Existing agents using VividnessMem can migrate to Mimir in one call:

```python
m = Mimir.migrate_from_vividnessmem("path/to/lela_data")
```

All VividnessMem fields (content, emotion, importance, timestamp, stability,
access_count, anchor, cherished, privacy, regret, why_saved, etc.) are
preserved. Mimir-specific fields (encoding_mood, emotion_pad, mentioned_dates,
flashbulb detection) are backfilled automatically.

---

## Hybrid Retrieval Bridge

The retrieval system solves the classic RAG problem — keyword search misses
meaning while semantic search misses names and dates — by fusing both:

### Stage 1: Broad Candidate Pool

Three channels work in parallel:

- **BM25 keyword search** — IDF-weighted term matching via an inverted word
  index. Excels at proper nouns, dates, exact phrases.
- **VividEmbed semantic search** — 384-d MiniLM + PAD cosine similarity.
  Excels at themes, paraphrases, emotional resonance.
- **Date index injection** — Any dates mentioned in the query are matched
  against the temporal index, catching questions like "what happened last
  Tuesday?" that neither BM25 nor semantic would catch.

### Stage 2: Composite Re-rank

All candidates are scored on **five signals**:

| Signal | Weight | Source |
|--------|--------|--------|
| Keyword match | 0.30 | Normalized BM25 |
| Semantic similarity | 0.30 | VividEmbed cosine |
| Vividness | 0.20 | Organic decay curve |
| Mood congruence | 0.10 | PAD dot product with current mood |
| Recency | 0.10 | Exponential decay, 5-day half-life |

### Post-Composite Bonuses

| Bonus | Value | Trigger |
|-------|-------|---------|
| Cherished memory | ×1.10 | `memory._cherished` flag |
| Priming activation | +0.02/word | Words in spreading-activation buffer |
| Temporal date match | +0.08 | Query dates overlap memory dates |
| Ambient temporal salience | +0.12 | Memory dates near today |
| Dual Coding (visual) | +0.05 | Memory has attached image |
| Yggdrasil connectivity | +0.03/neighbour | Connected to other retrieved memories |

---

## Memory Types

| Type | Class | Purpose | Decay |
|------|-------|---------|-------|
| **Episodic** | `Memory` | Self-reflections, observations, experiences | Organic vividness via spaced-repetition stability |
| **Social** | `Memory` | Impressions of other entities (people, agents) | Same organic decay |
| **Procedural** | `Lesson` | Learned strategies with outcome tracking | Zeigarnik-boosted for failures |
| **Volatile** | `ShortTermFact` | Quick factual data (entity/attribute/value) | 12-hour half-life |
| **Prospective** | `Reminder` | Time-triggered future notifications | Fires once, then marks complete |
| **Visual** | `Memory` + WebP | Image attachment to any episodic memory | Kosslyn fading tiers |

---

## Organic Decay Model

Vividness is not a toggle — it's a continuous curve:

$$v(t) = \frac{\text{importance}}{10} \times e^{-t / s}$$

Where $t$ is age in days and $s$ is stability (starting at 3.0 days).

Stability grows through spaced repetition:

$$s' = \min\left(s \times b^n,\; 180\right)$$

Where $b = 1.8$ is the spacing bonus and $n$ is the retrieval count with
diminishing returns (×0.85 per retrieval). This models the well-known spacing
effect from cognitive psychology.

**Floor protections:**
- Flashbulb memories: stability ≥ 120, vividness ≥ 0.85
- Anchor memories: stability ≥ 90, vividness ≥ 0.30

---

## Neurochemistry Integration

When VividnessMem is available, its 5-neurotransmitter system modulates
Mímir's behavior:

| Modifier | Effect |
|----------|--------|
| `encoding_boost` | Multiplies importance during `remember()` |
| `attention_width` | Scales how many active memories surface |
| `mood_decay_mult` | Controls mood drift speed |
| `flashbulb` | Forces flashbulb encoding on high-chemistry events |
| `social_boost` | Amplifies social impression importance |
| `consolidation_bonus` | Enhances stability during sleep reset |

The **Emotional Audit Log** transparently records every mood shift, dampening
activation, cognitive override, visual memory storage, and life event — making
the agent's emotional trajectory inspectable and debuggable.

---

## Installation

```bash
# Core (zero required dependencies — everything degrades gracefully)
pip install vividmimir

# With the full Vivid engine stack
pip install vividmimir[all]

# Individual extras
pip install vividmimir[engines]      # VividnessMem + VividEmbed
pip install vividmimir[visual]       # Pillow for mental-imagery system
pip install vividmimir[encryption]   # Fernet encryption at rest
```

---

## Quick Start

```python
from vividmimir import Mimir

# Full system (VividnessMem + VividEmbed + Pillow)
m = Mimir(data_dir="my_agent_memory")

# Or standalone (no external dependencies)
m = Mimir(data_dir="my_agent_memory", chemistry=False, visual=False)

# Store a memory
m.remember("I had a deep conversation about philosophy today",
           emotion="curious", importance=7,
           why_saved="meaningful intellectual exchange")

# Update mood from conversation
m.update_mood(["curious", "inspired"])

# Recall with hybrid retrieval
results = m.recall("What do I remember about philosophy?")
for mem in results:
    print(f"[{mem.emotion}] {mem.content}")

# Get full context block for LLM prompt injection
context = m.get_context_block(
    current_entity="Alex",
    conversation_context="discussing favorite books"
)

# Store a visual memory (requires Pillow)
with open("sunset.jpg", "rb") as f:
    m.remember_visual(f.read(), description="Sunset over the ocean",
                      emotion="serene", importance=8)

# Time-aware retrieval
from datetime import datetime
m.recall_period(datetime(2025, 12, 1), datetime(2025, 12, 31))

# Persist everything to disk
m.save()
```

---

## Context Block

The `get_context_block()` method generates a ready-to-inject text block for
LLM system prompts. It assembles:

```
(Feeling: bittersweet)

=== THINGS ON MY MIND ===
— I love deep philosophical conversations (curious)

=== MY IMPRESSIONS OF ALEX ===
— Alex is always supportive (warm)

=== THINGS I'M LEARNING ===
— Python debugging: Use pdb [OK]

=== SOMETHING THIS REMINDS ME OF ===
— That time we talked about consciousness (fascinated)

=== IMAGES I REMEMBER ===
— [vivid] Sunset over the ocean
— [fading] The cat sleeping on the keyboard

=== TODAY / UPCOMING ===
TODAY: dentist appointment at 3pm
UPCOMING: Mom's birthday (Mar 25)
RECENTLY: finished the book club novel (Mar 19)

=== NEUROCHEMISTRY ===
dopamine: 0.63 ▲ | cortisol: 0.26 ~ | serotonin: 0.56 ~

=== EMOTIONAL AUDIT ===
~ 13:50: Mood shifted to curious after deep conversation
```

---

## Full API Reference

### Mimir Class

```python
Mimir(
    data_dir="mimir_data",
    embed_model=None,
    chemistry=True,
    visual=True,
    encryption_key=None,   # enables Fernet + PBKDF2 encryption at rest
    llm_fn=None,           # callable(prompt: str) → str for LLM features
)
```

#### Core Methods

| Method | Description |
|--------|-------------|
| `remember(content, emotion, importance, source, why_saved)` | Store episodic memory with dedup, flashbulb detection, VividEmbed sync |
| `remember_visual(image_data, description, emotion, importance, ...)` | Store visual memory with compressed WebP attachment |
| `get_visual(memory)` → dict | Retrieve image bytes with fading applied per vividness tier |
| `forget_visual(memory)` → bool | Remove image attachment, keep text description |
| `recall(context, limit, mood)` → list | Hybrid BM25 + semantic retrieval with 5-signal re-rank |
| `recall_unified(context, limit)` → dict | Cross-type retrieval: reflections, impressions, facts, lessons in one call |
| `resonate(context, limit)` → list | `recall()` + retrieval-induced forgetting + involuntary recall |
| `recall_period(start, end, limit)` → list | Timeline navigation by date range |
| `get_active_self(context)` → list | Top-K self-memories weighted by mood and context |
| `get_context_block(current_entity, conversation_context)` → str | Full memory context for LLM prompt injection |
| `update_mood(emotions)` | EMA-blend mood toward emotion labels |
| `bump_session()` → int | Increment session counter, return new count |
| `save()` | Persist all data to disk |
| `stats()` → dict | Summary of memory system state |
| `migrate_from_vividnessmem(src_dir, dest_dir)` | Class method: import all data from VividnessMem |

#### Task / Project Branch

| Method | Description |
|--------|-------------|
| `set_active_project(name)` | Set or switch the active project context |
| `start_task(description, priority, project)` → TaskRecord | Create task with Zeigarnik anchor |
| `complete_task(task_id, outcome)` → bool | Mark task completed, release Zeigarnik tension |
| `fail_task(task_id, reason)` → bool | Mark task failed, create lesson |
| `get_active_tasks()` → list | Currently active tasks |
| `log_action(task_id, action, result, error, fix)` → ActionRecord | Log per-task action |
| `record_solution(problem, solution, importance)` → SolutionPattern | Store reusable problem→solution |
| `find_solutions(problem, top_k)` → list | BM25-matched solutions with reuse boost |
| `track_artifact(name, artifact_type, description, importance)` → ArtifactRecord | Track project artifact |
| `update_artifact(name, **updates)` → bool | Update artifact fields |
| `get_project_overview()` → dict | Full project state snapshot |

#### LLM Integration (optional)

| Method | Description |
|--------|-------------|
| `decompose_query(query)` → list[str] | Break vague query into 2-4 focused sub-queries |
| `edit_memories(instruction)` → dict | LLM-driven PROMOTE/DEMOTE/FORGET/UPDATE |
| `reflect()` → str | Periodic self-analysis of memory patterns & emotional trends |

#### Neuroscience & Graph

| Method | Description |
|--------|-------------|
| `huginn()` → list[Memory] | Pattern detection: entity arcs, recurring themes, open threads |
| `muninn()` → dict | Consolidation: merge duplicates, prune dead, strengthen co-activated |
| `volva_dream(n_samples)` → list[Memory] | Dream synthesis from random memory pairs |
| `sleep_reset(hours)` | Full between-session cycle: chemistry reset + Muninn + Huginn + Völva + Yggdrasil rebuild |
| `detect_drift(include_reframed)` → list | Find memories with significant emotional drift |
| `drift_analysis()` → dict | Enhanced drift: velocity vectors, cognitive bias alerts |
| `decay_priming()` | Decay the spreading-activation buffer by one tick |
| `yggdrasil_roots()` → list | Anchor, flashbulb, and high-importance identity memories |
| `yggdrasil_branches(memory)` → list | Direct neighbours in the memory graph |
| `yggdrasil_traverse(memory, depth)` → list | BFS traversal within N hops |
| `yggdrasil_path(a, b)` → list | Shortest path between two memories |
| `relive(memory)` → dict | Mental time travel — re-experience with mood restoration + Yggdrasil activation |
| `enrich_yggdrasil(batch_size)` → int | Batch LLM enrichment of memories without inferred edges |

#### Visualization

| Method | Description |
|--------|-------------|
| `memory_timeline()` → list[dict] | Chronological memory data for plotting |
| `emotion_distribution()` → dict | Memories counted by emotion |
| `importance_histogram()` → dict | Distribution across importance levels 1-10 |
| `arc_distribution()` → dict | Memories by narrative arc position |
| `drift_report()` → list[dict] | Emotionally drifted memories with magnitude |
| `neurochemistry_snapshot()` → dict | Current neurotransmitter state |
| `yggdrasil_graph()` → dict | Adjacency list export for graph visualization |
| `viz_summary()` → dict | All-in-one visualization payload |

#### Social & Procedural

| Method | Description |
|--------|-------------|
| `add_social_impression(entity, content, emotion, importance, why_saved)` | Store social memory |
| `add_lesson(topic, context_trigger, strategy, importance, source_memory_idx)` | Create procedural memory (optionally linked to origin memory) |
| `record_outcome(lesson_id, action, result, diagnosis)` | Log lesson application result |
| `get_active_lessons()` → list | Lessons ranked by vividness (Zeigarnik-boosted) |
| `add_fact(entity, attribute, value)` | Store volatile fact (12h decay) |
| `get_facts(entity)` → list | Return vivid facts, optionally filtered |

#### Emotional Control

| Method | Description |
|--------|-------------|
| `on_event(event_type, intensity)` | Signal life event to neurochemistry (10 event types) |
| `request_dampening(turns, intensity)` | Activate emotional self-regulation |
| `end_dampening()` | Manual dampening termination |
| `tick_dampening()` | Advance dampening by one turn |
| `cognitive_override(emotion, intensity)` | Deliberate emotional reappraisal |

#### Memory Curation

| Method | Description |
|--------|-------------|
| `promote_to_anchor(memory)` | Mark as formative (resists decay permanently) |
| `cherish(memory)` | Mark as sentimental favourite (1.1× recall boost) |
| `uncherish(memory)` | Remove cherished status |
| `reflect_on_cherished()` → list | Revisit cherished memories |
| `reframe(memory, new_emotion, reason)` → bool | Deliberate emotional reframe (records original, marks intentional) |
| `update_importance(memory, new_importance)` | Update + sync to VividEmbed |
| `query_by_emotion(emotion, top_k, min_importance)` | Emotion-space search via VividEmbed |
| `find_contradictions(text, emotion, threshold)` | Find semantically similar but emotionally opposite memories |

#### Temporal Awareness

| Method | Description |
|--------|-------------|
| `recall_period(start, end, limit)` | Retrieve memories from a time window |
| `get_temporal_context(now, lookahead, lookbehind)` | Proactive surfacing: today/upcoming/recent |
| `set_reminder(text, hours)` | Create time-triggered notification |
| `get_due_reminders()` → list | Return reminders that have fired |

---

## Dependencies

| Package | Required? | Purpose |
|---------|-----------|---------|
| Python ≥ 3.10 | Yes | Core language |
| `vividnessmem` | Optional | Neurochemistry engine (5 neurotransmitters, emotional audit) |
| `vividembed` | Optional | Semantic retrieval (389-d hybrid vectors) |
| `Pillow` | Optional | Visual memory (image compression/decompression) |
| `cryptography` | Optional | Encryption at rest (Fernet + PBKDF2, 600k iterations) |
All optional dependencies use graceful fallback — Mímir works standalone.

---

## Test Suites

| Suite | Tests | Coverage |
|-------|-------|----------|
| `_test_neuroscience.py` | 26 | All 8 core mechanisms + persistence + context block |
| `_test_temporal_memory.py` | 28 | Date extraction, timeline navigation, prospective memory |
| `_test_temporal_awareness.py` | 14 | Ambient salience, temporal context surfacing |
| `_test_integration.py` | 27 | VividnessMem + VividEmbed full integration |
| `_test_visual_memory.py` | 81 | Visual storage, fading tiers, dual coding, persistence |
| **Total** | **176** | **All passing** |

---

## Architecture Notes

- **Slots-based Memory**: 27-slot `__slots__` on the `Memory` class prevents
  arbitrary attributes and optimizes memory layout
- **Content-addressable storage**: Visual images indexed by SHA-256 hash —
  identical images share one file
- **Atomic persistence**: JSON files written via atomic temp-file + rename
  pattern to prevent corruption on crash
- **Inverted indexes**: Word index for BM25, date index for temporal queries —
  both rebuilt on load
- **60-emotion PAD space**: Full Pleasure-Arousal-Dominance mapping for
  fine-grained emotion tracking beyond simple sentiment labels

---

## License

[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for personal and research use. Commercial use requires a separate license.

Part of the Vivid ecosystem by [Kronic90](https://github.com/Kronic90).

| Package | PyPI | License |
|---|---|---|
| [VividnessMem](https://pypi.org/project/vividnessmem/) | `pip install vividnessmem` | MIT |
| [VividEmbed](https://pypi.org/project/vividembed/) | `pip install vividembed` | PolyForm-NC |
| **Mímir** | `pip install vividmimir` | PolyForm-NC |
