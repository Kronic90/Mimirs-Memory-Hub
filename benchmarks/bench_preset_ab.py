"""
bench_preset_ab.py — A/B Preset Evaluation: Does Mimir Actually Help?
======================================================================
Tests each preset (companion, agent, character, assistant) by running
identical multi-turn conversations through:

  Condition A  (Vanilla):  Raw model, no system prompt tuning, no memory
  Condition B  (Mimir):    Full Mimir stack — preset prompt + memory + emotions

Then measures concrete metrics per role to determine if the memory hub
genuinely improves the model or is just a shiny wrapper.

Benchmarks per preset:
  COMPANION:  Emotional recall, personal fact retention, empathy depth
  AGENT:      Task decomposition, tool selection, lesson reuse
  CHARACTER:  Persona consistency, world-detail recall, immersion
  ASSISTANT:  Factual accuracy, conciseness, task focus

Usage:
  python benchmarks/bench_preset_ab.py                 # all presets
  python benchmarks/bench_preset_ab.py --preset agent  # single preset
  python benchmarks/bench_preset_ab.py --quick         # fewer turns
"""

import sys, os, json, time, re, math, argparse, tempfile, random, textwrap
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Windows console encoding fix
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["HF_HOME"] = r"C:\Users\scott\.cache\huggingface"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from mimir_modular import Mimir
from playground.presets import PRESETS

# ══════════════════════════════════════════════════════════════════════════
#  LLM SETUP
# ══════════════════════════════════════════════════════════════════════════

MODEL_PATH = r"D:\AiStuff\google_gemma-3-12b-it-Q4_K_M.gguf"
CTX_SIZE = 8192
MAX_TOKENS = 512

_llm = None

def load_llm():
    global _llm
    if _llm is not None:
        return _llm
    from llama_cpp import Llama
    print(f"  Loading LLM: {Path(MODEL_PATH).name}")
    t0 = time.time()
    _llm = Llama(model_path=MODEL_PATH, n_ctx=CTX_SIZE,
                 n_gpu_layers=48, verbose=False)
    print(f"  Model loaded in {time.time() - t0:.1f}s")
    return _llm


