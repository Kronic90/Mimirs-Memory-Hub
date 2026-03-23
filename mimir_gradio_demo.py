"""Mimir Interactive Demo — Colab / Gradio

Run in Google Colab (T4 GPU) or any machine with ≥16 GB VRAM.

    pip install vividmimir[all] gradio transformers accelerate bitsandbytes
    python mimir_gradio_demo.py

Features:
    • Chat tab  — talk with a Qwen3.5-4B agent backed by full Mimir memory
    • Memory Viewer tab — browse all episodic memories, social impressions,
      lessons, tasks, reminders, and volatile facts
    • Import Memories tab — upload .txt or .json files; the LLM reads each
      entry and creates properly formatted Mimir memories
    • Settings tab — set a custom persona / system prompt (text box or upload)
"""

from __future__ import annotations

import json, os, re, textwrap, threading, time, traceback
from datetime import datetime
from pathlib import Path

# ── Detect environment ────────────────────────────────────────────────────
IN_COLAB = "COLAB_GPU" in os.environ or "COLAB_RELEASE_TAG" in os.environ

# ── Install deps if running in Colab ──────────────────────────────────────
if IN_COLAB:
    import subprocess, sys
    # Qwen3.5 needs latest transformers — force upgrade from source
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q", "--upgrade",
        "git+https://github.com/huggingface/transformers.git",
    ])
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "vividmimir[all]", "gradio",
        "accelerate", "bitsandbytes", "torch",
    ])

import gradio as gr
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from vividmimir import Mimir

# ═══════════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════════

MODEL_ID = "Qwen/Qwen3.5-4B"
DATA_DIR = "mimir_demo_data"
MAX_NEW_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.9

DEFAULT_PERSONA = textwrap.dedent("""\
    You are a friendly, curious AI companion with a living memory.
    You remember past conversations, form impressions of people,
    learn lessons from experience, and your mood shifts naturally.

    Your memory system (Mimir) feeds you context below your system prompt.
    Use that context naturally — reference past events, acknowledge mood
    shifts, bring up things you learned. Never pretend memories don't exist.
    If your memory says you're feeling a certain way, let it colour your tone.
    If you notice drift or reconsolidation in your memories, you can mention
    how your feelings about something have changed over time.
""")

# ═══════════════════════════════════════════════════════════════════════════
#  Load Model
# ═══════════════════════════════════════════════════════════════════════════

print(f"Loading {MODEL_ID} …")
_tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
_model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)
print("Model loaded ✓")


def llm_generate(prompt: str, max_tokens: int = MAX_NEW_TOKENS) -> str:
    """Generate text from the model."""
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
    with torch.no_grad():
        out = _model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            do_sample=True,
        )
    # Decode only the new tokens
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    return _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


# ═══════════════════════════════════════════════════════════════════════════
#  Init Mimir (all features enabled)
# ═══════════════════════════════════════════════════════════════════════════

def _mimir_llm_fn(prompt: str) -> str:
    """LLM callback for Mimir's relational reasoning."""
    return llm_generate(prompt, max_tokens=128)


mimir = Mimir(
    data_dir=DATA_DIR,
    chemistry=True,
    visual=True,
    llm_fn=_mimir_llm_fn,
)

# ═══════════════════════════════════════════════════════════════════════════
#  State
# ═══════════════════════════════════════════════════════════════════════════

_persona = DEFAULT_PERSONA
_chat_history: list[dict] = []  # [{role, content}, ...]
_entity_name = "User"
_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
#  Helper: build full prompt
# ═══════════════════════════════════════════════════════════════════════════

def _build_prompt(user_message: str) -> str:
    """Assemble system prompt + memory context + chat history + new message."""
    # Get Mimir context block
    ctx = mimir.get_context_block(
        current_entity=_entity_name,
        conversation_context=user_message,
    )

    system = _persona.strip()
    if ctx:
        system += "\n\n--- YOUR LIVING MEMORY ---\n" + ctx

    # Build ChatML format (Qwen3.5)
    parts = [f"<|im_start|>system\n{system}<|im_end|>"]

    for msg in _chat_history[-20:]:  # Keep last 20 turns
        role = msg["role"]  # "user" or "assistant"
        parts.append(f"<|im_start|>{role}\n{msg['content']}<|im_end|>")

    parts.append(f"<|im_start|>user\n{user_message}<|im_end|>")
    parts.append("<|im_start|>assistant\n")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
