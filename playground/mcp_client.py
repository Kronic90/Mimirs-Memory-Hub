"""MCP (Model Context Protocol) client for connecting to external tool servers.

Supports two transport types:
  - stdio: Launch a local process that communicates via stdin/stdout
  - sse:   Connect to a remote server via HTTP Server-Sent Events

Users can configure MCP servers in Settings → Tools → MCP Servers.
Each server exposes tools that agents can call like built-in tools.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import uuid
from typing import Any

import httpx

log = logging.getLogger(__name__)


class MCPServer:
    """Represents a connected MCP server and its available tools."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command", "")          # stdio
        self.args = config.get("args", [])                # stdio
        self.env = config.get("env", {})                  # stdio
        self.url = config.get("url", "")                  # sse
        self.headers = config.get("headers", {})          # sse
        self.tools: list[dict] = []
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # ── Connection lifecycle ──────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to the MCP server and discover tools."""
        try:
            if self.transport == "stdio":
                return await self._connect_stdio()
            elif self.transport == "sse":
                return await self._connect_sse()
            else:
                log.error("MCP %s: unsupported transport '%s'", self.name, self.transport)
                return False
        except Exception as e:
            log.error("MCP %s connect failed: %s", self.name, e)
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from the MCP server."""
        self._connected = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool on this MCP server."""
        try:
            if self.transport == "stdio":
                return await self._call_stdio(tool_name, arguments)
            elif self.transport == "sse":
                return await self._call_sse(tool_name, arguments)
            return {"error": f"Unsupported transport: {self.transport}"}
        except Exception as e:
            return {"error": f"MCP tool call failed: {e}"}

    # ── stdio transport ───────────────────────────────────────────

    async def _connect_stdio(self) -> bool:
        """Launch subprocess and send initialize request."""
        if not self.command:
            log.error("MCP %s: no command specified for stdio transport", self.name)
            return False

        cmd = [self.command] + self.args
        env = {**dict(__import__('os').environ), **self.env} if self.env else None
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=0,
            )
        except FileNotFoundError:
            log.error("MCP %s: command not found: %s", self.name, self.command)
            return False

        # Send initialize
        init_resp = await self._send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "MimirsWell", "version": "1.0"},
        })
        if not init_resp or "error" in init_resp:
            log.error("MCP %s: initialize failed: %s", self.name, init_resp)
            await self.disconnect()
            return False

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # Discover tools
        tools_resp = await self._send_jsonrpc("tools/list", {})
        if tools_resp and "result" in tools_resp:
            self.tools = tools_resp["result"].get("tools", [])
        else:
            self.tools = []

        self._connected = True
        log.info("MCP %s: connected via stdio, %d tools available", self.name, len(self.tools))
        return True

    async def _call_stdio(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via stdio JSON-RPC."""
        if not self._process or self._process.poll() is not None:
            return {"error": "MCP server process not running"}

        resp = await self._send_jsonrpc("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            # Flatten text content
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return {"result": "\n".join(texts) if texts else json.dumps(content)}
        elif resp and "error" in resp:
            return {"error": resp["error"].get("message", str(resp["error"]))}
        return {"error": "No response from MCP server"}

    async def _send_jsonrpc(self, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC request and read the response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        try:
            line = json.dumps(msg) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()

            # Read response with timeout
            loop = asyncio.get_event_loop()
            response_line = await asyncio.wait_for(
                loop.run_in_executor(None, self._process.stdout.readline),
                timeout=30.0,
            )
            if response_line:
                return json.loads(response_line.strip())
            return None
        except asyncio.TimeoutError:
            log.error("MCP %s: timeout waiting for response to %s", self.name, method)
            return None
        except Exception as e:
            log.error("MCP %s: jsonrpc error: %s", self.name, e)
            return None

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._process.stdin.write(json.dumps(msg) + "\n")
            self._process.stdin.flush()
        except Exception:
            pass

    # ── SSE transport ─────────────────────────────────────────────

    async def _connect_sse(self) -> bool:
        """Connect via HTTP and discover tools."""
        if not self.url:
            log.error("MCP %s: no URL specified for SSE transport", self.name)
            return False

        base = self.url.rstrip("/")
        headers = {**self.headers, "User-Agent": "MimirsWell/1.0"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Initialize
                resp = await client.post(f"{base}/initialize", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "MimirsWell", "version": "1.0"},
                    },
                }, headers=headers)

                if resp.status_code == 200:
                    pass  # OK
                elif resp.status_code == 404:
                    # Some MCP servers use /mcp or /rpc endpoint
                    pass

                # Discover tools
                resp = await client.post(f"{base}/tools/list", json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list",
                    "params": {},
                }, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    if "result" in data:
                        self.tools = data["result"].get("tools", [])
                    elif "tools" in data:
                        self.tools = data["tools"]
                    else:
                        self.tools = []
                else:
                    # Fallback: try simple REST-style tool listing
                    resp2 = await client.get(f"{base}/tools", headers=headers)
                    if resp2.status_code == 200:
                        data = resp2.json()
                        self.tools = data if isinstance(data, list) else data.get("tools", [])
                    else:
                        self.tools = []

        except Exception as e:
            log.error("MCP %s: SSE connect error: %s", self.name, e)
            return False

        self._connected = True
        log.info("MCP %s: connected via SSE to %s, %d tools", self.name, self.url, len(self.tools))
        return True

    async def _call_sse(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via HTTP."""
        base = self.url.rstrip("/")
        headers = {**self.headers, "User-Agent": "MimirsWell/1.0"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{base}/tools/call", json={
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                }, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    if "result" in data:
                        content = data["result"].get("content", [])
                        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                        return {"result": "\n".join(texts) if texts else json.dumps(content)}
                    elif "error" in data:
                        return {"error": data["error"].get("message", str(data["error"]))}
                return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}
        except Exception as e:
            return {"error": f"MCP SSE call failed: {e}"}

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions in a format suitable for display/prompt injection."""
        defs = []
        for t in self.tools:
            defs.append({
                "name": f"mcp_{self.name}_{t.get('name', 'unknown')}",
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {}),
                "server": self.name,
                "original_name": t.get("name", ""),
            })
        return defs


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    @property
    def servers(self) -> dict[str, MCPServer]:
        return dict(self._servers)

    async def load_from_config(self, mcp_config: dict) -> None:
        """Connect to all configured MCP servers."""
        # Disconnect removed servers
        for name in list(self._servers.keys()):
            if name not in mcp_config:
                await self._servers[name].disconnect()
                del self._servers[name]

        # Connect new/updated servers
        for name, cfg in mcp_config.items():
            if not cfg.get("enabled", True):
                if name in self._servers:
                    await self._servers[name].disconnect()
                    del self._servers[name]
                continue
            if name not in self._servers:
                server = MCPServer(name, cfg)
                ok = await server.connect()
                if ok:
                    self._servers[name] = server
                else:
                    log.warning("MCP server '%s' failed to connect", name)

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for server in self._servers.values():
            await server.disconnect()
        self._servers.clear()

    def get_all_tools(self) -> list[dict]:
        """Return all available MCP tools across all connected servers."""
        tools = []
        for server in self._servers.values():
            if server.connected:
                tools.extend(server.get_tool_definitions())
        return tools

    async def call_tool(self, full_tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool by its full name (mcp_serverName_toolName)."""
        # Parse: mcp_{server}_{tool}
        if not full_tool_name.startswith("mcp_"):
            return {"error": f"Not an MCP tool: {full_tool_name}"}

        rest = full_tool_name[4:]  # Remove "mcp_" prefix
        # Find matching server
        for server_name, server in self._servers.items():
            prefix = server_name + "_"
            if rest.startswith(prefix):
                tool_name = rest[len(prefix):]
                if server.connected:
                    return await server.call_tool(tool_name, arguments)
                return {"error": f"MCP server '{server_name}' is not connected"}

        return {"error": f"No MCP server found for tool: {full_tool_name}"}

    def status(self) -> list[dict]:
        """Return status of all configured servers."""
        result = []
        for name, server in self._servers.items():
            result.append({
                "name": name,
                "transport": server.transport,
                "connected": server.connected,
                "tools": len(server.tools),
                "tool_names": [t.get("name", "") for t in server.tools],
            })
        return result