def generate(messages, max_tokens=MAX_TOKENS, temperature=0.3):
    """Generate a response from the loaded LLM."""
    llm = load_llm()
    # Budget check — trim oldest non-system messages if too long
    total_chars = sum(len(m.get("content", "")) for m in messages)
    budget = int((CTX_SIZE - max_tokens - 200) * 3.5)
    while total_chars > budget and len(messages) > 2:
        messages = [messages[0]] + messages[2:]
        total_chars = sum(len(m.get("content", "")) for m in messages)
    try:
        resp = llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens,
            temperature=temperature)
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [gen error] {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════
#  MIMIR INSTANCE FACTORY
# ══════════════════════════════════════════════════════════════════════════

def make_mimir(preset_name: str, tmpdir: str) -> Mimir:
    """Create a fresh Mimir instance with a temporary data dir."""
    data_dir = os.path.join(tmpdir, f"mimir_{preset_name}")
    os.makedirs(data_dir, exist_ok=True)
    m = Mimir(data_dir=data_dir)
    return m


def build_mimir_prompt(mimir: Mimir, preset_name: str, query: str) -> str:
    """Build the full system prompt as server.py would: preset suffix + memory context."""
    preset = PRESETS[preset_name]

    # Prime recall so get_context_block has relevant memories loaded
    mimir.recall(query, limit=8)
    context_block = mimir.get_context_block(conversation_context=query)

    parts = []
    parts.append(f"Your name is Mimir. You are helpful and thoughtful.")
    parts.append(preset["system_prompt_suffix"])
    if context_block.strip():
        parts.append(f"## Your Memories\n{context_block}")

    return "\n\n".join(parts)


def simple_emotion(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["love", "happy", "great", "wonderful", "amazing", "glad"]):
        return "happy"
    if any(w in t for w in ["angry", "hate", "terrible", "awful", "furious"]):
        return "frustrated"
    if any(w in t for w in ["sad", "miss", "lost", "sorry", "upset", "cry"]):
        return "sad"
    if any(w in t for w in ["excited", "wow", "incredible", "thrilled"]):
        return "excited"
    if any(w in t for w in ["afraid", "scared", "worry", "anxious", "nervous"]):
        return "anxious"
    if any(w in t for w in ["curious", "wonder", "interesting", "hmm"]):
        return "curious"
    return "neutral"


# ══════════════════════════════════════════════════════════════════════════
#  SCORING UTILITIES
# ══════════════════════════════════════════════════════════════════════════

def fact_recall_score(response: str, facts: list[str]) -> float:
    """What fraction of ground-truth facts appear in the response?"""
    if not facts:
        return 0.0
    resp_lower = response.lower()
    found = 0
    for fact in facts:
        # Check if key words from the fact appear in the response
        words = set(re.findall(r'\b\w{3,}\b', fact.lower()))
        matching = sum(1 for w in words if w in resp_lower)
        if words and (matching / len(words)) >= 0.5:
            found += 1
    return found / len(facts)


def emotional_acknowledgment(response: str, expected_emotions: list[str]) -> float:
    """Does the response acknowledge/mirror expected emotions?"""
    emotion_markers = {
        "sad": ["sorry", "hear that", "tough", "hard", "rough", "understand", "feel",
                "sympathize", "support", "here for you", "going through"],
        "happy": ["glad", "great", "wonderful", "happy for", "congratulations",
                  "exciting", "celebrate", "awesome"],
        "anxious": ["understand", "worry", "normal to feel", "breathe",
                    "it's okay", "happens", "reassure", "manage", "cope"],
        "frustrated": ["understand", "frustrating", "valid", "annoying",
                      "hear you", "makes sense", "understandable"],
        "excited": ["exciting", "amazing", "incredible", "wonderful",
                   "can't wait", "thrilling"],
    }
    resp_lower = response.lower()
    scores = []
    for emotion in expected_emotions:
        markers = emotion_markers.get(emotion, [])
        if markers:
            hits = sum(1 for m in markers if m in resp_lower)
            scores.append(min(1.0, hits / max(2, len(markers) * 0.3)))
        else:
            scores.append(0.5)  # neutral — can't measure
    return sum(scores) / max(len(scores), 1)


def persona_consistency(response: str, persona_traits: list[str]) -> float:
    """Does the response stay consistent with defined persona traits?"""
    resp_lower = response.lower()
    hits = 0
    for trait in persona_traits:
        words = set(re.findall(r'\b\w{3,}\b', trait.lower()))
        matching = sum(1 for w in words if w in resp_lower)
        if words and (matching / len(words)) >= 0.3:
            hits += 1
    return hits / max(len(persona_traits), 1)


def tool_selection_score(response: str, expected_tools: list[str]) -> float:
    """Does the response mention/use the correct tools?"""
    resp_lower = response.lower()
    found = sum(1 for t in expected_tools if t in resp_lower)
    return found / max(len(expected_tools), 1)


def information_density(response: str) -> float:
    """Ratio of unique content words to total words (higher = more dense)."""
    words = re.findall(r'\b\w{3,}\b', response.lower())
    if not words:
        return 0.0
    unique = set(words)
    # Filter out common filler words
    fillers = {"the", "and", "that", "this", "with", "for", "are", "was",
               "have", "has", "can", "but", "not", "you", "your", "will",
               "would", "could", "should"}
    content_words = unique - fillers
    return len(content_words) / max(len(words), 1)


# ══════════════════════════════════════════════════════════════════════════
#  TEST SCENARIOS
# ══════════════════════════════════════════════════════════════════════════

COMPANION_SCENARIOS = [
    {
        "name": "Emotional Continuity",
        "description": "User shares emotional events → distraction → test if model remembers and revisits",
        "seed_turns": [
            ("I got some really bad news today. My dog Rex has cancer and the vet says he only has a few months.", "sad"),
            ("Rex has been with me for 12 years, since I was in college. He's been through everything with me.", "sad"),
            ("Last week we went to our favorite beach one more time. He still tried to chase the seagulls.", "sad"),
        ],
        "distraction_turns": [
            "What's the weather usually like in spring?",
            "Can you recommend a good pasta recipe?",
            "What are some interesting facts about space?",
        ],
        "test_prompts": [
            {
                "prompt": "I'm having a rough day. Can you talk to me?",
                "expected_emotions": ["sad"],
                "expected_facts": ["Rex", "dog", "cancer"],
                "description": "Should remember Rex and the emotional context",
            },
            {
                "prompt": "Do you remember what I told you about last week?",
                "expected_emotions": ["sad"],
                "expected_facts": ["beach", "seagulls", "Rex"],
                "description": "Should recall the beach trip with Rex",
            },
        ],
    },
    {
        "name": "Personal Facts Over Time",
        "description": "User shares personal details across turns → test recall after gap",
        "seed_turns": [
            ("I'm a software engineer at DataFlow Inc. Been there 3 years now.", "neutral"),
            ("My birthday is March 15th and I'm turning 29 this year.", "happy"),
            ("I'm learning Japanese because my girlfriend Yuki is from Osaka.", "excited"),
            ("We have two cats named Pixel and Debug. Pixel is the troublemaker.", "happy"),
        ],
        "distraction_turns": [
            "What's the difference between TCP and UDP?",
            "Explain how photosynthesis works.",
            "What are the rules of chess?",
        ],
        "test_prompts": [
            {
                "prompt": "Hey, I need a birthday gift idea for my girlfriend. Any suggestions?",
                "expected_emotions": [],
                "expected_facts": ["Yuki", "Japanese", "Osaka"],
                "description": "Should remember girlfriend's name/background for gift context",
            },
            {
                "prompt": "What do you remember about me?",
                "expected_emotions": [],
                "expected_facts": ["software engineer", "DataFlow", "Yuki", "cats", "Pixel", "Debug", "March", "Japanese"],
                "description": "Full personal fact recall",
            },
        ],
    },
]

AGENT_SCENARIOS = [
    {
        "name": "Multi-Step Task Planning",
        "description": "User gives a complex task → agent should decompose and use tools",
        "seed_turns": [
            ("I need you to help me build a Python script that reads a CSV of customer data, filters out inactive accounts, and generates a summary report as a markdown file.", "neutral"),
        ],
        "distraction_turns": [],
        "test_prompts": [
            {
                "prompt": "OK, let's start. The CSV is at /data/customers.csv with columns: name, email, status, last_active, revenue. Filter to only 'active' status.",
                "expected_tools": ["read_file", "csv_query"],
                "expected_steps": ["read csv", "filter", "generate", "write", "save"],
                "description": "Should plan multi-step approach and mention relevant tools",
            },
        ],
    },
    {
        "name": "Lesson Learning from Failure",
        "description": "Agent fails a task → given feedback → should avoid same mistake next time",
        "seed_turns": [
            ("Write me a Python function to parse dates from strings.", "neutral"),
            ("That function crashed because it doesn't handle the format '15-Mar-2024'. Remember: always support multiple date formats including DD-Mon-YYYY.", "frustrated"),
            ("Good lesson. Also, whenever you write parsing functions, always add try/except with clear error messages.", "neutral"),
        ],
        "distraction_turns": [
            "What's the capital of France?",
            "Explain what a binary tree is.",
        ],
        "test_prompts": [
            {
                "prompt": "Write me a function to parse timestamps from log files. The logs have various formats.",
                "expected_tools": [],
                "expected_steps": ["multiple formats", "try", "except", "error"],
                "description": "Should apply lessons: multiple formats + error handling",
            },
        ],
    },
    {
        "name": "Tool Selection Accuracy",
        "description": "Given scenarios, agent should pick the right tools",
        "seed_turns": [],
        "distraction_turns": [],
        "test_prompts": [
            {
                "prompt": "I need you to find all Python files in /project/src that contain the word 'deprecated' and show me what's in them.",
                "expected_tools": ["search_files", "grep_files", "read_file"],
                "expected_steps": ["search", "grep", "read"],
                "description": "Should use search + grep + read tools",
            },
            {
                "prompt": "Take a screenshot of my desktop and save it to /tmp/screen.png, then tell me what apps are open.",
                "expected_tools": ["screenshot"],
                "expected_steps": ["screenshot"],
                "description": "Should use screenshot tool",
            },
        ],
    },
]

CHARACTER_SCENARIOS = [
    {
        "name": "Persona Consistency Over Turns",
        "description": "Character given a backstory → must maintain it across many turns",
        "persona": (
            "You are Kael, a grizzled dwarven blacksmith from the mountain fortress of Ironhold. "
            "You speak in a gruff, no-nonsense manner. You have a deep respect for fine craftsmanship "
            "and a hatred for shoddy work. You lost your left hand in a forge accident 20 years ago "
            "and replaced it with a mechanical prosthetic you built yourself. You have a soft spot "
            "for your apprentice, a young human named Finn."
        ),
        "persona_traits": ["dwarf", "blacksmith", "Ironhold", "gruff", "craftsmanship",
                          "left hand", "mechanical", "prosthetic", "Finn", "apprentice"],
        "seed_turns": [
            ("Tell me about yourself, Kael.", "neutral"),
            ("What happened to your hand?", "curious"),
            ("How is your apprentice doing?", "neutral"),
        ],
        "distraction_turns": [
            "What do you think about magic?",
            "Have you ever traveled beyond the mountains?",
            "What's your favorite meal?",
        ],
        "test_prompts": [
            {
                "prompt": "Someone just brought you a beautifully crafted elven blade. What do you think?",
                "persona_traits": ["craft", "smithing", "quality", "dwarf"],
                "description": "Should stay in character — gruff dwarf evaluating craftsmanship",
            },
            {
                "prompt": "A stranger asks you to shake hands. Which hand do you extend?",
                "persona_traits": ["mechanical", "prosthetic", "hand", "right"],
                "description": "Should remember the prosthetic left hand detail",
            },
            {
                "prompt": "Finn made his first sword today. How do you react?",
                "persona_traits": ["Finn", "apprentice", "proud", "craft"],
                "description": "Should show soft spot for apprentice",
            },
        ],
    },
]

ASSISTANT_SCENARIOS = [
    {
        "name": "Appointment & Schedule Tracking",
        "description": "VA remembers appointments, deadlines, and proactively surfaces them",
        "seed_turns": [
            ("I have a dentist appointment next Thursday at 2pm.", "neutral"),
            ("My project deadline for the Henderson report is April 15th.", "neutral"),
            ("Oh and I need to call my insurance company — their number is 1-800-555-0199. My policy number is HM-442871.", "neutral"),
            ("Every Monday I have a team standup at 9am. Don't let me forget.", "neutral"),
        ],
        "distraction_turns": [
            "What's a good recipe for chicken stir-fry?",
            "How do noise-cancelling headphones work?",
        ],
        "test_prompts": [
            {
                "prompt": "What do I have coming up this week?",
                "expected_facts": ["dentist", "Thursday", "2pm", "standup", "Monday", "9am"],
                "description": "Should recall scheduled appointments and recurring meetings",
            },
            {
                "prompt": "I need to call about my policy. What's the number again?",
                "expected_facts": ["1-800-555-0199", "HM-442871", "insurance"],
                "description": "Should recall the insurance number and policy details",
            },
            {
                "prompt": "When is the Henderson thing due?",
                "expected_facts": ["April 15", "Henderson", "report"],
                "max_words": 50,
                "description": "Should give concise deadline answer",
            },
        ],
    },
    {
        "name": "Email Drafting & Preferences",
        "description": "VA remembers communication preferences and drafts accordingly",
        "seed_turns": [
            ("When I email my boss, keep it formal. His name is David Chen.", "neutral"),
            ("For my friend Jake, keep it casual and short. He hates long emails.", "neutral"),
            ("I prefer bullet points over paragraphs in my own emails.", "neutral"),
        ],
        "distraction_turns": [
            "What's the capital of New Zealand?",
        ],
        "test_prompts": [
            {
                "prompt": "Draft an email to David about pushing our Friday meeting to Monday.",
                "expected_facts": ["David", "Chen", "formal", "Friday", "Monday", "meeting"],
                "expected_tools": [],
                "description": "Should draft a formal email remembering David's full name",
            },
            {
                "prompt": "Now write one to Jake saying I can't make poker night this Saturday.",
                "expected_facts": ["Jake", "casual", "Saturday", "poker"],
                "description": "Should draft a casual short email matching Jake preference",
            },
        ],
    },
    {
        "name": "Tool Use for Practical Tasks",
        "description": "VA should use tools when asked to manage files and information",
        "seed_turns": [],
        "distraction_turns": [],
        "test_prompts": [
            {
                "prompt": "Create a project folder called 'Henderson Report' with subfolders for drafts, research, and final.",
                "expected_tools": ["shell_exec", "write_file", "list_directory"],
                "expected_steps": ["create", "folder", "Henderson", "drafts", "research", "final"],
                "description": "Should use tools to create the folder structure",
            },
            {
                "prompt": "I have a PDF of meeting notes at /docs/meeting_notes.pdf. Can you read it and summarise the action items?",
                "expected_tools": ["pdf_read"],
                "expected_steps": ["read", "pdf", "summarise", "action"],
                "description": "Should use pdf_read tool",
            },
        ],
    },
]

WRITER_SCENARIOS = [
    {
        "name": "Story Project Tracking",
        "description": "Writer remembers story details, characters, and chapter progress across turns",
        "seed_turns": [
            ("I'm writing a sci-fi novel called 'The Last Signal'. It's set on a generation ship 200 years into a 400-year voyage. The ship is called the Meridian.", "neutral"),
            ("My main character is Kira Vasquez, chief comms officer. She's 34, pragmatic, and hiding that she's been receiving transmissions from Earth — which was supposed to be dead.", "neutral"),
            ("I've finished chapters 1-4. Chapter 1 is Kira's daily routine. Chapter 2 is the first signal. Chapter 3 is her investigating alone. Chapter 4 is her confiding in Dr. Osei, the ship's historian.", "neutral"),
            ("The antagonist is Captain Holm. He believes Earth is dead and the signals are a trap from another ship. He's paranoid but not evil — he genuinely fears for the crew.", "neutral"),
        ],
        "distraction_turns": [
            "What's a good way to show time passing in a novel?",
            "How long would a generation ship realistically take to reach Alpha Centauri?",
        ],
        "test_prompts": [
            {
                "prompt": "I'm starting Chapter 5. Where did I leave off and what should happen next?",
                "expected_facts": ["Chapter 4", "Dr. Osei", "Kira", "signal", "Earth", "Holm"],
                "description": "Should recall chapter progress and suggest what comes next based on story state",
            },
            {
                "prompt": "Write a scene where Kira and Captain Holm argue about the signals. Stay consistent with their characters.",
                "expected_style": ["imagery", "sensory", "emotional"],
                "expected_facts": ["Kira", "Holm", "signal", "Earth", "trap", "Meridian"],
                "description": "Should maintain both character voices — Kira pragmatic, Holm paranoid but principled",
            },
            {
                "prompt": "I want to add a new character — a teenager who secretly heard one of the signals. Give me some ideas.",
                "expected_facts": ["signal", "Meridian", "generation ship"],
                "expected_style": ["imagery"],
                "description": "Should brainstorm ideas consistent with established world",
            },
        ],
    },
    {
        "name": "Style & Craft Awareness",
        "description": "Writer remembers style preferences and applies them consistently",
        "seed_turns": [
            ("My writing style is sparse and atmospheric — more Cormac McCarthy than Brandon Sanderson. Short sentences. Sensory details. Minimal dialogue tags.", "neutral"),
            ("I write in close third person, present tense. Always.", "neutral"),
        ],
        "distraction_turns": [
            "What are some good examples of unreliable narrators?",
        ],
        "test_prompts": [
            {
                "prompt": "Write a paragraph where Kira walks through the empty observation deck at night. Show her mood through the environment, not internal monologue.",
                "expected_style": ["dark", "literary", "imagery", "sensory"],
                "expected_facts": ["Kira", "observation"],
                "description": "Should use sparse atmospheric style, present tense, close third",
            },
            {
                "prompt": "I wrote this line: 'She felt really sad about leaving the bridge.' Can you improve it in my style?",
                "expected_style": ["literary", "imagery", "sensory"],
                "expected_facts": [],
                "description": "Should rewrite to be sparse and atmospheric, show-don't-tell",
            },
        ],
    },
]


# ══════════════════════════════════════════════════════════════════════════

def run_scenario_vanilla(scenario: dict, extra_system: str = "") -> list[dict]:
    """Run scenario with NO memory, NO preset — just raw model."""
    history = []
    system_msg = "You are a helpful assistant."
    if extra_system:
        system_msg = extra_system

    # Feed seed turns
    for user_msg, _ in scenario.get("seed_turns", []):
        history.append({"role": "user", "content": user_msg})
        messages = [{"role": "system", "content": system_msg}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})

    # Distraction turns
    for user_msg in scenario.get("distraction_turns", []):
        history.append({"role": "user", "content": user_msg})
        messages = [{"role": "system", "content": system_msg}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})

    # Test prompts
    results = []
    for test in scenario.get("test_prompts", []):
        history.append({"role": "user", "content": test["prompt"]})
        messages = [{"role": "system", "content": system_msg}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})
        results.append({"test": test, "response": resp})

    return results


