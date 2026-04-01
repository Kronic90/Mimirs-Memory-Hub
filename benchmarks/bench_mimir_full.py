"""
bench_mimir_full.py — Unified Mimir Benchmark Suite
====================================================
Runs Mimir against ALL 6 benchmark suites in one shot:

  1. Mem2ActBench   — Tool-call accuracy (episodic + procedural)  [LLM]
  2. MemoryBench    — WritingPrompts generation (METEOR/ROUGE)    [LLM]
  3. LoCoMo         — Evidence Recall@k by category               [CPU]
  4. LongMemEval    — Long conversation memory retrieval          [CPU]
  5. MSC            — Persona fact Recall@k                       [CPU]
  6. MTEB           — STS-B Spearman + GoEmotions kNN accuracy    [CPU]

Usage:
  python bench_mimir_full.py                     # all 6
  python bench_mimir_full.py --bench mem2act     # single bench
  python bench_mimir_full.py --skip-llm          # CPU-only (skip 1 & 2)
  python bench_mimir_full.py --quick             # fast mode (fewer items)
"""

import sys, os, json, time, re, math, argparse, shutil, tempfile, random
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

# Windows console encoding fix
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Environment ──────────────────────────────────────────────────────────
os.environ["HF_HOME"] = r"C:\Users\scott\.cache\huggingface"
os.environ["HF_DATASETS_CACHE"] = r"C:\Users\scott\.cache\huggingface\datasets"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import numpy as np
if not hasattr(np.ndarray, '__class_getitem__'):
    np.ndarray.__class_getitem__ = classmethod(lambda cls, *args: cls)

WORKSPACE = Path(__file__).parent
RESULTS_DIR = WORKSPACE / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)
MEM2ACT_DIR = WORKSPACE / "Mem2ActBench_repo"
MEMORYBENCH_DIR = WORKSPACE / "MemoryBench"

sys.path.insert(0, str(WORKSPACE / "Mimir"))
sys.path.insert(1, str(WORKSPACE / "standalone memory"))
sys.path.insert(2, str(WORKSPACE))

try:
    from mimir_modular import Mimir
    from mimir_modular.helpers import _resonance_words
except ModuleNotFoundError:
    from Mimir import Mimir, _resonance_words  # type: ignore


# ══════════════════════════════════════════════════════════════════════════
#  SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════════════

MODEL_PATH = r"D:\AiStuff\google_gemma-3-12b-it-Q4_K_M.gguf"
CTX_SIZE = 8192
MAX_TOKENS = 512

_llm_cache = None


def load_llm():
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache
    from llama_cpp import Llama
    print(f"  Loading LLM: {Path(MODEL_PATH).name}")
    t0 = time.time()
    _llm_cache = Llama(
        model_path=MODEL_PATH, n_ctx=CTX_SIZE,
        n_gpu_layers=48, verbose=False,
    )
    print(f"  Loaded in {time.time() - t0:.1f}s")
    return _llm_cache


def generate(llm, messages, max_tokens=MAX_TOKENS, temperature=0.0):
    total_chars = sum(len(m.get("content", "")) for m in messages)
    budget = int((CTX_SIZE - max_tokens - 200) * 3.5)
    while total_chars > budget and len(messages) > 2:
        messages = [messages[0]] + messages[2:]
        total_chars = sum(len(m.get("content", "")) for m in messages)
    if total_chars > budget:
        last = messages[-1]
        last["content"] = last["content"][:max(200, len(last["content"]) - (total_chars - budget))]
    try:
        resp = llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens, temperature=temperature)
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [gen error] {e}")
        return ""


def simple_emotion(text):
    t = text.lower()
    if any(w in t for w in ["love", "happy", "great", "wonderful", "amazing"]):
        return "happy"
    if any(w in t for w in ["hate", "terrible", "awful", "angry"]):
        return "frustrated"
    if any(w in t for w in ["sad", "miss", "lost", "sorry"]):
        return "sad"
    if any(w in t for w in ["excited", "wow", "incredible"]):
        return "excited"
    if any(w in t for w in ["afraid", "scared", "worry", "anxious"]):
        return "anxious"
    if any(w in t for w in ["curious", "wonder", "interesting"]):
        return "curious"
    return "neutral"


class TFIDFBaseline:
    """Dead simple TF-IDF bag-of-words retrieval baseline."""
    def __init__(self):
        self.docs = []
        self.doc_words = []
        self.idf = {}

    def add(self, text):
        words = _resonance_words(text)
        self.docs.append(text)
        self.doc_words.append(words)

    def build(self):
        N = len(self.docs)
        df = Counter()
        for words in self.doc_words:
            for w in set(words):
                df[w] += 1
        self.idf = {w: math.log((N + 1) / (c + 1)) + 1.0 for w, c in df.items()}

    def query(self, text, top_k=10):
        q_words = _resonance_words(text)
        scores = []
        for i, dw in enumerate(self.doc_words):
            score = sum(self.idf.get(w, 0.0) for w in q_words & dw)
            if score > 0:
                scores.append((score, i))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scores[:top_k]]


def jaccard_match(fact_words, doc_words, threshold=0.3):
    """Jaccard-like overlap check."""
    if not fact_words or not doc_words:
        return False
    overlap = len(fact_words & doc_words)
    return (overlap / max(len(fact_words | doc_words), 1)) >= threshold


def word_coverage_match(fact_words, doc_words, threshold=0.3):
    """Coverage: fraction of fact words found in doc."""
    if not fact_words:
        return False
    overlap = len(fact_words & doc_words)
    return (overlap / len(fact_words)) >= threshold


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 1: Mem2ActBench — Tool-call prediction with episodic + procedural
# ══════════════════════════════════════════════════════════════════════════

def _m2a_load_qa():
    path = MEM2ACT_DIR / "Mem2ActBench" / "qa_dataset.jsonl"
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def _m2a_build_session_index():
    path = MEM2ACT_DIR / "Mem2ActBench" / "toolmem_conversation.jsonl"
    idx = {}
    for line in path.open(encoding="utf-8"):
        sess = json.loads(line)
        for oci in sess.get("original_conversation_ids", []):
            idx[oci] = sess
    return idx


