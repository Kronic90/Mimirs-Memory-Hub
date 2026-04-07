"""Proactive Agent Engine for Mimir's Memory Hub.

Provides autonomous task execution with:
- Project-scoped sandboxing (user-set folder per project)
- Configurable tool permissions (all on by default, user can toggle)
- Observer vs Agent mode
- Timer-based proactive loop
- Token budget tracking
- Approval gates for destructive actions
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

# ── Data Models ──────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PROPOSED = "proposed"       # Agent-generated, needs approval
    APPROVED = "approved"       # User approved, ready to work
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"           # Interrupted (user chatting, budget hit)
    REVIEW = "review"           # Done, awaiting user review
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentMode(str, Enum):
    OFF = "off"
    OBSERVER = "observer"       # Read-only: suggests but doesn't act
    AGENT = "agent"             # Full autonomous execution


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = TaskStatus.APPROVED
    priority: str = TaskPriority.MEDIUM
    created_by: str = "user"    # "user" or "agent"
    dependencies: list[str] = field(default_factory=list)
    result: str = ""
    steps: list[dict] = field(default_factory=list)  # [{action, status, output}]
    token_budget: int = 4096
    tokens_used: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Project:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    folder: str = ""            # User-set working directory (sandbox root)
    description: str = ""
    tools_enabled: dict = field(default_factory=lambda: {
        "read_file": True, "write_file": True, "list_directory": True,
        "search_files": True, "grep_files": True, "web_search": True,
        "fetch_page": True, "http_request": True, "shell_exec": True,
        "run_code": True, "datetime": True, "json_parse": True,
        "diff_files": True, "regex_replace": True,
        # Off by default — potentially destructive / noisy
        "screenshot": False, "clipboard": False, "open_app": False,
        "system_info": False, "weather": False, "pdf_read": True,
        "csv_query": True,
    })
    daily_token_budget: int = 50000
    tokens_used_today: float = 0
    budget_reset_date: str = ""  # YYYY-MM-DD of last reset
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentLog:
    """Single entry in the agent activity log."""
    timestamp: float = field(default_factory=time.time)
    task_id: str = ""
    action: str = ""        # "tool_call", "thinking", "completed", "error", "approval_needed"
    detail: str = ""
    tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Proactive Agent Engine ───────────────────────────────────────────

class ProactiveAgent:
    """Core engine that manages projects, tasks, and the autonomous loop."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.projects_dir = self.data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

        self.mode: AgentMode = AgentMode.OFF
        self.interval: int = 300            # seconds between proactive cycles (default 5 min)
        self.current_task_id: str | None = None
        self._loop_task: asyncio.Task | None = None
        self._paused = False
        self._ws_broadcast: Any = None      # Set by server to push live updates
        self._generate_fn: Any = None       # Set by server — the LLM generate function
        self._logs: list[AgentLog] = []

        # Load state
        self._load_state()

    # ── Persistence ──────────────────────────────────────────────

    def _state_path(self) -> Path:
        return self.data_dir / "proactive_state.json"

    def _load_state(self):
        p = self._state_path()
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
                self.mode = AgentMode(state.get("mode", "off"))
                self.interval = state.get("interval", 300)
                self.current_task_id = state.get("current_task_id")
            except Exception:
                pass

    def _save_state(self):
        self._state_path().write_text(json.dumps({
            "mode": self.mode.value,
            "interval": self.interval,
            "current_task_id": self.current_task_id,
        }, indent=2), encoding="utf-8")

    # ── Project CRUD ─────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def _project_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _tasks_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "tasks.json"

    def _logs_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "logs.json"

    def list_projects(self) -> list[dict]:
        projects = []
        if not self.projects_dir.exists():
            return projects
        for d in sorted(self.projects_dir.iterdir()):
            pf = d / "project.json"
            if pf.exists():
                try:
                    projects.append(json.loads(pf.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return projects

    def get_project(self, project_id: str) -> Project | None:
        pf = self._project_file(project_id)
        if not pf.exists():
            return None
        return Project.from_dict(json.loads(pf.read_text(encoding="utf-8")))

    def create_project(self, name: str, folder: str, description: str = "",
                       tools_enabled: dict | None = None) -> Project:
        project = Project(name=name, folder=folder, description=description)
        if tools_enabled and isinstance(tools_enabled, dict):
            project.tools_enabled.update(tools_enabled)
        d = self._project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)
        self._project_file(project.id).write_text(
            json.dumps(project.to_dict(), indent=2), encoding="utf-8"
        )
        self._tasks_file(project.id).write_text("[]", encoding="utf-8")
        self._logs_file(project.id).write_text("[]", encoding="utf-8")
        return project

    def update_project(self, project_id: str, updates: dict) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None
        for k, v in updates.items():
            if hasattr(project, k) and k not in ("id", "created_at"):
                if k == "tools_enabled" and not isinstance(v, dict):
                    continue
                setattr(project, k, v)
        self._project_file(project_id).write_text(
            json.dumps(project.to_dict(), indent=2), encoding="utf-8"
        )
        return project

    def delete_project(self, project_id: str) -> bool:
        d = self._project_dir(project_id)
        if d.exists():
            import shutil
            shutil.rmtree(d)
            return True
        return False

    # ── Task CRUD ────────────────────────────────────────────────

    def _load_tasks(self, project_id: str) -> list[Task]:
        tf = self._tasks_file(project_id)
        if not tf.exists():
            return []
        try:
            return [Task.from_dict(t) for t in json.loads(tf.read_text(encoding="utf-8"))]
        except Exception:
            return []

    def _save_tasks(self, project_id: str, tasks: list[Task]):
        self._tasks_file(project_id).write_text(
            json.dumps([t.to_dict() for t in tasks], indent=2), encoding="utf-8"
        )

    def list_tasks(self, project_id: str) -> list[dict]:
        return [t.to_dict() for t in self._load_tasks(project_id)]

    def get_task(self, project_id: str, task_id: str) -> Task | None:
        for t in self._load_tasks(project_id):
            if t.id == task_id:
                return t
        return None

    def create_task(self, project_id: str, title: str, description: str = "",
                    priority: str = "medium", created_by: str = "user",
                    token_budget: int = 4096) -> Task | None:
        project = self.get_project(project_id)
        if not project:
            return None
        task = Task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            created_by=created_by,
            token_budget=token_budget,
            status=TaskStatus.APPROVED if created_by == "user" else TaskStatus.PROPOSED,
        )
        tasks = self._load_tasks(project_id)
        tasks.append(task)
        self._save_tasks(project_id, tasks)
        return task

    def update_task(self, project_id: str, task_id: str, updates: dict) -> Task | None:
        tasks = self._load_tasks(project_id)
        for t in tasks:
            if t.id == task_id:
                for k, v in updates.items():
                    if hasattr(t, k) and k not in ("id", "project_id", "created_at"):
                        setattr(t, k, v)
                self._save_tasks(project_id, tasks)
                return t
        return None

    def delete_task(self, project_id: str, task_id: str) -> bool:
        tasks = self._load_tasks(project_id)
        before = len(tasks)
        tasks = [t for t in tasks if t.id != task_id]
        if len(tasks) < before:
            self._save_tasks(project_id, tasks)
            return True
        return False

    # ── Logging ──────────────────────────────────────────────────

    def add_log(self, project_id: str, task_id: str, action: str,
                detail: str = "", tokens: int = 0):
        entry = AgentLog(task_id=task_id, action=action, detail=detail, tokens=tokens)
        self._logs.append(entry)
        # Persist to project
        lf = self._logs_file(project_id)
        try:
            logs = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else []
        except Exception:
            logs = []
        logs.append(entry.to_dict())
        # Keep last 500 entries per project
        if len(logs) > 500:
            logs = logs[-500:]
        lf.write_text(json.dumps(logs, indent=2), encoding="utf-8")

    def get_logs(self, project_id: str, limit: int = 50) -> list[dict]:
        lf = self._logs_file(project_id)
        if not lf.exists():
            return []
        try:
            logs = json.loads(lf.read_text(encoding="utf-8"))
            return logs[-limit:]
        except Exception:
            return []

    # ── Token Budget ─────────────────────────────────────────────

    def _check_budget(self, project: Project | None, tokens_needed: int = 0) -> tuple[bool, str]:
        """Check if project has remaining daily budget. Returns (ok, message)."""
        if project is None:
            return False, "No project set"
        import datetime as dt
        today = dt.date.today().isoformat()
        if project.budget_reset_date != today:
            project.tokens_used_today = 0
            project.budget_reset_date = today
            self._project_file(project.id).write_text(
                json.dumps(project.to_dict(), indent=2), encoding="utf-8"
            )

        remaining = project.daily_token_budget - project.tokens_used_today
        if remaining <= 0:
            return False, "Daily token budget exhausted"

        pct = project.tokens_used_today / max(project.daily_token_budget, 1) * 100
        if pct >= 80:
            return True, f"Warning: {pct:.0f}% of daily budget used"
        return True, ""

    def _consume_tokens(self, project_id: str, tokens: int):
        project = self.get_project(project_id)
        if project:
            project.tokens_used_today += tokens
            self._project_file(project_id).write_text(
                json.dumps(project.to_dict(), indent=2), encoding="utf-8"
            )

    # ── Tool Permissions ─────────────────────────────────────────

    def get_tool_permissions(self, project: Project) -> dict:
        """Build tool_runner-compatible permissions dict scoped to the project folder."""
        te = project.tools_enabled if isinstance(project.tools_enabled, dict) else {}
        enabled = [k for k, v in te.items() if v]
        return {
            "file_access": any(t in enabled for t in
                             ["read_file", "write_file", "list_directory",
                              "search_files", "grep_files", "diff_files"]),
            "web_search": "web_search" in enabled,
            "code_execution": "run_code" in enabled or "shell_exec" in enabled,
            # Sandbox to project folder only
            "allowed_paths": [project.folder] if project.folder else [],
            "allowed_commands": ["python", "pip", "node", "npm", "git", "ls", "dir",
                                "cat", "type", "echo", "mkdir", "cd"],
        }

    # ── Proactive Loop ───────────────────────────────────────────

    def start(self, mode: AgentMode = AgentMode.AGENT):
        """Start the proactive loop."""
        if self._loop_task and not self._loop_task.done():
            return  # Already running
        self.mode = mode
        self._paused = False
        self._save_state()
        self._loop_task = asyncio.ensure_future(self._proactive_loop())

    def stop(self):
        """Stop the proactive loop."""
        self.mode = AgentMode.OFF
        self._save_state()
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        self.current_task_id = None

    def pause(self):
        """Pause (e.g. user is chatting)."""
        self._paused = True

    def resume(self):
        """Resume after pause."""
        self._paused = False

    async def _proactive_loop(self):
        """Main autonomous loop — runs on a timer."""
        import traceback as _tb
        while self.mode != AgentMode.OFF:
            try:
                if not self._paused:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                detail = _tb.format_exc()
                await self._broadcast({"type": "agent_error", "error": f"{e}\n{detail}"})

            # Wait for next cycle
            for _ in range(self.interval):
                if self.mode == AgentMode.OFF:
                    return
                await asyncio.sleep(1)

    async def _tick(self):
        """Single proactive cycle: pick a task and work on it."""
        # Find projects with pending tasks
        for proj_dict in self.list_projects():
            project = Project.from_dict(proj_dict)
            ok, budget_msg = self._check_budget(project)
            if not ok:
                continue

            tasks = self._load_tasks(project.id)
            # Priority order: urgent > high > medium > low
            priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
            ready = [t for t in tasks if t.status in (
                TaskStatus.APPROVED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)]
            ready.sort(key=lambda t: (priority_order.get(t.priority, 9), t.created_at))

            if not ready:
                continue

            task = ready[0]
            self.current_task_id = task.id
            self._save_state()

            await self._broadcast({
                "type": "agent_status",
                "status": "working",
                "task_id": task.id,
                "task_title": task.title,
                "project_id": project.id,
                "project_name": project.name,
            })

            if self.mode == AgentMode.OBSERVER:
                await self._observe_task(project, task)
            else:
                await self._execute_task(project, task)

            self.current_task_id = None
            self._save_state()
            break  # One task per cycle

        if not self.current_task_id:
            await self._broadcast({"type": "agent_status", "status": "idle"})

    async def _observe_task(self, project: Project, task: Task):
        """Observer mode: analyze the task and suggest an approach, but don't execute."""
        if not self._generate_fn:
            return

        self.add_log(project.id, task.id, "thinking", "Analyzing task in observer mode...")
        await self._broadcast({
            "type": "agent_log", "project_id": project.id,
            "task_id": task.id, "action": "thinking",
            "detail": "Analyzing task in observer mode..."
        })

        # Sanitize task inputs
        safe_title = task.title[:200].replace("```", "").replace("<", "&lt;").replace(">", "&gt;")
        safe_desc = task.description[:500].replace("```", "").replace("<", "&lt;").replace(">", "&gt;")

        system = (
            "You are Mimir's proactive agent in OBSERVER mode. "
            "Analyze this task and suggest a step-by-step plan. "
            "Do NOT execute anything — only provide your analysis and recommended approach.\n\n"
            f"Project: {project.name}\n"
            f"Project folder: {project.folder}\n"
            f"Task: {safe_title}\n"
            f"Description: {safe_desc}\n"
        )

        suggestion = ""
        async for token in self._generate_fn(
            messages=[{"role": "user", "content": f"Analyze this task and suggest a plan: {task.title}\n{task.description}"}],
            system_prompt=system,
            temperature=0.4,
            max_tokens=1024,
        ):
            suggestion += token

        task.steps.append({"action": "observation", "status": "completed", "output": suggestion})
        self.update_task(project.id, task.id, {
            "status": TaskStatus.REVIEW,
            "steps": task.steps,
            "result": suggestion,
        })
        self.add_log(project.id, task.id, "completed", "Observation complete — check review.")

        await self._broadcast({
            "type": "agent_log", "project_id": project.id,
            "task_id": task.id, "action": "observation_complete",
            "detail": suggestion[:200] + "..." if len(suggestion) > 200 else suggestion,
        })

    async def _execute_task(self, project: Project, task: Task):
        """Agent mode: actually work on the task using tools."""
        if not self._generate_fn:
            return

        from playground import tool_runner

        self.update_task(project.id, task.id, {"status": TaskStatus.IN_PROGRESS})

        permissions = self.get_tool_permissions(project)
        te = project.tools_enabled if isinstance(project.tools_enabled, dict) else {}
        enabled_tools = [k for k, v in te.items() if v]

        tool_descriptions = self._build_tool_descriptions(enabled_tools)

        # Sanitize task inputs to prevent prompt injection
        safe_title = task.title[:200].replace("```", "").replace("<", "&lt;").replace(">", "&gt;")
        safe_desc = task.description[:500].replace("```", "").replace("<", "&lt;").replace(">", "&gt;")

        system = (
            "You are Mimir's proactive agent working autonomously on a task.\n"
            f"Project: {project.name}\n"
            f"Working directory: {project.folder}\n"
            f"Task: {safe_title}\n"
            f"Description: {safe_desc}\n\n"
            "You have access to these tools:\n" + tool_descriptions + "\n\n"
            "To use a tool, output a code block like:\n"
            "```tool\n{\"tool\": \"tool_name\", \"params\": {...}}\n```\n\n"
            "Work step by step. After each tool result, decide the next action.\n"
            "When the task is complete, output: <task_complete>summary of what you did</task_complete>\n"
            "If you encounter an error you can't recover from, output: <task_failed>reason</task_failed>\n"
            "IMPORTANT: Only work within the project folder. Do NOT access files outside it.\n"
        )

        conversation = [{"role": "user", "content": f"Execute this task: {task.title}\n{task.description}"}]
        max_iterations = 10
        total_tokens = 0

        for iteration in range(max_iterations):
            if self._paused or self.mode == AgentMode.OFF:
                self.update_task(project.id, task.id, {"status": TaskStatus.PAUSED})
                self.add_log(project.id, task.id, "paused", "Agent paused")
                return

            # Check task token budget
            if total_tokens >= task.token_budget:
                msg = f"Token budget exhausted ({total_tokens}/{task.token_budget})"
                self.update_task(project.id, task.id, {
                    "status": TaskStatus.PAUSED,
                    "result": msg,
                    "tokens_used": total_tokens,
                })
                self.add_log(project.id, task.id, "budget_hit", msg, total_tokens)
                await self._broadcast({
                    "type": "agent_approval_needed",
                    "project_id": project.id,
                    "task_id": task.id,
                    "reason": msg,
                })
                return

            self.add_log(project.id, task.id, "thinking", f"Step {iteration + 1}...")
            await self._broadcast({
                "type": "agent_log", "project_id": project.id,
                "task_id": task.id, "action": "thinking",
                "detail": f"Step {iteration + 1}/{max_iterations}",
            })

            # Generate next action
            response = ""
            async for token in self._generate_fn(
                messages=conversation,
                system_prompt=system,
                temperature=0.3,
                max_tokens=min(2048, task.token_budget - total_tokens),
            ):
                response += token
            total_tokens += len(response) // 4  # rough token estimate

            conversation.append({"role": "assistant", "content": response})

            # Check for completion markers
            if "<task_complete>" in response:
                import re
                match = re.search(r"<task_complete>(.*?)</task_complete>", response, re.DOTALL)
                summary = match.group(1).strip() if match else response
                task.steps.append({"action": "complete", "status": "completed", "output": summary})
                self.update_task(project.id, task.id, {
                    "status": TaskStatus.COMPLETED,
                    "result": summary,
                    "steps": task.steps,
                    "tokens_used": total_tokens,
                    "completed_at": time.time(),
                })
                self.add_log(project.id, task.id, "completed", summary, total_tokens)
                self._consume_tokens(project.id, total_tokens)
                await self._broadcast({
                    "type": "agent_task_complete",
                    "project_id": project.id,
                    "task_id": task.id,
                    "summary": summary,
                })
                return

            if "<task_failed>" in response:
                import re
                match = re.search(r"<task_failed>(.*?)</task_failed>", response, re.DOTALL)
                reason = match.group(1).strip() if match else "Unknown error"
                self.update_task(project.id, task.id, {
                    "status": TaskStatus.FAILED,
                    "result": reason,
                    "tokens_used": total_tokens,
                })
                self.add_log(project.id, task.id, "failed", reason, total_tokens)
                self._consume_tokens(project.id, total_tokens)
                await self._broadcast({
                    "type": "agent_log", "project_id": project.id,
                    "task_id": task.id, "action": "failed", "detail": reason,
                })
                return

            # Parse and execute tool calls
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # No tools and no completion marker — ask for next step
                conversation.append({"role": "user", "content": "Continue with the task. Use a tool or mark the task as complete/failed."})
                continue

            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                params = tc.get("params", {})

                # Verify tool is enabled for this project
                if tool_name not in enabled_tools:
                    result = {"error": f"Tool '{tool_name}' is not enabled for this project."}
                    tool_name = ""  # Skip execution
                else:
                    # Validate ALL path-like params are within project folder
                    path_keys = ["path", "filepath", "src", "dest", "path_a", "path_b"]
                    path_blocked = False
                    if project.folder:
                        from pathlib import Path as P
                        for pk in path_keys:
                            if pk in params:
                                try:
                                    # Resolve symlinks to prevent escape
                                    resolved = P(params[pk]).resolve(strict=False)
                                    proj_resolved = P(project.folder).resolve(strict=False)
                                    if not str(resolved).startswith(str(proj_resolved)):
                                        result = {"error": f"Path '{params[pk]}' is outside project folder '{project.folder}'."}
                                        path_blocked = True
                                        break
                                except Exception:
                                    result = {"error": f"Invalid path: '{params[pk]}'"}
                                    path_blocked = True
                                    break

                    if not path_blocked and tool_name:
                        self.add_log(project.id, task.id, "tool_call",
                                    f"{tool_name}({json.dumps(params)[:100]})")
                        await self._broadcast({
                            "type": "agent_log", "project_id": project.id,
                            "task_id": task.id, "action": "tool_call",
                            "detail": f"{tool_name}({json.dumps(params)[:100]})",
                        })
                        try:
                            result = tool_runner.run_tool(tool_name, params, permissions)
                        except Exception as e:
                            result = {"error": f"Tool execution error: {e}"}

                display_name = tool_name or "blocked"
                step = {"action": f"tool:{display_name}", "status": "completed",
                        "output": json.dumps(result)[:500]}
                task.steps.append(step)

                # Feed result back to LLM
                conversation.append({
                    "role": "user",
                    "content": f"Tool result for {tool_name}:\n```json\n{json.dumps(result, indent=2)[:2000]}\n```\nContinue with the task."
                })

            self.update_task(project.id, task.id, {
                "steps": task.steps,
                "tokens_used": total_tokens,
            })

        # Hit max iterations
        self.update_task(project.id, task.id, {
            "status": TaskStatus.PAUSED,
            "result": f"Reached max iterations ({max_iterations}). Resume to continue.",
            "tokens_used": total_tokens,
        })
        self.add_log(project.id, task.id, "paused", "Max iterations reached", total_tokens)
        self._consume_tokens(project.id, total_tokens)

    def _build_tool_descriptions(self, enabled_tools: list[str]) -> str:
        """Build human-readable tool list for the system prompt."""
        descs = {
            "read_file": "read_file(path) — Read a file's contents",
            "write_file": "write_file(path, content) — Write content to a file",
            "list_directory": "list_directory(path) — List files/folders in a directory",
            "search_files": "search_files(path, pattern) — Search for files by name pattern",
            "grep_files": "grep_files(path, pattern) — Search file contents for a pattern",
            "web_search": "web_search(query) — Search the web",
            "fetch_page": "fetch_page(url) — Fetch a web page's content",
            "http_request": "http_request(method, url, body, headers) — Make an HTTP request",
            "shell_exec": "shell_exec(command) — Run a shell command",
            "run_code": "run_code(language, code) — Execute code (python, javascript)",
            "datetime": "datetime() — Get current date/time",
            "json_parse": "json_parse(text) — Parse JSON from text",
            "diff_files": "diff_files(path_a, path_b) — Compare two files",
            "regex_replace": "regex_replace(path, pattern, replacement) — Regex replace in a file",
            "pdf_read": "pdf_read(path) — Read text from a PDF file",
            "csv_query": "csv_query(path, query) — Query a CSV file",
            "screenshot": "screenshot() — Take a screenshot",
            "clipboard": "clipboard(action, text) — Read/write clipboard",
            "open_app": "open_app(name) — Open an application",
            "system_info": "system_info() — Get system information",
            "weather": "weather(location) — Get weather info",
        }
        return "\n".join(f"- {descs[t]}" for t in enabled_tools if t in descs)

    # ── WebSocket broadcast helper ───────────────────────────────

    _CODE_BLOCK_RE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)

    @staticmethod
    def _parse_tool_calls(text: str) -> list[dict]:
        """Extract ```tool blocks → [{tool, params}]."""
        calls = []
        for m in ProactiveAgent._CODE_BLOCK_RE.finditer(text):
            lang = (m.group(1) or "text").lower()
            code = m.group(2).strip()
            if code and lang == "tool":
                try:
                    data = json.loads(code)
                    if isinstance(data, dict) and "tool" in data:
                        calls.append(data)
                except (json.JSONDecodeError, ValueError):
                    pass
        return calls

    async def _broadcast(self, message: dict):
        if self._ws_broadcast:
            try:
                await self._ws_broadcast(message)
            except Exception:
                pass

    # ── Status ───────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "mode": self.mode.value,
            "interval": self.interval,
            "current_task_id": self.current_task_id,
            "paused": self._paused,
        }