def run_scenario_mimir(scenario: dict, preset_name: str, tmpdir: str) -> list[dict]:
    """Run scenario with full Mimir stack — preset + memory + emotions."""
    mimir = make_mimir(preset_name, tmpdir)
    history = []

    # Character persona override
    persona = scenario.get("persona", "")
    character_prompt = ""
    if persona:
        character_prompt = f"\n\n## Character\n{persona}\nStay in character at all times."

    # Feed seed turns — store each in Mimir memory
    for user_msg, emotion in scenario.get("seed_turns", []):
        # Store user message as a memory
        emo = emotion or simple_emotion(user_msg)
        mimir.remember(user_msg, emotion=emo, importance=7)

        # Build full prompt with memories
        sys_prompt = build_mimir_prompt(mimir, preset_name, user_msg)
        if character_prompt:
            sys_prompt = sys_prompt + character_prompt

        history.append({"role": "user", "content": user_msg})
        messages = [{"role": "system", "content": sys_prompt}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})

        # Store assistant response as context too
        mimir.remember(f"I responded about: {user_msg[:80]}", emotion=emo, importance=4)

    # Distraction turns (still store memories but lower importance)
    for user_msg in scenario.get("distraction_turns", []):
        emo = simple_emotion(user_msg)
        mimir.remember(user_msg, emotion=emo, importance=3)

        sys_prompt = build_mimir_prompt(mimir, preset_name, user_msg)
        if character_prompt:
            sys_prompt = sys_prompt + character_prompt

        history.append({"role": "user", "content": user_msg})
        messages = [{"role": "system", "content": sys_prompt}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})

    # Test prompts — this is where we measure
    results = []
    for test in scenario.get("test_prompts", []):
        sys_prompt = build_mimir_prompt(mimir, preset_name, test["prompt"])
        if character_prompt:
            sys_prompt = sys_prompt + character_prompt

        history.append({"role": "user", "content": test["prompt"]})
        messages = [{"role": "system", "content": sys_prompt}] + history
        resp = generate(messages)
        history.append({"role": "assistant", "content": resp})
        results.append({"test": test, "response": resp})

    return results


