"""Mimir LLM mixin — decompose_query, edit_memories, reflect."""

from __future__ import annotations

from .helpers import _resonance_words


class LLMMixin:
    """Mixin providing optional LLM-driven operations: query decomposition,
    agentic memory editing, and periodic self-reflection."""

    def decompose_query(self, query: str) -> list[str]:
        """Use LLM to break a vague query into focused sub-queries."""
        if not self._llm_fn:
            return [query]
        prompt = (
            "Break this memory query into 2-4 specific sub-queries "
            "that would help retrieve relevant memories. Return ONLY "
            "the sub-queries, one per line, no numbering.\n\n"
            f"Query: {query}"
        )
        try:
            response = self._llm_fn(prompt)
            lines = [l.strip() for l in response.strip().split("\n")
                     if l.strip()]
            return lines[:4] if lines else [query]
        except Exception:
            return [query]

    def edit_memories(self, instruction: str) -> dict:
        """LLM-driven agentic memory operations."""
        if not self._llm_fn:
            return {"error": "no LLM function configured"}

        recent = sorted(self._reflections, key=lambda m: m.timestamp,
                        reverse=True)[:20]
        mem_lines = []
        for i, m in enumerate(recent):
            mem_lines.append(
                f"[{i}] imp={m.importance} emo={m.emotion} "
                f"content={m.gist}")

        prompt = (
            "You are a memory editor. Given these recent memories and "
            "an instruction, output operations as one-per-line:\n"
            "  PROMOTE idx — boost importance by 2\n"
            "  DEMOTE idx — reduce importance by 2\n"
            "  FORGET idx — mark as forgotten (importance=0)\n"
            "  UPDATE idx new_content — replace content\n\n"
            "Memories:\n" + "\n".join(mem_lines) + "\n\n"
            f"Instruction: {instruction}\n"
            "Output operations only, no explanation."
        )
        try:
            response = self._llm_fn(prompt)
        except Exception as e:
            return {"error": str(e)}

        changes = {"promoted": 0, "demoted": 0,
                   "forgotten": 0, "updated": 0}
        for line in response.strip().split("\n"):
            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue
            op = parts[0].upper()
            try:
                idx = int(parts[1])
            except (ValueError, IndexError):
                continue
            if idx < 0 or idx >= len(recent):
                continue
            mem = recent[idx]
            if op == "PROMOTE":
                mem._importance = min(10, mem.importance + 2)
                changes["promoted"] += 1
            elif op == "DEMOTE":
                mem._importance = max(1, mem.importance - 2)
                changes["demoted"] += 1
            elif op == "FORGET":
                mem._importance = 0
                changes["forgotten"] += 1
            elif op == "UPDATE" and len(parts) == 3:
                mem._content = parts[2]
                mem._content_words = None
                changes["updated"] += 1
        return changes

    def reflect(self) -> str:
        """LLM-driven periodic self-analysis of the memory system."""
        if not self._llm_fn:
            return ""

        s = self.stats()
        summary = (
            f"Memories: {s['total_reflections']}, "
            f"Flashbulbs: {s['flashbulb_count']}, "
            f"Cherished: {s['cherished_count']}, "
            f"Mood: {s['mood']}, "
            f"Lessons: {s['total_lessons']}, "
            f"Drifted: {s['drifted_memories']}, "
            f"Avg novelty: {s['avg_novelty']}"
        )
        recent = sorted(self._reflections, key=lambda m: m.timestamp,
                        reverse=True)[:10]
        mem_text = "\n".join(f"- {m.gist} (emo={m.emotion})"
                            for m in recent)
        prompt = (
            "You are an introspective memory system. Analyze this state "
            "and produce 2-3 brief observations about patterns, emotional "
            "trends, or notable gaps. Be concise.\n\n"
            f"State: {summary}\n\n"
            f"Recent memories:\n{mem_text}"
        )
        try:
            response = self._llm_fn(prompt)
            if response.strip():
                self.remember(
                    content=f"[reflection] {response.strip()[:300]}",
                    emotion="contemplative", importance=4,
                    source="huginn",
                    why_saved="periodic self-analysis")
            return response.strip()
        except Exception:
            return ""