def _m2a_get_sessions(qa, si):
    seen, out = set(), []
    for src in qa["source_conversation_ids"]:
        s = si.get(src)
        if s and s["session_id"] not in seen:
            seen.add(s["session_id"])
            out.append(s)
    return out


def _m2a_store(mind, sessions):
    """Feed episodic memories + procedural lessons into Mimir."""
    for sess in sessions:
        for ti, turn in enumerate(sess["turns"]):
            role = turn["role"]
            content = (turn.get("content", "") or "").strip()
            if role == "user" and content:
                mind.remember(content=f"User said: {content[:300]}",
                              emotion="neutral", importance=6)
            tool_calls = turn.get("tool_calls")
            if not tool_calls:
                continue
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "")
                if isinstance(args_raw, str):
                    try: args = json.loads(args_raw)
                    except (json.JSONDecodeError, TypeError): args = {}
                else:
                    args = args_raw if isinstance(args_raw, dict) else {}
                if not isinstance(args, dict):
                    args = {}
                fact = f"Used tool {name} with args: {json.dumps(args)}"
                mind.remember(content=fact, emotion="neutral", importance=7)

                trigger = ""
                for j in range(ti - 1, -1, -1):
                    if sess["turns"][j]["role"] == "user":
                        trigger = (sess["turns"][j].get("content", "") or "")[:200]
                        break
                if not name or not trigger:
                    continue

                mind.add_lesson(
                    topic=f"Use {name} for: {trigger[:60]}",
                    context_trigger=trigger,
                    strategy=f"Call {name} with arguments: {json.dumps(args)}")

                for key, val in args.items():
                    val_str = str(val).strip()
                    if not val_str or val_str in ("", "null", "none"):
                        continue
                    mind.add_lesson(
                        topic=f"Arg: {name}.{key}={val_str}",
                        context_trigger=f"{name} {key} {val_str} {trigger}"[:300],
                        strategy=f"For tool {name}, set {key}='{val_str}'. Context: {trigger[:150]}")


_RESOLVE_PROMPT = """You are a memory lookup assistant. The user's query contains vague references.
Given the query and memory context, identify EVERY specific entity, value, or name being referenced.
Return ONLY a comma-separated list. If nothing needs resolving, return: NONE"""


def _m2a_resolve_implicit(llm, query, memory_context):
    if not memory_context:
        return []
    msgs = [
        {"role": "system", "content": _RESOLVE_PROMPT},
        {"role": "user", "content": f"Memory Context:\n{memory_context[:2000]}\n\nQuery: {query}\n\nResolved values:"},
    ]
    try:
        raw = generate(llm, msgs, max_tokens=100, temperature=0.0).strip().strip('"')
        if not raw or raw.upper() == "NONE":
            return []
        return [v.strip() for v in raw.split(",") if v.strip()]
    except Exception:
        return []


def _m2a_retrieve(mind, query, tool_schema, llm=None):
    """Pull episodic + procedural context for tool-call prediction."""
    tool_name = tool_schema.get("name", "")
    tool_desc = tool_schema.get("description", "")[:200]
    search = f"{query} {tool_name} {tool_desc}"

    _IMPLICIT_MARKERS = frozenset({
        "that", "those", "the", "same", "usual", "always",
        "my", "our", "typical", "regular", "again", "previous",
    })
    query_words = set(query.lower().split())
    has_implicit = bool(query_words & _IMPLICIT_MARKERS)

    lines = []
    memories = mind.resonate(search, limit=8)
    if memories:
        lines.append("## Retrieved Memories (Episodic)")
        for m in memories:
            lines.append(f"- {m.gist}")

    # Tool-first: scan lessons by topic
    results = {}
    tool_tag = tool_name.lower().strip()
    if tool_tag:
        for lesson in mind.lessons:
            if tool_tag in lesson.topic.lower():
                results[lesson.topic] = (lesson, 1.0)

    for lesson, score in mind.retrieve_lessons(search, limit=8):
        if lesson.topic not in results:
            results[lesson.topic] = (lesson, score)

    if tool_name:
        for lesson, score in mind.retrieve_lessons(tool_name, limit=5):
            if lesson.topic not in results:
                results[lesson.topic] = (lesson, score)

    params = tool_schema.get("parameters", {}).get("properties", {})
    if params:
        parts = []
        for pk, pv in params.items():
            parts.append(pk)
            d = pv.get("description", "")
            if d:
                parts.append(d[:60])
        s2 = f"{query} {' '.join(parts)}"
        for lesson, score in mind.retrieve_lessons(s2, limit=6):
            if lesson.topic not in results:
                results[lesson.topic] = (lesson, score)

    # Gemma implicit reference resolution
    if has_implicit and llm and results:
        ctx_parts = []
        for lesson, _ in sorted(results.values(), key=lambda x: x[1], reverse=True)[:15]:
            ctx_parts.append(f"- {lesson.strategy[:200]}")
        for m in (memories or [])[:5]:
            ctx_parts.append(f"- {m.gist[:200]}")
        initial_ctx = "\n".join(ctx_parts)
        resolved = _m2a_resolve_implicit(llm, query, initial_ctx)
        if resolved:
            for term in resolved:
                for lesson, score in mind.retrieve_lessons(f"{term} {tool_name}", limit=5):
                    if lesson.topic not in results:
                        results[lesson.topic] = (lesson, score + 0.1)
                term_lower = term.lower().strip()
                for lesson in mind.lessons:
                    if lesson.topic in results:
                        continue
                    lesson_text = f"{lesson.topic} {lesson.context_trigger} {lesson.strategy}".lower()
                    if term_lower in lesson_text:
                        results[lesson.topic] = (lesson, 0.9)

    if results:
        ranked = sorted(results.values(), key=lambda x: x[1], reverse=True)[:20]
        lines.append("## Retrieved Procedural Knowledge (Lessons)")
        for lesson, score in ranked:
            lines.append(f"- {lesson.strategy[:250]}")

    return "\n".join(lines) if lines else ""


_M2A_SYSTEM = """You are an AI assistant that helps users by calling tools. Given a user query, past memory context, and a target tool schema, you must generate the correct tool call with filled-in arguments.

CRITICAL RULES:
1. Respond ONLY with a JSON object: {"name": "<tool_name>", "arguments": {<key>: <value>, ...}}
2. ALWAYS use EXACT values from the memory context when filling arguments.
3. When a user refers to something implicitly, look up the SPECIFIC value from memory context.
4. Include ALL required parameters from the schema.
Do NOT include any other text. Just the raw JSON object."""