#  Helper: extract emotions / importance from response context
# ═══════════════════════════════════════════════════════════════════════════

EMOTION_WORDS = {
    "happy", "sad", "angry", "afraid", "surprised", "disgusted",
    "curious", "excited", "anxious", "hopeful", "grateful",
    "proud", "embarrassed", "jealous", "nostalgic", "amused",
    "bored", "confused", "content", "disappointed", "inspired",
    "lonely", "loving", "neutral", "overwhelmed", "peaceful",
    "playful", "relieved", "resentful", "romantic", "serene",
    "shy", "sympathetic", "tender", "triumphant", "vulnerable",
    "wistful", "worried", "awe", "determined", "melancholic",
}


def _detect_emotion(text: str) -> str:
    """Simple keyword emotion detection from text."""
    lower = text.lower()
    for emo in EMOTION_WORDS:
        if emo in lower:
            return emo
    return "neutral"


def _estimate_importance(user_msg: str, bot_msg: str) -> int:
    """Heuristic importance 1-10."""
    combined = (user_msg + " " + bot_msg).lower()
    score = 5
    # Boost for emotional content
    if any(w in combined for w in ["love", "hate", "amazing", "terrible", "died", "born", "married"]):
        score += 2
    # Boost for personal disclosure
    if any(w in combined for w in ["i feel", "i think", "my life", "my family", "secret"]):
        score += 1
    # Boost for questions about past
    if any(w in combined for w in ["remember when", "last time", "do you recall"]):
        score += 1
    return min(score, 10)


# ═══════════════════════════════════════════════════════════════════════════
#  Chat handler
# ═══════════════════════════════════════════════════════════════════════════

def chat(user_message: str, history: list[list[str]]) -> tuple:
    """Process a chat message through the LLM + Mimir pipeline."""
    global _chat_history

    if not user_message.strip():
        return history, ""

    with _lock:
        # 1. Build prompt with memory context
        prompt = _build_prompt(user_message)

        # 2. Generate response
        response = llm_generate(prompt)

        # 3. Update chat history
        _chat_history.append({"role": "user", "content": user_message})
        _chat_history.append({"role": "assistant", "content": response})

        # 4. Store the exchange in Mimir
        emotion = _detect_emotion(user_message + " " + response)
        importance = _estimate_importance(user_message, response)

        mimir.remember(
            content=f"[{_entity_name}]: {user_message}\n[Me]: {response}",
            emotion=emotion,
            importance=importance,
            source="conversation",
            why_saved=f"Conversation exchange with {_entity_name}",
        )

        # 5. Update mood based on detected emotions
        emotions_in_text = [e for e in EMOTION_WORDS
                           if e in (user_message + " " + response).lower()]
        if emotions_in_text:
            mimir.update_mood(emotions_in_text[:3])

        # 6. Check for social content (impressions about the user)
        if any(w in user_message.lower() for w in ["i am", "i'm", "my name", "i like", "i hate", "i love"]):
            mimir.add_social_impression(
                entity=_entity_name,
                content=user_message,
                emotion=emotion,
                importance=min(importance + 1, 10),
                why_saved="Personal disclosure from user",
            )

        # 7. Tick dampening if active
        if mimir.is_dampened():
            mimir.tick_dampening()

        # 8. Update history for Gradio
        history = history or []
        history.append([user_message, response])

    return history, ""


# ═══════════════════════════════════════════════════════════════════════════
#  Memory Viewer
# ═══════════════════════════════════════════════════════════════════════════