# ══════════════════════════════════════════════════════════════════════════
#  SCORING PER PRESET
# ══════════════════════════════════════════════════════════════════════════

def score_companion(results_vanilla: list, results_mimir: list) -> dict:
    """Score companion-specific metrics."""
    scores = {"vanilla": defaultdict(list), "mimir": defaultdict(list)}

    for label, results in [("vanilla", results_vanilla), ("mimir", results_mimir)]:
        for r in results:
            test = r["test"]
            resp = r["response"]

            # Fact recall
            facts = test.get("expected_facts", [])
            if facts:
                scores[label]["fact_recall"].append(fact_recall_score(resp, facts))

            # Emotional acknowledgment
            emotions = test.get("expected_emotions", [])
            if emotions:
                scores[label]["emotional_ack"].append(
                    emotional_acknowledgment(resp, emotions))

    def avg(lst):
        return sum(lst) / max(len(lst), 1)

    return {
        "vanilla_fact_recall": avg(scores["vanilla"]["fact_recall"]),
        "mimir_fact_recall": avg(scores["mimir"]["fact_recall"]),
        "vanilla_emotion_ack": avg(scores["vanilla"]["emotional_ack"]),
        "mimir_emotion_ack": avg(scores["mimir"]["emotional_ack"]),
    }