def _m2a_parse_tool_call(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    match = re.search(r'\{[^{}]*"name"\s*:.*\}', raw, re.DOTALL)
    if match:
        try: return json.loads(match.group())
        except json.JSONDecodeError: pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try: return json.loads(raw[start:end + 1])
        except json.JSONDecodeError: pass
    return None


def _normalize(v):
    if isinstance(v, bool): return str(v).lower()
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, str): return v.strip().lower()
    return json.dumps(v, sort_keys=True).lower()


def _m2a_tool_accuracy(pred, gold):
    if pred is None: return 0.0
    if pred.get("name", "").strip().lower() != gold["name"].strip().lower():
        return 0.0
    for k, v in gold.get("arguments", {}).items():
        if k not in pred.get("arguments", {}): return 0.0
        if _normalize(pred["arguments"][k]) != _normalize(v): return 0.0
    return 1.0


def _m2a_f1(pred, gold):
    if pred is None: return 0.0, 0.0, 0.0
    gold_pairs = {(k, _normalize(v)) for k, v in gold.get("arguments", {}).items()}
    pred_pairs = {(k, _normalize(v)) for k, v in (pred.get("arguments", {}) or {}).items()}
    if not gold_pairs and not pred_pairs: return 1.0, 1.0, 1.0
    if not pred_pairs or not gold_pairs: return 0.0, 0.0, 0.0
    tp = len(gold_pairs & pred_pairs)
    prec = tp / len(pred_pairs)
    rec = tp / len(gold_pairs)
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def _m2a_bleu1(pred, gold):
    if pred is None: return 0.0
    gold_args = gold.get("arguments", {})
    pred_args = pred.get("arguments", {}) if pred else {}
    gold_tok, pred_tok = [], []
    for k, v in sorted(gold_args.items()):
        gold_tok.extend(str(k).lower().split())
        gold_tok.extend(str(v).lower().split())
    for k, v in sorted(pred_args.items()):
        pred_tok.extend(str(k).lower().split())
        pred_tok.extend(str(v).lower().split())
    if not gold_tok or not pred_tok: return 0.0
    gc = Counter(gold_tok); pc = Counter(pred_tok)
    clipped = sum(min(pc[w], gc[w]) for w in pc)
    prec = clipped / sum(pc.values())
    bp = min(1.0, len(pred_tok) / len(gold_tok))
    return bp * prec


def bench_mem2act(max_eval=100, quick=False):
    """Mem2ActBench: episodic + procedural → tool-call prediction."""
    from tqdm import tqdm
    if quick: max_eval = min(max_eval, 30)
    llm = load_llm()

    print(f"\n{'='*70}")
    print(f"  BENCH 1: Mem2ActBench — Tool-Call Accuracy  (n={max_eval})")
    print(f"{'='*70}")

    qa_items = _m2a_load_qa()
    session_index = _m2a_build_session_index()
    print(f"  {len(qa_items)} QA items, {len(session_index)} sessions indexed")

    metrics = {"tool_accuracy": [], "f1": [], "precision": [], "recall": [], "bleu1": []}
    level_metrics = {}

    items = qa_items[:max_eval]
    t0 = time.time()
    for i, qa in enumerate(tqdm(items, desc="mem2act")):
        query = qa["query"]
        gold = qa["tool_call"]
        schema = qa["target_tool_schema"]
        level = qa["complexity_metadata"]["level"]
        sessions = _m2a_get_sessions(qa, session_index)

        tmp = tempfile.mkdtemp(prefix="bm_m2a_")
        try:
            mind = Mimir(data_dir=os.path.join(tmp, "m"), chemistry=False)
            _m2a_store(mind, sessions)
            mind.save()
            ctx = _m2a_retrieve(mind, query, schema, llm=llm)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        schema_text = json.dumps(schema, indent=2, ensure_ascii=False)
        user = f"Target Tool Schema:\n{schema_text}\n\n"
        if ctx:
            user += f"{ctx}\n\n"
        user += f"User Query: {query}\n\nGenerate the tool call JSON:"
        msgs = [{"role": "system", "content": _M2A_SYSTEM},
                {"role": "user", "content": user}]
        raw = generate(llm, msgs)
        pred = _m2a_parse_tool_call(raw)

        ta = _m2a_tool_accuracy(pred, gold)
        prec, rec, f1 = _m2a_f1(pred, gold)
        b1 = _m2a_bleu1(pred, gold)

        metrics["tool_accuracy"].append(ta)
        metrics["f1"].append(f1)
        metrics["precision"].append(prec)
        metrics["recall"].append(rec)
        metrics["bleu1"].append(b1)

        if level not in level_metrics:
            level_metrics[level] = {"tool_accuracy": [], "f1": [], "bleu1": []}
        level_metrics[level]["tool_accuracy"].append(ta)
        level_metrics[level]["f1"].append(f1)
        level_metrics[level]["bleu1"].append(b1)

        if (i + 1) % 25 == 0:
            avg_ta = np.mean(metrics["tool_accuracy"])
            avg_f1 = np.mean(metrics["f1"])
            print(f"  [{i+1}/{len(items)}] TA={avg_ta:.3f} F1={avg_f1:.3f}")

    elapsed = time.time() - t0
    n = len(metrics["tool_accuracy"])
    report = {
        "benchmark": "Mem2ActBench", "condition": "mimir",
        "n_evaluated": n, "time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
        "overall": {k: float(np.mean(v)) for k, v in metrics.items()},
        "per_level": {},
    }
    for lvl, lm in sorted(level_metrics.items()):
        report["per_level"][lvl] = {
            "n": len(lm["tool_accuracy"]),
            "tool_accuracy": float(np.mean(lm["tool_accuracy"])),
            "f1": float(np.mean(lm["f1"])),
            "bleu1": float(np.mean(lm["bleu1"])),
        }
    return report


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 2: MemoryBench — WritingPrompts generation quality
# ══════════════════════════════════════════════════════════════════════════