def get_memories_table() -> str:
    """Return a formatted Markdown table of all episodic memories."""
    mems = sorted(mimir.self_reflections, key=lambda m: m.timestamp, reverse=True)
    if not mems:
        return "No memories yet. Start chatting!"

    rows = ["| # | Content | Emotion | Vividness | Importance | Source | Flags |",
            "|---|---------|---------|-----------|------------|--------|-------|"]
    for i, m in enumerate(mems[:100]):
        content = m.gist[:80].replace("|", "\\|").replace("\n", " ")
        flags = []
        if m._cherished:
            flags.append("♥")
        if m._anchor:
            flags.append("⚓")
        if m._is_flashbulb:
            flags.append("⚡")
        if m.has_drifted:
            flags.append("↝")
        rows.append(
            f"| {i+1} | {content} | {m.emotion} | "
            f"{m.vividness:.2f} | {m.importance} | {m.source} | "
            f"{''.join(flags)} |"
        )
    return "\n".join(rows)


def get_social_table() -> str:
    """Social impressions table."""
    all_social = mimir.social_impressions
    if not all_social:
        return "No social impressions yet."

    rows = ["| Entity | Content | Emotion | Vividness |",
            "|--------|---------|---------|-----------|"]
    for entity, impressions in all_social.items():
        for m in sorted(impressions, key=lambda x: x.timestamp, reverse=True)[:20]:
            content = m.content[:60].replace("|", "\\|").replace("\n", " ")
            rows.append(f"| {entity} | {content} | {m.emotion} | {m.vividness:.2f} |")
    return "\n".join(rows)


def get_lessons_table() -> str:
    """Lessons table."""
    lessons = mimir.get_active_lessons()
    if not lessons:
        return "No lessons learned yet."

    rows = ["| Topic | Strategy | Failures | Vividness |",
            "|-------|----------|----------|-----------|"]
    for ls in lessons[:30]:
        rows.append(
            f"| {ls.topic[:50]} | {ls.strategy[:50]} | "
            f"{ls.consecutive_failures} | {ls.vividness:.2f} |"
        )
    return "\n".join(rows)


def get_tasks_table() -> str:
    """Tasks table."""
    tasks = mimir.get_active_tasks()
    if not tasks:
        return "No active tasks."

    rows = ["| Task | Priority | Status | Created |",
            "|------|----------|--------|---------|"]
    for t in tasks:
        rows.append(
            f"| {t.description[:60]} | {t.priority} | {t.status} | "
            f"{t.created[:19]} |"
        )
    return "\n".join(rows)


def get_facts_table() -> str:
    """Volatile facts table."""
    facts = mimir.get_facts()
    if not facts:
        return "No volatile facts."

    rows = ["| Entity | Attribute | Value | Vividness |",
            "|--------|-----------|-------|-----------|"]
    for f in facts[:30]:
        rows.append(f"| {f.entity} | {f.attribute} | {f.value} | {f.vividness:.2f} |")
    return "\n".join(rows)


def get_reminders_text() -> str:
    """Show all reminders (not just due ones)."""
    rems = mimir._reminders
    if not rems:
        return "No reminders set."

    lines = []
    for r in rems:
        status = "✅ Fired" if r.fired else ("⏰ Due!" if r.is_due else "⏳ Pending")
        lines.append(f"- **{r.text}** — due {r.due_at[:19]} — {status}")
    return "\n".join(lines)


def get_chemistry_text() -> str:
    """Neurochemistry + mood readout."""
    lines = [f"**Mood:** {mimir.mood_label} (PAD: {mimir.mood})"]
    if mimir.chemistry.enabled:
        lines.append(f"**Chemistry:** {mimir.chemistry.describe()}")
    if mimir.is_dampened():
        lines.append("**Dampening:** Active (emotional shield)")
    return "\n\n".join(lines)