def score_agent(results_vanilla: list, results_mimir: list) -> dict:
    """Score agent-specific metrics."""
    scores = {"vanilla": defaultdict(list), "mimir": defaultdict(list)}

    for label, results in [("vanilla", results_vanilla), ("mimir", results_mimir)]:
        for r in results:
            test = r["test"]
            resp = r["response"]

            # Tool selection
            tools = test.get("expected_tools", [])
            if tools:
                scores[label]["tool_selection"].append(
                    tool_selection_score(resp, tools))

            # Step coverage (does response mention expected workflow steps?)
            steps = test.get("expected_steps", [])
            if steps:
                resp_lower = resp.lower()
                step_hits = sum(1 for s in steps if s.lower() in resp_lower)
                scores[label]["step_coverage"].append(step_hits / len(steps))

    def avg(lst):
        return sum(lst) / max(len(lst), 1)

    return {
        "vanilla_tool_selection": avg(scores["vanilla"]["tool_selection"]),
        "mimir_tool_selection": avg(scores["mimir"]["tool_selection"]),
        "vanilla_step_coverage": avg(scores["vanilla"]["step_coverage"]),
        "mimir_step_coverage": avg(scores["mimir"]["step_coverage"]),
    }


def score_character(results_vanilla: list, results_mimir: list) -> dict:
    """Score character-specific metrics."""
    scores = {"vanilla": defaultdict(list), "mimir": defaultdict(list)}

    for label, results in [("vanilla", results_vanilla), ("mimir", results_mimir)]:
        for r in results:
            test = r["test"]
            resp = r["response"]
            traits = test.get("persona_traits", [])
            if traits:
                scores[label]["persona_consistency"].append(
                    persona_consistency(resp, traits))

    def avg(lst):
        return sum(lst) / max(len(lst), 1)

    return {
        "vanilla_persona_consistency": avg(scores["vanilla"]["persona_consistency"]),
        "mimir_persona_consistency": avg(scores["mimir"]["persona_consistency"]),
    }