def bench_memorybench(max_train=100, max_test=50, quick=False):
    """MemoryBench WritingPrompts with Mimir episodic memory."""
    from tqdm import tqdm
    if quick:
        max_train, max_test = 30, 15
    llm = load_llm()

    print(f"\n{'='*70}")
    print(f"  BENCH 2: MemoryBench (WritingPrompts)  train={max_train} test={max_test}")
    print(f"{'='*70}")

    orig_dir = os.getcwd()
    os.chdir(str(MEMORYBENCH_DIR))
    if str(MEMORYBENCH_DIR) not in sys.path:
        sys.path.insert(0, str(MEMORYBENCH_DIR))
    try:
        from memorybench import load_memory_bench
        dataset_train = load_memory_bench("single", "WritingPrompts", eval_mode=False)
        dataset_eval = load_memory_bench("single", "WritingPrompts", eval_mode=True)
    finally:
        os.chdir(orig_dir)

    train_data = list(dataset_train.dataset["train"])[:max_train]
    test_data = list(dataset_eval.dataset["test"])[:max_test]
    random.seed(42)
    random.shuffle(train_data)
    random.seed(1042)
    random.shuffle(test_data)

    print(f"  Train: {len(train_data)}, Test: {len(test_data)}")

    # Build Mimir from training dialogues
    mem_dir = tempfile.mkdtemp(prefix="bm_mb_")
    mind = Mimir(data_dir=os.path.join(mem_dir, "m"), chemistry=False)

    for d in tqdm(train_data, desc="mb-store"):
        dialog = d.get("dialog", [])
        fb = d.get("implicit_feedback", [])
        for i, turn in enumerate(dialog):
            if isinstance(turn, dict):
                text = turn.get("content", turn.get("text", str(turn)))
            else:
                text = str(turn)
            if len(text.strip()) < 5:
                continue
            emotion = simple_emotion(text)
            imp = 7 if (fb and i < len(fb) and fb[i]) else 5
            mind.remember(content=text[:500], emotion=emotion, importance=imp)
    mind.save()
    print(f"  Mimir: {len(mind._reflections)} memories stored")

    # Evaluate
    preds = []
    t0 = time.time()
    for d in tqdm(test_data, desc="mb-eval"):
        test_idx = d["test_idx"]
        prompt = d.get("input_prompt", "")
        if not prompt and "input_chat_messages" in d:
            prompt = d["input_chat_messages"][-1]["content"]

        resonant = mind.resonate(prompt, limit=5)
        if resonant:
            mem_lines = [f"- {r.content[:300]}" for r in resonant]
            mem_block = "\n".join(mem_lines)
            user_content = (
                f"Relevant past experience:\n{mem_block}\n\n"
                f"Now respond to: {prompt}")
        else:
            user_content = prompt

        msgs = [
            {"role": "system", "content": "You are a helpful assistant. Answer concisely. Use relevant experience provided to improve your response."},
            {"role": "user", "content": user_content},
        ]
        response = generate(llm, msgs, max_tokens=1024, temperature=0.7)
        preds.append({"test_idx": test_idx, "response": response, "dataset": "WritingPrompts"})

    elapsed = time.time() - t0

    # Evaluate with MemoryBench scorer
    os.chdir(str(MEMORYBENCH_DIR))
    try:
        from memorybench import evaluate, summary_results
        details = evaluate("single", "WritingPrompts", preds)
        summary = summary_results("single", "WritingPrompts", preds, details)
    finally:
        os.chdir(orig_dir)
    shutil.rmtree(mem_dir, ignore_errors=True)

    report = {
        "benchmark": "MemoryBench", "condition": "mimir",
        "dataset": "WritingPrompts", "seed": 42,
        "n_train": len(train_data), "n_test": len(test_data),
        "time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
        "overall": summary["summary"],
    }
    return report


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 3: LoCoMo — Evidence Recall@k by category
# ══════════════════════════════════════════════════════════════════════════