def get_yggdrasil_text() -> str:
    """Yggdrasil graph summary."""
    roots = mimir.yggdrasil_roots()
    if not roots:
        return "Yggdrasil is empty — no anchor/flashbulb memories yet."

    lines = [f"**Foundation memories (roots):** {len(roots)}"]
    for m in roots[:10]:
        content = m.gist[:60]
        lines.append(f"- 🌳 {content} ({m.emotion})")
    total_edges = sum(len(v) for v in mimir._yggdrasil.values())
    lines.append(f"\n**Total graph edges:** {total_edges}")
    return "\n".join(lines)


def get_insights_text() -> str:
    """Huginn + Völva insights."""
    insights = [m for m in mimir.self_reflections
                if m.source in ("huginn", "volva") and m.vividness > 0.1]
    if not insights:
        return "No insights yet. Run sleep cycle or chat more to generate patterns."

    insights.sort(key=lambda m: m.timestamp, reverse=True)
    lines = []
    for m in insights[:15]:
        tag = "🦅 Huginn" if m.source == "huginn" else "🔮 Völva"
        lines.append(f"- {tag}: {m.gist[:100]} ({m.emotion})")
    return "\n".join(lines)


def refresh_all_viewers():
    """Refresh all memory viewer tabs."""
    return (
        get_memories_table(),
        get_social_table(),
        get_lessons_table(),
        get_tasks_table(),
        get_facts_table(),
        get_reminders_text(),
        get_chemistry_text(),
        get_yggdrasil_text(),
        get_insights_text(),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Memory Import
# ═══════════════════════════════════════════════════════════════════════════

def _parse_import_entry(raw_text: str) -> dict:
    """Use the LLM to parse a raw memory entry into structured fields."""
    prompt = textwrap.dedent(f"""\
        <|im_start|>system
        You are a memory analyst. Given a raw text entry, extract structured
        memory fields. Respond ONLY with valid JSON, no extra text.
        
        Required JSON fields:
        - "content": the memory text (clean it up if needed, keep the meaning)
        - "emotion": one word from this list: happy, sad, angry, afraid, surprised,
          curious, excited, anxious, hopeful, grateful, proud, embarrassed,
          nostalgic, amused, content, disappointed, inspired, loving, neutral,
          peaceful, playful, tender, triumphant, vulnerable, wistful, worried,
          awe, determined, melancholic, serene
        - "importance": integer 1-10 (how significant is this memory?)
        - "why_saved": a brief reason why this memory matters
        - "is_about_person": true/false — is this primarily about a specific person?
        - "person_name": if is_about_person is true, the person's name, else ""
        <|im_end|>
        <|im_start|>user
        Parse this memory entry:

        {raw_text}
        <|im_end|>
        <|im_start|>assistant
        """)

    result = llm_generate(prompt, max_tokens=256)

    # Extract JSON from response
    try:
        # Try to find JSON in the response
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    # Fallback: create a basic entry
    return {
        "content": raw_text.strip(),
        "emotion": _detect_emotion(raw_text),
        "importance": 5,
        "why_saved": "Imported from user file",
        "is_about_person": False,
        "person_name": "",
    }


def import_memories(file_obj, progress=gr.Progress()) -> str:
    """Import memories from an uploaded .txt or .json file."""
    if file_obj is None:
        return "No file uploaded."

    file_path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    ext = Path(file_path).suffix.lower()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    entries: list[str] = []

    if ext == ".json":
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        entries.append(item)
                    elif isinstance(item, dict):
                        # Try to use pre-structured data
                        text = item.get("content") or item.get("text") or item.get("memory") or json.dumps(item)
                        entries.append(text)
            elif isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, str):
                        entries.append(f"{key}: {val}")
                    elif isinstance(val, list):
                        for v in val:
                            entries.append(str(v))
        except json.JSONDecodeError:
            entries = [line.strip() for line in raw.split("\n") if line.strip()]
    else:
        # Text file: split by double newlines or single lines
        if "\n\n" in raw:
            entries = [chunk.strip() for chunk in raw.split("\n\n") if chunk.strip()]
        else:
            entries = [line.strip() for line in raw.split("\n") if line.strip()]

    if not entries:
        return "No memory entries found in file."

    results = []
    total = len(entries)

    for i, entry in enumerate(entries):
        if not entry.strip():
            continue

        progress((i + 1) / total, desc=f"Processing {i+1}/{total}")

        try:
            parsed = _parse_import_entry(entry)

            content = str(parsed.get("content", entry))
            emotion = str(parsed.get("emotion", "neutral"))
            importance = int(parsed.get("importance", 5))
            why_saved = str(parsed.get("why_saved", "Imported memory"))

            # Validate emotion
            if emotion not in EMOTION_WORDS:
                emotion = "neutral"
            importance = max(1, min(10, importance))

            # Store as social impression if about a person
            if parsed.get("is_about_person") and parsed.get("person_name"):
                mimir.add_social_impression(
                    entity=parsed["person_name"],
                    content=content,
                    emotion=emotion,
                    importance=importance,
                    why_saved=why_saved,
                )
                results.append(f"✓ Social impression ({parsed['person_name']}): {content[:50]}…")
            else:
                mimir.remember(
                    content=content,
                    emotion=emotion,
                    importance=importance,
                    source="import",
                    why_saved=why_saved,
                )
                results.append(f"✓ Memory: {content[:50]}…")

        except Exception as e:
            results.append(f"✗ Error on entry {i+1}: {e}")

    summary = f"**Imported {sum(1 for r in results if r.startswith('✓'))}/{total} memories**\n\n"
    summary += "\n".join(results)
    return summary