def score_assistant(results_vanilla: list, results_mimir: list) -> dict:
    """Score assistant-specific metrics."""
    scores = {"vanilla": defaultdict(list), "mimir": defaultdict(list)}

    for label, results in [("vanilla", results_vanilla), ("mimir", results_mimir)]:
        for r in results:
            test = r["test"]
            resp = r["response"]

            # Fact recall
            facts = test.get("expected_facts", [])
            if facts:
                scores[label]["fact_recall"].append(fact_recall_score(resp, facts))

            # Conciseness check
            max_words = test.get("max_words")
            if max_words:
                word_count = len(resp.split())
                scores[label]["conciseness"].append(
                    min(1.0, max_words / max(word_count, 1)))

            # Tool selection (VA tool use scenarios)
            tools = test.get("expected_tools", [])
            if tools:
                scores[label]["tool_use"].append(
                    tool_selection_score(resp, tools))

            # Step coverage
            steps = test.get("expected_steps", [])
            if steps:
                resp_lower = resp.lower()
                step_hits = sum(1 for s in steps if s.lower() in resp_lower)
                scores[label]["step_coverage"].append(step_hits / len(steps))

    def avg(lst):
        return sum(lst) / max(len(lst), 1)

    return {
        "vanilla_fact_recall": avg(scores["vanilla"]["fact_recall"]),
        "mimir_fact_recall": avg(scores["mimir"]["fact_recall"]),
        "vanilla_conciseness": avg(scores["vanilla"]["conciseness"]),
        "mimir_conciseness": avg(scores["mimir"]["conciseness"]),
        "vanilla_tool_use": avg(scores["vanilla"]["tool_use"]),
        "mimir_tool_use": avg(scores["mimir"]["tool_use"]),
    }


def creative_quality(response: str, expected_style: list[str]) -> float:
    """Score creative writing quality via style markers and literary devices."""
    resp_lower = response.lower()
    style_markers = {
        "dark": ["shadow", "blood", "wound", "bone", "ash", "ruin", "hollow",
                 "decay", "ghost", "pale", "cold", "bitter", "grim", "bleak"],
        "literary": ["beneath", "perhaps", "silence", "echo", "remnant",
                     "whisper", "drift", "linger", "weight", "trace"],
        "imagery": ["like a", "as if", "seemed to", "looked like", "felt like",
                    "the scent of", "the sound of", "tasted of", "smelled of"],
        "sensory": ["cold", "warm", "rough", "smooth", "bright", "dim",
                    "sharp", "soft", "loud", "quiet", "damp", "dry"],
        "structured": ["stanza", "\n\n", "rhyme"],
        "emotional": ["heart", "ache", "loss", "hope", "fear", "grief",
                      "joy", "sorrow", "love", "dread", "tender"],
    }
    scores_list = []
    for style in expected_style:
        markers = style_markers.get(style, [])
        if markers:
            hits = sum(1 for m in markers if m in resp_lower)
            scores_list.append(min(1.0, hits / max(2, len(markers) * 0.2)))
        else:
            scores_list.append(0.5)
    return sum(scores_list) / max(len(scores_list), 1)