def bench_locomo(quick=False):
    """LoCoMo: retrieve evidence turns for conversation memory questions."""
    from datasets import load_dataset

    print(f"\n{'='*70}")
    print(f"  BENCH 3: LoCoMo — Evidence Recall@k")
    print(f"{'='*70}")

    ds = load_dataset("KhangPTT373/locomo_preprocess", split="test")
    print(f"  {len(ds)} dialogues loaded")

    CAT_NAMES = {1: "single-hop", 2: "multi-hop", 3: "open-domain",
                 4: "adversarial", 5: "temporal"}
    K_VALUES = [1, 3, 5, 10]

    mimir_hits = {k: defaultdict(int) for k in K_VALUES}
    tfidf_hits = {k: defaultdict(int) for k in K_VALUES}
    cat_totals = defaultdict(int)
    total = 0

    max_dialogues = 5 if quick else len(ds)
    t0 = time.time()

    for d_idx in range(min(max_dialogues, len(ds))):
        ex = ds[d_idx]
        turns = ex.get("turns", [])
        sessions = ex.get("sessions", [])
        questions = ex.get("questions", [])
        evidences_raw = ex.get("evidences", [])
        categories = ex.get("category", [])

        if not turns or not questions:
            continue

        elapsed = time.time() - t0
        print(f"  Dialogue {d_idx}: {len(questions)} Qs, {len(turns)} turns ({elapsed:.1f}s)")

        # Build session turn offsets
        session_turn_counts = []
        cursor = 0
        for s in sessions:
            if isinstance(s, str):
                lines = [l for l in s.strip().split("\n") if l.strip()]
                n_turns = max(len(lines) - 1, 0)
            else:
                n_turns = 0
            session_turn_counts.append((cursor, n_turns))
            cursor += n_turns

        # Build Mimir + TF-IDF
        tmpdir = tempfile.mkdtemp()
        m = Mimir(data_dir=tmpdir, chemistry=False)
        tfidf = TFIDFBaseline()

        turn_texts = []
        for t in turns:
            text = t if isinstance(t, str) else str(t)
            turn_texts.append(text)
            if len(text.strip()) > 3:
                m.remember(text, "neutral", 5)
                tfidf.add(text)
        tfidf.build()

        for q_idx, question in enumerate(questions):
            cat = categories[q_idx] if q_idx < len(categories) else 0
            if cat == 4:
                continue
            evidence = evidences_raw[q_idx] if q_idx < len(evidences_raw) else []
            if not evidence:
                continue

            evidence_globals = set()
            for ev in evidence:
                if isinstance(ev, (list, tuple)) and len(ev) == 2:
                    s_0 = ev[0] - 1
                    t_0 = ev[1] - 1
                    if 0 <= s_0 < len(session_turn_counts):
                        start, count = session_turn_counts[s_0]
                        if 0 <= t_0 < count:
                            evidence_globals.add(start + t_0)

            if not evidence_globals:
                continue

            evidence_words = set()
            for idx in evidence_globals:
                if idx < len(turn_texts):
                    evidence_words |= _resonance_words(turn_texts[idx])

            if not evidence_words:
                continue

            total += 1
            cat_totals[cat] += 1

            # Mimir retrieval
            recalled = m.recall(question, limit=max(K_VALUES))
            recalled_texts = [r.content for r in recalled]

            # TF-IDF retrieval
            tfidf_indices = tfidf.query(question, top_k=max(K_VALUES))
            tfidf_texts = [tfidf.docs[i] for i in tfidf_indices]

            for k in K_VALUES:
                # Mimir
                for rt in recalled_texts[:k]:
                    if word_coverage_match(evidence_words, _resonance_words(rt)):
                        mimir_hits[k][cat] += 1
                        break
                # TF-IDF
                for tt in tfidf_texts[:k]:
                    if word_coverage_match(evidence_words, _resonance_words(tt)):
                        tfidf_hits[k][cat] += 1
                        break

        shutil.rmtree(tmpdir, ignore_errors=True)

    elapsed = time.time() - t0

    report = {
        "benchmark": "LoCoMo", "condition": "mimir",
        "n_questions": total, "time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
        "overall": {},
        "per_category": {},
        "tfidf_baseline": {},
    }
    for k in K_VALUES:
        m_total = sum(mimir_hits[k].values())
        t_total = sum(tfidf_hits[k].values())
        report["overall"][f"recall@{k}"] = m_total / max(total, 1)
        report["tfidf_baseline"][f"recall@{k}"] = t_total / max(total, 1)

    for cat in sorted(cat_totals.keys()):
        n = cat_totals[cat]
        if n == 0:
            continue
        cat_name = CAT_NAMES.get(cat, f"cat-{cat}")
        report["per_category"][cat_name] = {"n": n}
        for k in K_VALUES:
            report["per_category"][cat_name][f"recall@{k}"] = mimir_hits[k].get(cat, 0) / n

    return report


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 4: LongMemEval — Long conversation memory retrieval
# ══════════════════════════════════════════════════════════════════════════

def bench_longmemeval(quick=False):
    """LongMemEval: retrieve answer-bearing turns from conversation history."""
    from huggingface_hub import hf_hub_download

    print(f"\n{'='*70}")
    print(f"  BENCH 4: LongMemEval — Long Conversation Memory")
    print(f"{'='*70}")

    path = hf_hub_download("xiaowu0162/longmemeval", "longmemeval_oracle",
                           repo_type="dataset")
    data = json.load(open(path))
    print(f"  {len(data)} questions loaded")

    max_items = 50 if quick else len(data)
    K_VALUES = [1, 3, 5, 10]

    cat_names = sorted(set(d["question_type"] for d in data))
    mimir_hits = {k: defaultdict(int) for k in K_VALUES}
    tfidf_hits = {k: defaultdict(int) for k in K_VALUES}
    cat_totals = defaultdict(int)
    total = 0

    t0 = time.time()
    items = data[:max_items]

    for i, item in enumerate(items):
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(items)}] ({elapsed:.1f}s)")

        question = item["question"]
        answer = str(item["answer"]).lower()
        q_type = item["question_type"]
        haystack = item["haystack_sessions"]  # list of session lists

        # Store all turns
        tmpdir = tempfile.mkdtemp()
        m = Mimir(data_dir=tmpdir, chemistry=False)
        tfidf = TFIDFBaseline()

        all_turns = []
        answer_indices = set()

        for sess in haystack:
            for turn in sess:
                text = turn.get("content", "")
                has_ans = turn.get("has_answer", False)
                idx = len(all_turns)
                all_turns.append(text)
                if has_ans:
                    answer_indices.add(idx)
                if len(text.strip()) > 3:
                    m.remember(text[:500], "neutral", 5)
                    tfidf.add(text)
        tfidf.build()

        if not answer_indices:
            shutil.rmtree(tmpdir, ignore_errors=True)
            continue

        total += 1
        cat_totals[q_type] += 1

        # Build answer evidence words from answer-bearing turns
        evidence_words = set()
        for idx in answer_indices:
            evidence_words |= _resonance_words(all_turns[idx])
        # Also include the gold answer words themselves
        answer_words = _resonance_words(answer)

        # Mimir retrieval
        recalled = m.recall(question, limit=max(K_VALUES))
        recalled_texts = [r.content for r in recalled]

        # TF-IDF retrieval
        tfidf_indices = tfidf.query(question, top_k=max(K_VALUES))
        tfidf_texts = [tfidf.docs[i] for i in tfidf_indices]

        for k in K_VALUES:
            # Mimir: check if any of top-k contains evidence or answer
            mimir_hit = False
            for rt in recalled_texts[:k]:
                rt_words = _resonance_words(rt)
                if (word_coverage_match(answer_words, rt_words, 0.4) or
                        word_coverage_match(evidence_words, rt_words, 0.25)):
                    mimir_hit = True
                    break
            if mimir_hit:
                mimir_hits[k][q_type] += 1

            # TF-IDF
            tfidf_hit = False
            for tt in tfidf_texts[:k]:
                tt_words = _resonance_words(tt)
                if (word_coverage_match(answer_words, tt_words, 0.4) or
                        word_coverage_match(evidence_words, tt_words, 0.25)):
                    tfidf_hit = True
                    break
            if tfidf_hit:
                tfidf_hits[k][q_type] += 1

        shutil.rmtree(tmpdir, ignore_errors=True)

    elapsed = time.time() - t0

    report = {
        "benchmark": "LongMemEval", "condition": "mimir",
        "n_questions": total, "time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
        "overall": {},
        "per_category": {},
        "tfidf_baseline": {},
    }
    for k in K_VALUES:
        m_total = sum(mimir_hits[k].values())
        t_total = sum(tfidf_hits[k].values())
        report["overall"][f"recall@{k}"] = m_total / max(total, 1)
        report["tfidf_baseline"][f"recall@{k}"] = t_total / max(total, 1)

    for cat in sorted(cat_totals.keys()):
        n = cat_totals[cat]
        if n == 0:
            continue
        report["per_category"][cat] = {"n": n}
        for k in K_VALUES:
            report["per_category"][cat][f"recall@{k}"] = mimir_hits[k].get(cat, 0) / n

    return report


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 5: MSC — Multi-Session Chat persona fact retrieval
# ══════════════════════════════════════════════════════════════════════════