# ═══════════════════════════════════════════════════════════════════════════
#  Settings / Persona
# ═══════════════════════════════════════════════════════════════════════════

def update_persona(persona_text: str, persona_file, entity_name: str) -> str:
    """Update the system prompt persona."""
    global _persona, _entity_name

    if entity_name.strip():
        _entity_name = entity_name.strip()

    # File takes priority if uploaded
    if persona_file is not None:
        try:
            file_path = persona_file.name if hasattr(persona_file, "name") else str(persona_file)
            with open(file_path, "r", encoding="utf-8") as f:
                new_persona = f.read().strip()
            if new_persona:
                _persona = new_persona
                return f"✓ Persona loaded from file ({len(new_persona)} chars). Entity: {_entity_name}"
        except Exception as e:
            return f"Error reading persona file: {e}"

    if persona_text.strip():
        _persona = persona_text.strip()
        return f"✓ Persona updated ({len(_persona)} chars). Entity: {_entity_name}"

    return "No changes — provide text or upload a file."


def get_current_persona() -> str:
    """Return current persona for display."""
    return _persona


# ═══════════════════════════════════════════════════════════════════════════
#  Manual Mimir Actions
# ═══════════════════════════════════════════════════════════════════════════

def run_sleep_cycle() -> str:
    """Run Mimir's full sleep cycle (Muninn → Huginn → Völva)."""
    try:
        mimir.sleep_reset(hours=8.0)
        return "✓ Sleep cycle complete (Muninn consolidation → Huginn insights → Völva dreams)"
    except Exception as e:
        return f"Error: {e}"


def run_huginn() -> str:
    """Run Huginn pattern detection."""
    try:
        insights = mimir.huginn()
        if insights:
            lines = [f"🦅 Huginn found {len(insights)} insight(s):"]
            for m in insights:
                lines.append(f"  • {m.gist[:80]}")
            return "\n".join(lines)
        return "🦅 Huginn found no new patterns."
    except Exception as e:
        return f"Error: {e}"


def run_volva() -> str:
    """Run Völva dream synthesis."""
    try:
        dreams = mimir.volva_dream()
        if dreams:
            lines = [f"🔮 Völva synthesised {len(dreams)} dream(s):"]
            for m in dreams:
                lines.append(f"  • {m.gist[:80]}")
            return "\n".join(lines)
        return "🔮 Völva had no dreams — need more memories."
    except Exception as e:
        return f"Error: {e}"