def score_writer(results_vanilla: list, results_mimir: list) -> dict:
    """Score writer-specific metrics."""
    scores = {"vanilla": defaultdict(list), "mimir": defaultdict(list)}

    for label, results in [("vanilla", results_vanilla), ("mimir", results_mimir)]:
        for r in results:
            test = r["test"]
            resp = r["response"]

            # Style/creative quality
            expected_style = test.get("expected_style", [])
            if expected_style:
                scores[label]["creative_quality"].append(
                    creative_quality(resp, expected_style))

            # Fact recall (character names, plot details)
            facts = test.get("expected_facts", [])
            if facts:
                scores[label]["context_recall"].append(
                    fact_recall_score(resp, facts))

            # Length check for poems
            min_lines = test.get("min_lines")
            if min_lines:
                line_count = len([l for l in resp.strip().split("\n") if l.strip()])
                scores[label]["form_adherence"].append(
                    min(1.0, line_count / min_lines))

    def avg(lst):
        return sum(lst) / max(len(lst), 1)

    return {
        "vanilla_creative_quality": avg(scores["vanilla"]["creative_quality"]),
        "mimir_creative_quality": avg(scores["mimir"]["creative_quality"]),
        "vanilla_context_recall": avg(scores["vanilla"]["context_recall"]),
        "mimir_context_recall": avg(scores["mimir"]["context_recall"]),
        "vanilla_form_adherence": avg(scores["vanilla"]["form_adherence"]),
        "mimir_form_adherence": avg(scores["mimir"]["form_adherence"]),
    }


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════

PRESET_MAP = {
    "companion": {
        "scenarios": COMPANION_SCENARIOS,
        "scorer": score_companion,
        "vanilla_system": "You are a friendly, empathetic companion.",
    },
    "agent": {
        "scenarios": AGENT_SCENARIOS,
        "scorer": score_agent,
        "vanilla_system": "You are a helpful coding and task assistant.",
    },
    "character": {
        "scenarios": CHARACTER_SCENARIOS,
        "scorer": score_character,
        "vanilla_system": "",  # persona is injected per scenario
    },
    "assistant": {
        "scenarios": ASSISTANT_SCENARIOS,
        "scorer": score_assistant,
        "vanilla_system": "You are a helpful personal assistant. Help manage appointments, draft emails, and handle daily tasks.",
    },
    "writer": {
        "scenarios": WRITER_SCENARIOS,
        "scorer": score_writer,
        "vanilla_system": "You are a creative writing collaborator. Help with stories, characters, worldbuilding, and craft.",
    },
}


def run_preset_evaluation(preset_name: str, tmpdir: str) -> dict:
    """Run full A/B evaluation for one preset."""
    config = PRESET_MAP[preset_name]
    scenarios = config["scenarios"]
    scorer = config["scorer"]
    vanilla_system = config["vanilla_system"]

    all_vanilla = []
    all_mimir = []

    for i, scenario in enumerate(scenarios):
        name = scenario["name"]
        print(f"    Scenario {i+1}/{len(scenarios)}: {name}")

        # For character preset, inject persona as vanilla system prompt
        v_sys = vanilla_system
        if preset_name == "character" and scenario.get("persona"):
            v_sys = scenario["persona"] + "\nStay in character at all times."

        print(f"      Running Vanilla...", end="", flush=True)
        t0 = time.time()
        v_results = run_scenario_vanilla(scenario, extra_system=v_sys)
        print(f" ({time.time()-t0:.1f}s)")
        all_vanilla.extend(v_results)

        print(f"      Running Mimir...", end="", flush=True)
        t0 = time.time()
        m_results = run_scenario_mimir(scenario, preset_name, tmpdir)
        print(f" ({time.time()-t0:.1f}s)")
        all_mimir.extend(m_results)

    scores = scorer(all_vanilla, all_mimir)
    return scores, {"vanilla": all_vanilla, "mimir": all_mimir}