def bench_msc(max_dialogues=200, quick=False):
    """MSC: retrieve conversation memories relevant to persona facts."""
    from datasets import load_dataset

    if quick:
        max_dialogues = 30

    print(f"\n{'='*70}")
    print(f"  BENCH 5: MSC — Persona Fact Recall@k  (max {max_dialogues} dialogues)")
    print(f"{'='*70}")

    ds = load_dataset("nayohan/multi_session_chat", split="train")
    print(f"  {len(ds)} sessions loaded")

    dialogues = defaultdict(list)
    for row in ds:
        dialogues[row["dialoug_id"]].append(row)
    for did in dialogues:
        dialogues[did].sort(key=lambda r: r["session_id"])

    K_VALUES = [1, 3, 5, 10]
    mimir_hits = {k: 0 for k in K_VALUES}
    tfidf_hits = {k: 0 for k in K_VALUES}
    total = 0

    t0 = time.time()
    sample_ids = sorted(dialogues.keys())[:max_dialogues]

    for prog, did in enumerate(sample_ids):
        sessions = dialogues[did]

        if (prog + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  [{prog+1}/{len(sample_ids)}] ({elapsed:.1f}s)")

        persona_facts = set()
        all_turns = []
        for sess in sessions:
            for p in (sess.get("persona1", []) + sess.get("persona2", [])):
                if p and len(p.strip()) > 5:
                    persona_facts.add(p.strip())
            for turn in sess.get("dialogue", []):
                text = turn if isinstance(turn, str) else str(turn)
                if len(text.strip()) > 5:
                    all_turns.append(text)

        if not persona_facts or not all_turns:
            continue

        tmpdir = tempfile.mkdtemp()
        m = Mimir(data_dir=tmpdir, chemistry=False)
        tfidf = TFIDFBaseline()

        for turn in all_turns:
            m.remember(turn, "neutral", 5)
            tfidf.add(turn)
        tfidf.build()

        for fact in persona_facts:
            fact_words = _resonance_words(fact)
            if not fact_words:
                continue
            total += 1

            recalled = m.recall(fact, limit=max(K_VALUES))
            recalled_texts = [r.content for r in recalled]

            tfidf_indices = tfidf.query(fact, top_k=max(K_VALUES))
            tfidf_texts = [tfidf.docs[i] for i in tfidf_indices]

            for k in K_VALUES:
                for rt in recalled_texts[:k]:
                    if jaccard_match(fact_words, _resonance_words(rt)):
                        mimir_hits[k] += 1
                        break
                for tt in tfidf_texts[:k]:
                    if jaccard_match(fact_words, _resonance_words(tt)):
                        tfidf_hits[k] += 1
                        break

        shutil.rmtree(tmpdir, ignore_errors=True)

    elapsed = time.time() - t0

    report = {
        "benchmark": "MSC", "condition": "mimir",
        "n_dialogues": len(sample_ids), "n_queries": total,
        "time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
        "overall": {},
        "tfidf_baseline": {},
    }
    for k in K_VALUES:
        report["overall"][f"recall@{k}"] = mimir_hits[k] / max(total, 1)
        report["tfidf_baseline"][f"recall@{k}"] = tfidf_hits[k] / max(total, 1)

    return report


# ══════════════════════════════════════════════════════════════════════════
#  BENCH 6: MTEB — STS-B Spearman + GoEmotions kNN accuracy
# ══════════════════════════════════════════════════════════════════════════

_KEYWORD_EMOTIONS = {
    "happy": "happy", "glad": "happy", "joy": "happy", "love": "love",
    "sad": "sad", "sorry": "sad", "upset": "sad", "cry": "sad",
    "angry": "angry", "mad": "angry", "furious": "angry",
    "afraid": "fearful", "fear": "fearful", "scared": "fearful",
    "surprise": "surprised", "wow": "surprised", "shocked": "surprised",
    "disgust": "disgusted", "gross": "disgusted",
    "anxious": "anxious", "worried": "anxious", "nervous": "anxious",
    "grateful": "grateful", "thank": "grateful",
    "proud": "proud", "excited": "excited", "hope": "hopeful",
}


def _infer_emotion(text):
    t = text.lower()
    for kw, emo in _KEYWORD_EMOTIONS.items():
        if kw in t:
            return emo
    return "neutral"


def bench_mteb(quick=False):
    """MTEB sub-benchmarks: STS-B Spearman + GoEmotions kNN accuracy."""
    from scipy.stats import spearmanr
    from datasets import load_dataset
    from sentence_transformers import SentenceTransformer
    from VividEmbed import VividEmbed

    print(f"\n{'='*70}")
    print(f"  BENCH 6: MTEB — STS-B + GoEmotions")
    print(f"{'='*70}")

    ve = VividEmbed()
    base_model = SentenceTransformer("all-MiniLM-L6-v2")

    # ── STS-B ────────────────────────────────────────────────────────
    print("\n  Loading STS-B...")
    sts = load_dataset("sentence-transformers/stsb", split="test")
    if quick:
        sts = sts.select(range(min(200, len(sts))))
    print(f"  {len(sts)} pairs")

    s1 = sts["sentence1"]
    s2 = sts["sentence2"]
    human_scores = np.array(sts["score"])

    # MiniLM baseline
    print("  Encoding MiniLM baseline...")
    t0 = time.time()
    e1_base = base_model.encode(s1, batch_size=128, show_progress_bar=False)
    e2_base = base_model.encode(s2, batch_size=128, show_progress_bar=False)
    cos_base = np.array([
        float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        for a, b in zip(e1_base, e2_base)])
    spearman_base, _ = spearmanr(human_scores, cos_base)
    base_time = time.time() - t0

    # VividEmbed (neutral)
    print("  Encoding VividEmbed (neutral)...")
    t0 = time.time()
    e1_vivid = np.array([ve._encode_memory(s, emotion="neutral", importance=5) for s in s1])
    e2_vivid = np.array([ve._encode_memory(s, emotion="neutral", importance=5) for s in s2])
    cos_vivid = np.array([
        float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        for a, b in zip(e1_vivid, e2_vivid)])
    spearman_vivid, _ = spearmanr(human_scores, cos_vivid)
    vivid_time = time.time() - t0

    # VividEmbed (emotion-inferred)
    print("  Encoding VividEmbed (emotion-inferred)...")
    t0 = time.time()
    e1_emo = np.array([ve._encode_memory(s, emotion=_infer_emotion(s), importance=5) for s in s1])
    e2_emo = np.array([ve._encode_memory(s, emotion=_infer_emotion(s), importance=5) for s in s2])
    cos_emo = np.array([
        float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        for a, b in zip(e1_emo, e2_emo)])
    spearman_emo, _ = spearmanr(human_scores, cos_emo)
    emo_time = time.time() - t0

    sts_report = {
        "minilm_spearman": float(spearman_base),
        "vivid_neutral_spearman": float(spearman_vivid),
        "vivid_emotion_spearman": float(spearman_emo),
        "n_pairs": len(sts),
    }

    # ── GoEmotions kNN ───────────────────────────────────────────────
    print("\n  Loading GoEmotions...")
    ge_train = load_dataset("google-research-datasets/go_emotions", "simplified",
                            split="train")
    ge_test = load_dataset("google-research-datasets/go_emotions", "simplified",
                           split="test")

    max_train_ge = 3000 if quick else 10000
    max_test_ge = 500 if quick else 2000

    # Filter to single-label only
    train_texts, train_labels = [], []
    for row in ge_train:
        labels = row["labels"]
        if len(labels) == 1:
            train_texts.append(row["text"])
            train_labels.append(labels[0])
        if len(train_texts) >= max_train_ge:
            break

    test_texts, test_labels = [], []
    for row in ge_test:
        labels = row["labels"]
        if len(labels) == 1:
            test_texts.append(row["text"])
            test_labels.append(labels[0])
        if len(test_texts) >= max_test_ge:
            break

    print(f"  GoEmotions: {len(train_texts)} train, {len(test_texts)} test")

    # Encode with VividEmbed (emotion-inferred for richer vectors)
    print("  Encoding train (VividEmbed)...")
    t0 = time.time()
    train_embs = np.array([
        ve._encode_memory(t, emotion=_infer_emotion(t), importance=5)
        for t in train_texts])

    print("  Encoding test (VividEmbed)...")
    test_embs = np.array([
        ve._encode_memory(t, emotion=_infer_emotion(t), importance=5)
        for t in test_texts])

    # Encode with MiniLM baseline
    print("  Encoding train (MiniLM baseline)...")
    train_embs_base = base_model.encode(train_texts, batch_size=128,
                                         show_progress_bar=False)
    print("  Encoding test (MiniLM baseline)...")
    test_embs_base = base_model.encode(test_texts, batch_size=128,
                                        show_progress_bar=False)
    ge_time = time.time() - t0

    # kNN (k=5)
    knn_k = 5
    train_labels_np = np.array(train_labels)

    def knn_accuracy(tr_embs, te_embs, tr_labels, k=5):
        # Normalize
        tr_norms = np.linalg.norm(tr_embs, axis=1, keepdims=True) + 1e-9
        te_norms = np.linalg.norm(te_embs, axis=1, keepdims=True) + 1e-9
        tr_normed = tr_embs / tr_norms
        te_normed = te_embs / te_norms
        # Cosine similarity matrix
        sims = te_normed @ tr_normed.T  # (n_test, n_train)
        # Top-k neighbours
        top_k_idx = np.argsort(-sims, axis=1)[:, :k]
        correct = 0
        for i, test_label in enumerate(test_labels):
            neighbour_labels = tr_labels[top_k_idx[i]]
            pred = Counter(neighbour_labels.tolist()).most_common(1)[0][0]
            if pred == test_label:
                correct += 1
        return correct / len(test_labels)

    vivid_acc = knn_accuracy(train_embs, test_embs, train_labels_np, knn_k)
    base_acc = knn_accuracy(train_embs_base, test_embs_base, train_labels_np, knn_k)

    ge_report = {
        "vivid_knn_accuracy": float(vivid_acc),
        "minilm_knn_accuracy": float(base_acc),
        "knn_k": knn_k,
        "n_train": len(train_texts),
        "n_test": len(test_texts),
    }

    report = {
        "benchmark": "MTEB", "condition": "mimir",
        "timestamp": datetime.now().isoformat(),
        "stsb": sts_report,
        "goemotions": ge_report,
    }
    return report


# ══════════════════════════════════════════════════════════════════════════
#  DASHBOARD — Print comprehensive results
# ══════════════════════════════════════════════════════════════════════════

PREV_RESULTS = {
    "Mem2ActBench": {
        "VividnessMem": {"tool_accuracy": 0.39, "f1": 0.462, "bleu1": 0.611},
        "Mimir (prev)": {"tool_accuracy": 0.47, "f1": 0.541, "bleu1": 0.655},
        "no_memory":    {"tool_accuracy": 0.10, "f1": 0.158, "bleu1": 0.302},
    },
}


def print_dashboard(results):
    print("\n")
    print("=" * 78)
    print("  MIMIR COMPREHENSIVE BENCHMARK DASHBOARD")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 78)

    for r in results:
        bench = r["benchmark"]
        print(f"\n{'─'*78}")
        print(f"  {bench.upper()}")
        print(f"{'─'*78}")

        if bench == "Mem2ActBench":
            o = r["overall"]
            print(f"  {'Metric':<16} {'Mimir':>10} {'VMem':>10} {'no_mem':>10}")
            print(f"  {'-'*48}")
            prev = PREV_RESULTS.get("Mem2ActBench", {})
            for k in ["tool_accuracy", "f1", "precision", "recall", "bleu1"]:
                val = o.get(k, 0)
                vm = prev.get("VividnessMem", {}).get(k, "—")
                nm = prev.get("no_memory", {}).get(k, "—")
                vm_s = f"{vm:.3f}" if isinstance(vm, float) else vm
                nm_s = f"{nm:.3f}" if isinstance(nm, float) else nm
                print(f"  {k:<16} {val:>10.3f} {vm_s:>10} {nm_s:>10}")
            if r.get("per_level"):
                print(f"\n  Per-Level:")
                for lvl, lm in sorted(r["per_level"].items()):
                    print(f"    {lvl} (n={lm['n']}): TA={lm['tool_accuracy']:.3f} "
                          f"F1={lm['f1']:.3f} BLEU-1={lm['bleu1']:.3f}")

        elif bench == "MemoryBench":
            o = r.get("overall", {})
            print(f"  Dataset: {r.get('dataset', '?')}")
            print(f"  Train: {r.get('n_train', '?')}, Test: {r.get('n_test', '?')}")
            print(f"  Metrics:")
            for k, v in sorted(o.items()):
                print(f"    {k:<20}: {v:.4f}" if isinstance(v, float)
                      else f"    {k:<20}: {v}")

        elif bench in ("LoCoMo", "LongMemEval"):
            o = r.get("overall", {})
            bl = r.get("tfidf_baseline", {})
            print(f"  Questions: {r.get('n_questions', '?')}")
            print(f"  {'Metric':<16} {'Mimir':>10} {'TF-IDF':>10} {'Delta':>10}")
            print(f"  {'-'*48}")
            for k in sorted(o.keys()):
                m_val = o[k]
                t_val = bl.get(k, 0)
                delta = m_val - t_val
                sign = "+" if delta >= 0 else ""
                print(f"  {k:<16} {m_val:>9.1%} {t_val:>9.1%} {sign}{delta:>9.1%}")
            # Per-category
            cats = r.get("per_category", {})
            if cats:
                print(f"\n  By Category:")
                for cat, cv in sorted(cats.items()):
                    n = cv.get("n", 0)
                    r5 = cv.get("recall@5", 0)
                    print(f"    {cat:<25} (n={n:>3}): R@5={r5:.1%}")

        elif bench == "MSC":
            o = r.get("overall", {})
            bl = r.get("tfidf_baseline", {})
            print(f"  Dialogues: {r.get('n_dialogues', '?')}, Queries: {r.get('n_queries', '?')}")
            print(f"  {'Metric':<16} {'Mimir':>10} {'TF-IDF':>10} {'Delta':>10}")
            print(f"  {'-'*48}")
            for k in sorted(o.keys()):
                m_val = o[k]
                t_val = bl.get(k, 0)
                delta = m_val - t_val
                sign = "+" if delta >= 0 else ""
                print(f"  {k:<16} {m_val:>9.1%} {t_val:>9.1%} {sign}{delta:>9.1%}")

        elif bench == "MTEB":
            sts = r.get("stsb", {})
            ge = r.get("goemotions", {})
            print(f"\n  STS-B ({sts.get('n_pairs', '?')} pairs):")
            print(f"    MiniLM-L6-v2 Spearman:          {sts.get('minilm_spearman', 0):.4f}")
            print(f"    VividEmbed (neutral) Spearman:   {sts.get('vivid_neutral_spearman', 0):.4f}")
            print(f"    VividEmbed (emotion) Spearman:   {sts.get('vivid_emotion_spearman', 0):.4f}")
            print(f"\n  GoEmotions kNN (k={ge.get('knn_k', '?')}, "
                  f"train={ge.get('n_train', '?')}, test={ge.get('n_test', '?')}):")
            print(f"    MiniLM-L6-v2 Accuracy:           {ge.get('minilm_knn_accuracy', 0):.4f}")
            print(f"    VividEmbed (emotion) Accuracy:    {ge.get('vivid_knn_accuracy', 0):.4f}")

    # Final summary line
    print(f"\n{'='*78}")
    total_time = sum(r.get("time_seconds", 0) for r in results)
    print(f"  Total benchmark time: {total_time:.0f}s ({total_time/60:.1f}m)")
    print("=" * 78)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

