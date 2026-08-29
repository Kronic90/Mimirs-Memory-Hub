"""Mimir Yggdrasil mixin — World Tree memory graph (mechanism #13)."""

from __future__ import annotations

from collections import deque
from datetime import datetime

from .constants import (
    YGGDRASIL_WORD_EDGE_MIN, YGGDRASIL_WORD_EDGE_MAX,
    YGGDRASIL_TEMPORAL_DAYS, YGGDRASIL_MAX_EDGES,
    SPREADING_ACTIVATION_HOPS, SPREADING_ACTIVATION_DECAY,
    SPREADING_ACTIVATION_THRESHOLD,
)
from .helpers import _overlap_ratio, _resonance_words
from .models import Memory


class YggdrasilMixin:
    """Mixin providing Yggdrasil graph construction, spreading activation,
    LLM-inferred relational reasoning, and graph traversal."""

    # ══════════════════════════════════════════════════════════════════
    #  Yggdrasil — World Tree (memory graph, mechanism #13)
    # ══════════════════════════════════════════════════════════════════

    def _build_yggdrasil(self):
        """Build the memory graph from scratch.

        Six edge types:
        - entity:       memories sharing the same entity reference
        - lexical:      significant word overlap (related, not duplicate)
        - temporal:     created within the same 3-day window
        - emotional:    same emotion label
        - task_origin:  memories linked to the same task
        - caused_lesson: memory that spawned a lesson, or vice versa
        """
        self._yggdrasil = {}
        n = len(self._reflections)
        if n < 2:
            return

        # Pre-compute per-memory data
        words = [m.content_words for m in self._reflections]
        days = []
        for m in self._reflections:
            try:
                days.append(
                    datetime.fromisoformat(m.timestamp).timestamp()
                    / 86400)
            except Exception:
                days.append(0.0)
        entities = [m.entity.lower() for m in self._reflections]
        emotions = [m.emotion.lower() for m in self._reflections]

        # ── Cross-hierarchy index: gather memory indices linked to
        #    the same task or lesson ──────────────────────────────────
        task_groups: dict[str, list[int]] = {}
        for t in self._project_tasks:
            if t._memory_indices:
                task_groups[t.task_id] = [
                    i for i in t._memory_indices if i < n]

        lesson_linked: set[tuple[int, int]] = set()
        for les in self._lessons:
            if les._source_memory_idx >= 0 and les._source_memory_idx < n:
                src = les._source_memory_idx
                for i in range(max(0, src - 2), min(n, src + 3)):
                    if i != src:
                        lesson_linked.add((src, i))
                        lesson_linked.add((i, src))

        # Build edges
        for i in range(n):
            edges: list[tuple[int, str, float]] = []
            for j in range(n):
                if i == j:
                    continue
                best_type = None
                best_strength = 0.0

                # Entity edge
                if entities[i] and entities[i] == entities[j]:
                    best_type = "entity"
                    best_strength = 0.8

                # Lexical edge
                if words[i] and words[j]:
                    overlap = _overlap_ratio(words[i], words[j])
                    if (YGGDRASIL_WORD_EDGE_MIN <= overlap
                            <= YGGDRASIL_WORD_EDGE_MAX):
                        if overlap > best_strength:
                            best_type = "lexical"
                            best_strength = overlap

                # Temporal edge
                if abs(days[i] - days[j]) <= YGGDRASIL_TEMPORAL_DAYS:
                    temporal_str = 1.0 - (
                        abs(days[i] - days[j]) / YGGDRASIL_TEMPORAL_DAYS)
                    if temporal_str > best_strength:
                        best_type = "temporal"
                        best_strength = temporal_str

                # Emotional edge (same emotion, decent vividness)
                if (emotions[i] == emotions[j]
                        and emotions[i] != "neutral"):
                    if 0.5 > best_strength:
                        best_type = "emotional"
                        best_strength = 0.5

                if best_type and best_strength >= YGGDRASIL_WORD_EDGE_MIN:
                    edges.append((j, best_type, best_strength))

                # Cross-hierarchy edges are additive
                is_task_linked = False
                for _, members in task_groups.items():
                    if i in members and j in members:
                        is_task_linked = True
                        break
                if is_task_linked:
                    edges.append((j, "task_origin", 0.75))

                if (i, j) in lesson_linked:
                    edges.append((j, "caused_lesson", 0.65))

            # Keep only top N edges per node (sorted by strength)
            edges.sort(key=lambda e: e[2], reverse=True)
            self._yggdrasil[i] = edges[:YGGDRASIL_MAX_EDGES]

        # ── LLM-inferred edges (if available) ─────────────────────────
        if self._llm_fn and self._inferred_edges:
            for (src, tgt), strength in self._inferred_edges.items():
                if src < n and tgt < n:
                    edges = self._yggdrasil.get(src, [])
                    existing_targets = {e[0] for e in edges}
                    if tgt not in existing_targets:
                        edges.append((tgt, "inferred", strength))
                        edges.sort(key=lambda e: e[2], reverse=True)
                        self._yggdrasil[src] = edges[:YGGDRASIL_MAX_EDGES]

    def _spreading_activation(
        self,
        seed_indices: set[int],
        hops: int = SPREADING_ACTIVATION_HOPS,
        decay: float = SPREADING_ACTIVATION_DECAY,
        threshold: float = SPREADING_ACTIVATION_THRESHOLD,
    ) -> dict[int, float]:
        """Collins & Loftus 1975 — true spreading activation on Yggdrasil."""
        if not self._yggdrasil:
            return {}

        activation: dict[int, float] = {}
        for idx in seed_indices:
            activation[idx] = 1.0

        frontier = set(seed_indices)
        for hop in range(hops):
            next_frontier: set[int] = set()
            hop_decay = decay ** (hop + 1)
            for node in frontier:
                for target, _etype, strength in self._yggdrasil.get(node, []):
                    transmitted = hop_decay * strength
                    if transmitted < threshold:
                        continue
                    prev = activation.get(target, 0.0)
                    activation[target] = prev + transmitted
                    if target not in seed_indices:
                        next_frontier.add(target)
            frontier = next_frontier
            if not frontier:
                break

        return activation

    def _infer_relations(self, mem_idx: int):
        """Use LLM to discover implicit relationships between a new memory
        and recent memories that lexical/temporal overlap alone would miss."""
        if not self._llm_fn or mem_idx >= len(self._reflections):
            return

        new_mem = self._reflections[mem_idx]
        existing_targets = {
            e[0] for e in self._yggdrasil.get(mem_idx, [])}
        candidates = []
        for i in range(max(0, mem_idx - 30), mem_idx):
            if i not in existing_targets:
                candidates.append((i, self._reflections[i]))
        if not candidates:
            return

        mem_lines = []
        for i, (idx, m) in enumerate(candidates[-15:]):
            mem_lines.append(f"[{i}] {m.gist}")

        prompt = (
            "Given this NEW memory and these EXISTING memories, identify "
            "which existing memories are implicitly related (not by shared "
            "words, but by causal, thematic, or contextual connections). "
            "Return ONLY the indices of related memories, one per line, "
            "with a confidence score 0.3-0.9. Format: idx score\n"
            "Return nothing if no implicit connections exist.\n\n"
            f"NEW: {new_mem.gist}\n\n"
            "EXISTING:\n" + "\n".join(mem_lines)
        )
        try:
            response = self._llm_fn(prompt)
        except Exception:
            return

        sample = candidates[-15:]
        for line in response.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                local_idx = int(parts[0])
                strength = float(parts[1])
            except (ValueError, IndexError):
                continue
            if 0 <= local_idx < len(sample) and 0.3 <= strength <= 0.9:
                real_idx = sample[local_idx][0]
                self._inferred_edges[(mem_idx, real_idx)] = strength
                self._inferred_edges[(real_idx, mem_idx)] = strength
                for src, tgt in [(mem_idx, real_idx), (real_idx, mem_idx)]:
                    edges = self._yggdrasil.get(src, [])
                    existing = {e[0] for e in edges}
                    if tgt not in existing:
                        edges.append((tgt, "inferred", strength))
                        edges.sort(key=lambda e: e[2], reverse=True)
                        self._yggdrasil[src] = edges[:YGGDRASIL_MAX_EDGES]

    def enrich_yggdrasil(self, batch_size: int = 20) -> int:
        """Batch-enrich Yggdrasil with LLM-inferred relationships."""
        if not self._llm_fn:
            return 0
        n = len(self._reflections)
        before = len(self._inferred_edges)
        start = max(0, n - batch_size)
        for i in range(start, n):
            has_inferred = any(
                src == i for (src, _) in self._inferred_edges)
            if not has_inferred:
                self._infer_relations(i)
        return (len(self._inferred_edges) - before) // 2

    def yggdrasil_roots(self) -> list[Memory]:
        """Return the roots of the World Tree — anchor and high-importance
        memories that form the foundation of identity."""
        roots = [
            m for m in self._reflections
            if m._anchor or m._is_flashbulb or m.importance >= 9]
        return sorted(roots, key=lambda m: m.vividness, reverse=True)

    def yggdrasil_branches(self, memory: Memory) -> list[Memory]:
        """Return memories connected to the given memory in the graph."""
        try:
            idx = self._reflections.index(memory)
        except ValueError:
            return []
        edges = self._yggdrasil.get(idx, [])
        result = []
        for target_idx, edge_type, strength in edges:
            if target_idx < len(self._reflections):
                result.append(self._reflections[target_idx])
        return result

    def yggdrasil_traverse(self, memory: Memory,
                           depth: int = 2) -> list[Memory]:
        """BFS traversal from a memory, returning all reachable nodes
        within *depth* hops."""
        try:
            start = self._reflections.index(memory)
        except ValueError:
            return []
        visited: set[int] = {start}
        frontier = [start]
        for _ in range(depth):
            next_frontier: list[int] = []
            for idx in frontier:
                for target, _, _ in self._yggdrasil.get(idx, []):
                    if target not in visited and target < len(self._reflections):
                        visited.add(target)
                        next_frontier.append(target)
            frontier = next_frontier
        visited.discard(start)
        return [self._reflections[i] for i in sorted(visited)]

    def yggdrasil_path(self, a: Memory, b: Memory) -> list[Memory]:
        """Find shortest path between two memories in the graph."""
        try:
            start = self._reflections.index(a)
            end = self._reflections.index(b)
        except ValueError:
            return []
        if start == end:
            return [a]

        queue: deque[list[int]] = deque([[start]])
        visited: set[int] = {start}
        while queue:
            path = queue.popleft()
            current = path[-1]
            for target, _, _ in self._yggdrasil.get(current, []):
                if target == end:
                    full = path + [target]
                    return [self._reflections[i] for i in full]
                if target not in visited and target < len(self._reflections):
                    visited.add(target)
                    queue.append(path + [target])
        return []
