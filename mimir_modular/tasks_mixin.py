"""Mimir tasks mixin — project/task/solution/artifact CRUD."""

from __future__ import annotations

from .constants import SOLUTION_INITIAL_IMPORTANCE
from .helpers import _resonance_words
from .models import (
    TaskRecord, ActionRecord, SolutionPattern, ArtifactRecord, Lesson,
)


class TasksMixin:
    """Mixin providing the Task / Project Branch — projects, tasks,
    actions, solutions, and artifacts."""

    def set_active_project(self, name: str) -> str:
        """Set (or switch) the active project context."""
        prev = self._active_project
        self._active_project = name
        if prev and prev != name:
            return f"Switched project context: {prev!r} → {name!r}"
        return f"Active project: {name!r}"

    def start_task(self, description: str, priority: int = 5,
                   project: str = "") -> TaskRecord:
        """Create a new task under the active project."""
        proj = project or self._active_project
        t = TaskRecord(description=description, priority=priority,
                       project=proj)
        self._project_tasks.append(t)
        mem = self.remember(
            content=f"[task-started] {description}",
            emotion="determination", importance=priority,
            source="task_branch",
            why_saved="tracking an active task")
        mem_idx = len(self._reflections) - 1
        t._memory_indices.append(mem_idx)
        return t

    def complete_task(self, task_id: str, outcome: str = "") -> bool:
        """Mark a task as completed, releasing its Zeigarnik tension."""
        for t in self._project_tasks:
            if t.task_id == task_id and t.status == "active":
                t.complete(outcome)
                mem = self.remember(
                    content=f"[task-done] {t.description}: {outcome}" if outcome
                           else f"[task-done] {t.description}",
                    emotion="satisfaction", importance=t.priority,
                    source="task_branch",
                    why_saved="recording task completion")
                t._memory_indices.append(len(self._reflections) - 1)
                return True
        return False

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        """Mark a task as failed, recording the lesson."""
        for t in self._project_tasks:
            if t.task_id == task_id and t.status == "active":
                t.fail(reason)
                lesson = self.add_lesson(
                    topic=f"[task-failed] {t.description}",
                    strategy=reason or "unknown failure")
                if t._memory_indices:
                    lesson._source_memory_idx = t._memory_indices[0]
                return True
        return False

    def get_active_tasks(self) -> list[TaskRecord]:
        """Return all currently active tasks."""
        return [t for t in self._project_tasks if t.status == "active"]

    def log_action(self, task_id: str, action: str,
                   result: str = "", error: str = "",
                   fix: str = "") -> ActionRecord:
        """Log an action taken for a task."""
        a = ActionRecord(task_id=task_id, action=action,
                         result=result, error=error, fix=fix)
        self._project_actions.append(a)
        return a

    def record_solution(self, problem: str, solution: str,
                        importance: int = 0) -> SolutionPattern:
        """Store a reusable problem→solution pattern."""
        imp = importance or SOLUTION_INITIAL_IMPORTANCE
        s = SolutionPattern(problem=problem, solution=solution,
                            importance=imp)
        self._solutions.append(s)
        self.add_lesson(topic=problem, strategy=solution)
        return s

    def find_solutions(self, problem: str, top_k: int = 3) -> list[SolutionPattern]:
        """Find matching solution patterns, boosting reuse count."""
        query_words = _resonance_words(problem)
        scored: list[tuple[float, SolutionPattern]] = []
        for s in self._solutions:
            sol_words = _resonance_words(s.search_text)
            overlap = len(query_words & sol_words)
            if overlap == 0:
                continue
            score = overlap * s.vividness
            scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [s for _, s in scored[:top_k]]
        for s in results:
            s.apply()
        return results

    def track_artifact(self, name: str, artifact_type: str = "file",
                       description: str = "", importance: int = 5,
                       dependencies: list[str] | None = None) -> ArtifactRecord:
        """Track a project artifact (file, model, dataset, etc.)."""
        a = ArtifactRecord(name=name, artifact_type=artifact_type,
                           description=description, importance=importance,
                           dependencies=dependencies or [])
        self._artifacts.append(a)
        return a

    def update_artifact(self, name: str, **updates) -> bool:
        """Update an artifact's fields."""
        for a in self._artifacts:
            if a.name == name:
                for k, v in updates.items():
                    if hasattr(a, k):
                        setattr(a, k, v)
                return True
        return False

    def get_project_overview(self) -> dict:
        """Snapshot of the current project state."""
        active = self.get_active_tasks()
        done = [t for t in self._project_tasks if t.status == "completed"]
        failed = [t for t in self._project_tasks if t.status == "failed"]
        return {
            "project": self._active_project,
            "tasks_active": len(active),
            "tasks_completed": len(done),
            "tasks_failed": len(failed),
            "actions_logged": len(self._project_actions),
            "solutions_stored": len(self._solutions),
            "artifacts_tracked": len(self._artifacts),
            "active_task_descriptions": [t.description for t in active],
        }