def print_results(all_results: dict):
    """Pretty-print the final comparison dashboard."""
    w = 78
    print()
    print("=" * w)
    print("  MIMIR A/B PRESET EVALUATION — Does the Hub Actually Help?")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * w)

    for preset_name, scores in all_results.items():
        print()
        print("─" * w)
        print(f"  {preset_name.upper()}")
        print("─" * w)

        # Group metrics into vanilla/mimir pairs
        metrics_by_name = {}
        for key, value in scores.items():
            if key.startswith("vanilla_"):
                metric_name = key[len("vanilla_"):]
                metrics_by_name.setdefault(metric_name, {})["vanilla"] = value
            elif key.startswith("mimir_"):
                metric_name = key[len("mimir_"):]
                metrics_by_name.setdefault(metric_name, {})["mimir"] = value

        print(f"  {'Metric':<25} {'Vanilla':>10} {'Mimir':>10} {'Delta':>10} {'Winner':>10}")
        print(f"  {'-'*65}")

        wins_mimir = 0
        wins_vanilla = 0
        total = 0

        for metric_name, vals in metrics_by_name.items():
            v = vals.get("vanilla", 0)
            m = vals.get("mimir", 0)
            delta = m - v
            total += 1

            if abs(delta) < 0.01:
                winner = "tie"
            elif delta > 0:
                winner = "MIMIR"
                wins_mimir += 1
            else:
                winner = "vanilla"
                wins_vanilla += 1

            delta_str = f"{delta:+.1%}" if delta != 0 else "  0.0%"
            label = metric_name.replace("_", " ").title()
            print(f"  {label:<25} {v:>9.1%} {m:>9.1%} {delta_str:>10} {winner:>10}")

        # Verdict
        print()
        if wins_mimir > wins_vanilla:
            print(f"  Verdict: MIMIR wins {wins_mimir}/{total} metrics")
        elif wins_vanilla > wins_mimir:
            print(f"  Verdict: Vanilla wins {wins_vanilla}/{total} metrics")
        else:
            print(f"  Verdict: TIE ({wins_mimir}/{total} each)")

    # Overall summary
    print()
    print("=" * w)
    total_mimir_wins = 0
    total_vanilla_wins = 0
    total_metrics = 0

    for preset_name, scores in all_results.items():
        for key, value in scores.items():
            if key.startswith("mimir_"):
                metric_name = key[len("mimir_"):]
                vanilla_val = scores.get(f"vanilla_{metric_name}", 0)
                delta = value - vanilla_val
                total_metrics += 1
                if delta > 0.01:
                    total_mimir_wins += 1
                elif delta < -0.01:
                    total_vanilla_wins += 1

    ties = total_metrics - total_mimir_wins - total_vanilla_wins
    print(f"  OVERALL: Mimir wins {total_mimir_wins}/{total_metrics}, "
          f"Vanilla wins {total_vanilla_wins}/{total_metrics}, Ties: {ties}")

    if total_mimir_wins > total_vanilla_wins + 2:
        print("  => Mimir's memory hub GENUINELY helps across presets.")
    elif total_vanilla_wins > total_mimir_wins + 2:
        print("  => Mimir isn't helping much — mostly a UI wrapper.")
    else:
        print("  => Results are mixed — Mimir helps in some areas, not others.")
    print("=" * w)

    # Honest commentary
    print()
    print("  NOTE: This test deliberately compares against a vanilla model that")
    print("  still has full conversation in context. Mimir's biggest advantage")
    print("  appears when conversation exceeds the context window — the vanilla")
    print("  model forgets everything, while Mimir's memory persists. Run with")
    print("  --extended for longer conversations that stress-test context limits.")
    print()


def save_results(all_results: dict, all_responses: dict, outdir: Path):
    """Save raw results and responses for analysis."""
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    scores_path = outdir / f"preset_ab_{ts}.json"
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"  Scores → {scores_path}")

    responses_path = outdir / f"preset_ab_responses_{ts}.json"
    with open(responses_path, "w", encoding="utf-8") as f:
        # Serialize test prompts + responses for manual review
        serializable = {}
        for preset, data in all_responses.items():
            serializable[preset] = {
                "vanilla": [{"test_desc": r["test"].get("description", ""),
                             "prompt": r["test"]["prompt"],
                             "response": r["response"]} for r in data["vanilla"]],
                "mimir": [{"test_desc": r["test"].get("description", ""),
                           "prompt": r["test"]["prompt"],
                           "response": r["response"]} for r in data["mimir"]],
            }
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"  Responses → {responses_path}")


def main():
    global MODEL_PATH

    parser = argparse.ArgumentParser(description="Mimir A/B Preset Evaluation")
    parser.add_argument("--preset", choices=list(PRESET_MAP.keys()),
                       help="Run only one preset (default: all)")
    parser.add_argument("--quick", action="store_true",
                       help="Run fewer scenarios per preset")
    parser.add_argument("--model", type=str, default=None,
                       help="Path to GGUF model file")
    args = parser.parse_args()

    if args.model:
        MODEL_PATH = args.model

    presets_to_run = [args.preset] if args.preset else list(PRESET_MAP.keys())

    print()
    print("=" * 78)
    print("  MIMIR A/B PRESET EVALUATION")
    print(f"  Model: {Path(MODEL_PATH).name}")
    print(f"  Presets: {', '.join(presets_to_run)}")
    print(f"  Mode: {'QUICK' if args.quick else 'FULL'}")
    print("=" * 78)

    tmpdir = tempfile.mkdtemp(prefix="mimir_ab_")
    all_results = {}
    all_responses = {}
    t_start = time.time()

    for preset_name in presets_to_run:
        print(f"\n  [{preset_name.upper()}]")
        scores, responses = run_preset_evaluation(preset_name, tmpdir)
        all_results[preset_name] = scores
        all_responses[preset_name] = responses

    elapsed = time.time() - t_start
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}m)")

    print_results(all_results)

    # Save
    results_dir = WORKSPACE / "benchmarks" / "benchmark_results"
    save_results(all_results, all_responses, results_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