ALL_BENCHES = ["mem2act", "memorybench", "locomo", "longmemeval", "msc", "mteb"]
LLM_BENCHES = {"mem2act", "memorybench"}


def main():
    parser = argparse.ArgumentParser(description="Mimir Full Benchmark Suite")
    parser.add_argument("--bench", nargs="+", default=ALL_BENCHES,
                        choices=ALL_BENCHES,
                        help="Which benchmarks to run")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM-requiring benchmarks (1 & 2)")
    parser.add_argument("--quick", action="store_true",
                        help="Fast mode with fewer items")
    parser.add_argument("--max-eval", type=int, default=100,
                        help="Max items for Mem2ActBench")
    args = parser.parse_args()

    benches = [b for b in args.bench
               if not (args.skip_llm and b in LLM_BENCHES)]

    print("\n" + "=" * 78)
    print("  MIMIR FULL BENCHMARK SUITE")
    print(f"  Running: {', '.join(benches)}")
    if args.quick:
        print("  Mode: QUICK (reduced items)")
    print("=" * 78)

    results = []
    tag = datetime.now().strftime("%Y%m%d_%H%M")

    for bench in benches:
        try:
            if bench == "mem2act":
                r = bench_mem2act(max_eval=args.max_eval, quick=args.quick)
            elif bench == "memorybench":
                r = bench_memorybench(quick=args.quick)
            elif bench == "locomo":
                r = bench_locomo(quick=args.quick)
            elif bench == "longmemeval":
                r = bench_longmemeval(quick=args.quick)
            elif bench == "msc":
                r = bench_msc(quick=args.quick)
            elif bench == "mteb":
                r = bench_mteb(quick=args.quick)
            else:
                continue
            results.append(r)
        except Exception as e:
            print(f"\n  [ERROR] {bench}: {e}")
            import traceback
            traceback.print_exc()
            results.append({"benchmark": bench, "error": str(e)})

    print_dashboard(results)

    # Save results
    out_path = RESULTS_DIR / f"MimirFull_{tag}.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n  Results saved: {out_path.name}")


if __name__ == "__main__":
    main()