def add_manual_memory(content: str, emotion: str, importance: int, why: str) -> str:
    """Manually add a memory."""
    if not content.strip():
        return "Content cannot be empty."
    emotion = emotion.strip().lower() or "neutral"
    if emotion not in EMOTION_WORDS:
        emotion = "neutral"
    importance = max(1, min(10, importance))

    mimir.remember(
        content=content.strip(),
        emotion=emotion,
        importance=importance,
        why_saved=why.strip() or "Manually added",
    )
    return f"✓ Stored: \"{content[:50]}…\" ({emotion}, importance={importance})"


def set_reminder_ui(text: str, hours: float) -> str:
    """Set a reminder."""
    if not text.strip():
        return "Reminder text cannot be empty."
    r = mimir.set_reminder(text.strip(), hours=max(0.1, hours))
    return f"✓ Reminder set: \"{r.text}\" — due {r.due_at[:19]}"


def add_fact_ui(entity: str, attribute: str, value: str) -> str:
    """Add a volatile fact."""
    if not all([entity.strip(), attribute.strip(), value.strip()]):
        return "All fields required."
    mimir.add_fact(entity.strip(), attribute.strip(), value.strip())
    return f"✓ Fact stored: {entity}.{attribute} = {value}"


# ═══════════════════════════════════════════════════════════════════════════
#  Build Gradio UI
# ═══════════════════════════════════════════════════════════════════════════

MEMORY_USAGE_NOTE = textwrap.dedent("""\
    **Memory System Info:**
    The agent's memory is powered by **Mimir** — 21 neuroscience mechanisms
    including flashbulb encoding, reconsolidation drift, spreading activation,
    neurochemistry, and more. Every message you send is remembered;
    memories decay organically and can be involuntarily recalled.
""")

with gr.Blocks(
    title="Mimir Demo — Living Memory AI",
    theme=gr.themes.Soft(),
    css=".memory-table {font-size: 0.85em;}"
) as demo:
    gr.Markdown("# 🧠 Mimir — Living Memory AI Demo")
    gr.Markdown(MEMORY_USAGE_NOTE)

    with gr.Tabs():
        # ── Tab 1: Chat ──────────────────────────────────────────────
        with gr.Tab("💬 Chat"):
            chatbot = gr.Chatbot(height=500, label="Conversation")
            with gr.Row():
                msg_box = gr.Textbox(
                    placeholder="Type a message…",
                    show_label=False,
                    scale=9,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            with gr.Accordion("Quick Actions", open=False):
                with gr.Row():
                    sleep_btn = gr.Button("😴 Sleep Cycle")
                    huginn_btn = gr.Button("🦅 Huginn")
                    volva_btn = gr.Button("🔮 Völva")
                action_output = gr.Textbox(label="Action Result", interactive=False)

            # Wire chat
            msg_box.submit(chat, [msg_box, chatbot], [chatbot, msg_box])
            send_btn.click(chat, [msg_box, chatbot], [chatbot, msg_box])

            # Wire quick actions
            sleep_btn.click(run_sleep_cycle, outputs=action_output)
            huginn_btn.click(run_huginn, outputs=action_output)
            volva_btn.click(run_volva, outputs=action_output)

        # ── Tab 2: Memory Viewer ─────────────────────────────────────
        with gr.Tab("🧠 Memory Viewer"):
            refresh_btn = gr.Button("🔄 Refresh All", variant="primary")

            with gr.Tabs():
                with gr.Tab("Episodic"):
                    mem_table = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Social"):
                    social_table = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Lessons"):
                    lessons_table = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Tasks"):
                    tasks_table = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Facts"):
                    facts_table = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Reminders"):
                    reminders_text = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Chemistry"):
                    chem_text = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Yggdrasil"):
                    ygg_text = gr.Markdown(value="Click Refresh to load")
                with gr.Tab("Insights"):
                    insights_text = gr.Markdown(value="Click Refresh to load")

            refresh_btn.click(
                refresh_all_viewers,
                outputs=[
                    mem_table, social_table, lessons_table, tasks_table,
                    facts_table, reminders_text, chem_text, ygg_text,
                    insights_text,
                ],
            )

        # ── Tab 3: Import Memories ───────────────────────────────────
        with gr.Tab("📥 Import Memories"):
            gr.Markdown(textwrap.dedent("""\
                **Upload a .txt or .json file** containing memories you want the AI to absorb.

                **Supported formats:**
                - **.txt** — one memory per line, or paragraphs separated by blank lines
                - **.json** — array of strings, or array of objects with `"content"` / `"text"` fields

                The LLM will read each entry and create properly structured Mimir memories
                with appropriate emotion, importance, and reasoning.
            """))
            import_file = gr.File(
                label="Upload memories file",
                file_types=[".txt", ".json"],
            )
            import_btn = gr.Button("🧠 Import & Process", variant="primary")
            import_output = gr.Markdown(value="")

            import_btn.click(import_memories, inputs=import_file, outputs=import_output)

        # ── Tab 4: Manual Memory ─────────────────────────────────────
        with gr.Tab("✏️ Add Memory"):
            gr.Markdown("**Manually add a memory, fact, or reminder.**")

            with gr.Accordion("Add Episodic Memory", open=True):
                mem_content = gr.Textbox(label="Content", lines=3)
                with gr.Row():
                    mem_emotion = gr.Textbox(label="Emotion", value="neutral")
                    mem_importance = gr.Slider(1, 10, value=5, step=1, label="Importance")
                mem_why = gr.Textbox(label="Why save this?")
                mem_btn = gr.Button("Store Memory")
                mem_result = gr.Textbox(label="Result", interactive=False)
                mem_btn.click(add_manual_memory,
                             [mem_content, mem_emotion, mem_importance, mem_why],
                             mem_result)

            with gr.Accordion("Add Volatile Fact", open=False):
                with gr.Row():
                    fact_entity = gr.Textbox(label="Entity")
                    fact_attr = gr.Textbox(label="Attribute")
                    fact_val = gr.Textbox(label="Value")
                fact_btn = gr.Button("Store Fact")
                fact_result = gr.Textbox(label="Result", interactive=False)
                fact_btn.click(add_fact_ui,
                              [fact_entity, fact_attr, fact_val],
                              fact_result)

            with gr.Accordion("Set Reminder", open=False):
                with gr.Row():
                    rem_text = gr.Textbox(label="Reminder text", scale=3)
                    rem_hours = gr.Number(label="Hours from now", value=1.0, scale=1)
                rem_btn = gr.Button("Set Reminder")
                rem_result = gr.Textbox(label="Result", interactive=False)
                rem_btn.click(set_reminder_ui, [rem_text, rem_hours], rem_result)

        # ── Tab 5: Settings ──────────────────────────────────────────
        with gr.Tab("⚙️ Settings"):
            gr.Markdown(textwrap.dedent("""\
                **Customise the AI persona.** The memory system instructions are
                automatically injected — your persona just sets the personality/role.
            """))
            persona_box = gr.Textbox(
                label="System Prompt / Persona",
                value=DEFAULT_PERSONA,
                lines=10,
            )
            persona_file_upload = gr.File(
                label="Or upload a .txt persona file",
                file_types=[".txt"],
            )
            entity_box = gr.Textbox(
                label="Your name (for social impressions)",
                value="User",
            )
            save_persona_btn = gr.Button("💾 Save Persona", variant="primary")
            persona_status = gr.Textbox(label="Status", interactive=False)

            save_persona_btn.click(
                update_persona,
                [persona_box, persona_file_upload, entity_box],
                persona_status,
            )

            gr.Markdown("---")
            gr.Markdown("**Current persona preview:**")
            persona_preview = gr.Textbox(
                value=DEFAULT_PERSONA,
                interactive=False,
                lines=8,
            )
            save_persona_btn.click(get_current_persona, outputs=persona_preview)

# ═══════════════════════════════════════════════════════════════════════════
#  Launch
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    demo.queue()
    demo.launch(
        share=IN_COLAB,  # Auto-generate public URL if in Colab
        server_name="0.0.0.0",
        server_port=7860,
    )
