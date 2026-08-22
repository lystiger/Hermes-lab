import json
import logging
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

logger = logging.getLogger("hermes.tools")

LYSSTACK_TOOL_REQUEST_START = "--- LYSSTACK TOOL REQUEST ---"
LYSSTACK_TOOL_REQUEST_END = "--- END LYSSTACK TOOL REQUEST ---"


@dataclass
class ToolProfile:
    """Descriptor for a registered tool actor."""
    id: str
    displayName: str
    capabilities: List[str]
    inputSchema: Optional[Dict[str, Any]] = None
    outputSchema: Optional[Dict[str, Any]] = None
    timeoutSeconds: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolProfile":
        return cls(
            id=str(data.get("id", "")).strip(),
            displayName=data.get("displayName") or str(data.get("id", "")).capitalize(),
            capabilities=data.get("capabilities") or [],
            inputSchema=data.get("inputSchema"),
            outputSchema=data.get("outputSchema"),
            timeoutSeconds=int(data.get("timeoutSeconds", 30)),
            metadata=data.get("metadata") or {},
        )


@dataclass
class ToolInvocationRequest:
    """A structured request from an agent to invoke a controlled tool."""
    toolId: str
    args: Dict[str, Any]
    id: Optional[str] = None
    requester: Optional[Dict[str, Any]] = None
    jobId: Optional[str] = None
    threadId: Optional[str] = None
    conversationId: Optional[str] = None
    parentMessageId: Optional[str] = None
    timeoutSeconds: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.id:
            self.id = f"toolreq_{int(time.time() * 1000)}_{id(self) % 10000:04d}"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolInvocationRequest":
        raw_requester = data.get("requester")
        requester_dict = raw_requester if isinstance(raw_requester, dict) else None
        return cls(
            id=data.get("id"),
            toolId=str(data.get("toolId") or data.get("tool_id", "")).strip(),
            args=data.get("args") or {},
            requester=requester_dict,
            jobId=data.get("jobId") or data.get("job_id"),
            threadId=data.get("threadId") or data.get("thread_id"),
            conversationId=data.get("conversationId") or data.get("conversation_id"),
            parentMessageId=data.get("parentMessageId") or data.get("parent_message_id"),
            timeoutSeconds=data.get("timeoutSeconds") or data.get("timeout_seconds"),
            metadata=data.get("metadata"),
        )


@dataclass
class ToolInvocationResult:
    """The structured outcome of a tool execution."""
    requestId: str
    toolId: str
    status: str = "success"  # "success", "failed", "rejected", "timeout"
    output: Optional[Any] = None
    artifactRefs: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolInvocationResult":
        return cls(
            requestId=data.get("requestId") or data.get("request_id", ""),
            toolId=data.get("toolId") or data.get("tool_id", ""),
            status=data.get("status", "success"),
            output=data.get("output"),
            artifactRefs=data.get("artifactRefs") or data.get("artifact_refs"),
            error=data.get("error"),
            metadata=data.get("metadata"),
        )


@dataclass
class ToolPolicy:
    """Configurable tool policy constraints."""
    allow_tools: bool = True
    allowed_tools: Optional[List[str]] = None
    require_actor_capability: bool = True
    read_only_only: bool = True
    max_timeout_seconds: int = 120

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPolicy":
        return cls(
            allow_tools=bool(data.get("allow_tools", data.get("allowTools", True))),
            allowed_tools=data.get("allowed_tools") or data.get("allowedTools"),
            require_actor_capability=bool(data.get("require_actor_capability", True)),
            read_only_only=bool(data.get("read_only_only", True)),
            max_timeout_seconds=int(data.get("max_timeout_seconds", 120)),
        )


class ToolRegistry:
    """
    Central registry for tool actor profiles and safe execution dispatch.
    Hermes is the sole tool execution authority.
    """

    def __init__(self):
        self._tools: Dict[str, ToolProfile] = {}
        self._handlers: Dict[str, Callable[[ToolInvocationRequest, Optional[Path], Optional[Dict[str, Any]]], ToolInvocationResult]] = {}
        self._register_default_tools()

    def register_tool(
        self,
        profile: ToolProfile,
        handler: Callable[[ToolInvocationRequest, Optional[Path], Optional[Dict[str, Any]]], ToolInvocationResult],
    ) -> None:
        self._tools[profile.id] = profile
        self._handlers[profile.id] = handler

    def get_tool(self, tool_id: str) -> Optional[ToolProfile]:
        return self._tools.get(tool_id)

    def list_tools(self) -> List[ToolProfile]:
        return list(self._tools.values())

    def execute(
        self,
        request: ToolInvocationRequest,
        worktree_dir: Optional[Path] = None,
        job_config: Optional[Dict[str, Any]] = None,
        capability_registry: Optional[Any] = None,
        publisher: Any = None,
        job_id: Optional[str] = None,
    ) -> ToolInvocationResult:
        """
        Validates permission, actor capability, and executes tool safely under Hermes control.
        """
        tool_id = request.toolId
        req_id = request.id or "unknown"
        requester_id = ""
        if isinstance(request.requester, dict):
            requester_id = str(request.requester.get("id", "")).strip()
        elif request.requester:
            requester_id = str(request.requester).strip()

        if publisher:
            publisher.publish(
                source_id="hermes_runner",
                source_kind="runtime",
                kind="tool.requested",
                detail=f"Tool execution requested: {tool_id}",
                job_id=job_id or request.jobId,
                metadata={
                    "requestId": req_id,
                    "toolId": tool_id,
                    "requester": request.requester,
                    "args": request.args,
                },
            )

        # 1. Tool existence check
        profile = self._tools.get(tool_id)
        if not profile or tool_id not in self._handlers:
            err = f"Tool '{tool_id}' is not registered."
            logger.warning(err)
            if publisher:
                publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="tool.rejected",
                    detail=err,
                    job_id=job_id or request.jobId,
                    metadata={"requestId": req_id, "toolId": tool_id, "reason": "unregistered_tool"},
                )
            return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)

        # 2. Permission and tool policy checks
        if job_config:
            limits = job_config.get("limits", {}) if isinstance(job_config.get("limits"), dict) else {}
            # 2a. Check if tools are enabled
            allow_tools = limits.get("allow_tools")
            if allow_tools is False:
                err = "Tool execution is disabled by job policy (limits.allow_tools=false)."
                logger.warning(err)
                if publisher:
                    publisher.publish(
                        source_id="hermes_runner",
                        source_kind="runtime",
                        kind="tool.rejected",
                        detail=err,
                        job_id=job_id or request.jobId,
                        metadata={"requestId": req_id, "toolId": tool_id, "reason": "tools_disabled"},
                    )
                return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)

            # 2b. allowed_tools allowlist check
            allowed_tools = limits.get("allowed_tools")
            if allowed_tools is None and "allowed_tools" in job_config:
                allowed_tools = job_config.get("allowed_tools")
            if allowed_tools is not None:
                allowed_set = {t.strip() for t in allowed_tools}
                if tool_id not in allowed_set:
                    err = f"Tool '{tool_id}' is not permitted for this job (allowed: {list(allowed_set)})."
                    logger.warning(err)
                    if publisher:
                        publisher.publish(
                            source_id="hermes_runner",
                            source_kind="runtime",
                            kind="tool.rejected",
                            detail=err,
                            job_id=job_id or request.jobId,
                            metadata={"requestId": req_id, "toolId": tool_id, "reason": "permission_denied"},
                        )
                    return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)

        # 3. Actor capability enforcement
        if requester_id and profile.capabilities:
            cap_reg = capability_registry
            if not cap_reg:
                from capabilities import default_capability_registry
                cap_reg = default_capability_registry

            actor_caps = set(cap_reg.get_actor_capabilities(requester_id))
            has_capability = any(c in actor_caps for c in profile.capabilities)
            if not has_capability:
                err = f"Actor '{requester_id}' lacks required capabilities for tool '{tool_id}' (requires one of {profile.capabilities}, actor has {sorted(list(actor_caps))})."
                logger.warning(err)
                if publisher:
                    publisher.publish(
                        source_id="hermes_runner",
                        source_kind="runtime",
                        kind="tool.rejected",
                        detail=err,
                        job_id=job_id or request.jobId,
                        metadata={
                            "requestId": req_id,
                            "toolId": tool_id,
                            "actorId": requester_id,
                            "reason": "insufficient_actor_capabilities",
                            "toolCapabilities": profile.capabilities,
                            "actorCapabilities": sorted(list(actor_caps)),
                        },
                    )
                return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)

        if publisher:
            publisher.publish(
                source_id="hermes_runner",
                source_kind="runtime",
                kind="tool.started",
                detail=f"Executing tool: {tool_id}",
                job_id=job_id or request.jobId,
                metadata={"requestId": req_id, "toolId": tool_id},
            )

        # 4. Handler execution
        handler = self._handlers[tool_id]
        try:
            result = handler(request, worktree_dir, job_config)
            if result.status == "success":
                if publisher:
                    publisher.publish(
                        source_id="hermes_runner",
                        source_kind="runtime",
                        kind="tool.completed",
                        detail=f"Tool {tool_id} completed successfully.",
                        job_id=job_id or request.jobId,
                        metadata={"requestId": req_id, "toolId": tool_id, "status": result.status},
                    )
            else:
                if publisher:
                    publisher.publish(
                        source_id="hermes_runner",
                        source_kind="runtime",
                        kind="tool.failed",
                        detail=f"Tool {tool_id} failed: {result.error}",
                        job_id=job_id or request.jobId,
                        metadata={"requestId": req_id, "toolId": tool_id, "error": result.error},
                    )
            return result
        except Exception as exc:
            err = f"Unhandled exception executing tool '{tool_id}': {exc}"
            logger.exception(err)
            if publisher:
                publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="tool.failed",
                    detail=err,
                    job_id=job_id or request.jobId,
                    metadata={"requestId": req_id, "toolId": tool_id, "error": str(exc)},
                )
            return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="failed", error=err)

    def _register_default_tools(self) -> None:
        # Tool: tool.git.inspect (Read-only git status, diff, log, show)
        git_profile = ToolProfile(
            id="tool.git.inspect",
            displayName="Git Inspector",
            capabilities=["git.inspect", "repo.read"],
            timeoutSeconds=30,
            metadata={"readOnly": True},
        )
        self.register_tool(git_profile, _handle_git_inspect)

        # Tool: tool.test_runner (Controlled test runner)
        test_profile = ToolProfile(
            id="tool.test_runner",
            displayName="Test Runner",
            capabilities=["testing.unit", "testing.integration"],
            timeoutSeconds=60,
            metadata={"readOnly": True},
        )
        self.register_tool(test_profile, _handle_test_runner)


def _handle_git_inspect(
    request: ToolInvocationRequest,
    worktree_dir: Optional[Path],
    job_config: Optional[Dict[str, Any]] = None,
) -> ToolInvocationResult:
    """Safe read-only git inspection handler."""
    req_id = request.id or "unknown"
    tool_id = "tool.git.inspect"
    args = request.args or {}
    op = str(args.get("operation") or args.get("op", "status")).strip().lower()

    # Strict whitelist of permitted read-only git operations
    ALLOWED_OPERATIONS = {"status", "diff", "log", "show"}
    if op not in ALLOWED_OPERATIONS:
        err = f"Operation '{op}' is not permitted on tool.git.inspect (allowed: {sorted(list(ALLOWED_OPERATIONS))})."
        return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)

    if not worktree_dir or not worktree_dir.exists():
        err = f"Worktree directory '{worktree_dir}' is invalid or does not exist."
        return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="failed", error=err)

    cmd = ["git", op]
    # Handle safe optional arguments
    if op == "diff":
        target = args.get("target") or args.get("path")
        if target and isinstance(target, str):
            if target.startswith("-"):
                err = f"Disallowed flag option '{target}' in diff target."
                return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)
            cmd.append(target)
    elif op == "log":
        limit = args.get("limit") or args.get("max_count", 10)
        try:
            limit_n = min(max(1, int(limit)), 50)
            cmd.extend(["-n", str(limit_n)])
        except Exception:
            cmd.extend(["-n", "10"])
    elif op == "show":
        commit = args.get("commit") or args.get("ref", "HEAD")
        if commit and isinstance(commit, str):
            if commit.startswith("-"):
                err = f"Disallowed flag option '{commit}' in show target."
                return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="rejected", error=err)
            cmd.append(commit)

    timeout = request.timeoutSeconds or 30
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return ToolInvocationResult(
                requestId=req_id,
                toolId=tool_id,
                status="success",
                output={
                    "operation": op,
                    "stdout": proc.stdout[:20000],
                    "returncode": 0,
                },
                metadata={"command": cmd},
            )
        else:
            return ToolInvocationResult(
                requestId=req_id,
                toolId=tool_id,
                status="failed",
                error=proc.stderr or proc.stdout or f"git {op} exited with code {proc.returncode}",
                metadata={"command": cmd, "returncode": proc.returncode},
            )
    except subprocess.TimeoutExpired:
        return ToolInvocationResult(
            requestId=req_id,
            toolId=tool_id,
            status="timeout",
            error=f"git {op} timed out after {timeout} seconds",
        )
    except Exception as exc:
        return ToolInvocationResult(
            requestId=req_id,
            toolId=tool_id,
            status="failed",
            error=str(exc),
        )


def _handle_test_runner(
    request: ToolInvocationRequest,
    worktree_dir: Optional[Path],
    job_config: Optional[Dict[str, Any]] = None,
) -> ToolInvocationResult:
    """Safe configured test runner execution."""
    req_id = request.id or "unknown"
    tool_id = "tool.test_runner"
    args = request.args or {}

    # Extract configured verification command if present in job_config or spec
    verification_cmds = []
    if job_config and "verification" in job_config:
        for v in job_config["verification"]:
            if isinstance(v, dict) and "command" in v:
                verification_cmds.append(v["command"])

    if not verification_cmds:
        # Default verification fallback
        target = args.get("target") or args.get("test_path")
        if target and isinstance(target, str) and not target.startswith("-"):
            cmd = ["pytest", target]
        else:
            cmd = ["pytest", "-q"]
    else:
        cmd = verification_cmds[0]
        if isinstance(cmd, str):
            cmd = cmd.split()

    if not worktree_dir or not worktree_dir.exists():
        err = f"Worktree directory '{worktree_dir}' is invalid or does not exist."
        return ToolInvocationResult(requestId=req_id, toolId=tool_id, status="failed", error=err)

    timeout = request.timeoutSeconds or 60
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ToolInvocationResult(
            requestId=req_id,
            toolId=tool_id,
            status="success" if proc.returncode == 0 else "failed",
            output={
                "stdout": proc.stdout[:20000],
                "stderr": proc.stderr[:5000],
                "returncode": proc.returncode,
            },
            error=proc.stderr if proc.returncode != 0 else None,
            metadata={"command": cmd},
        )
    except subprocess.TimeoutExpired:
        return ToolInvocationResult(
            requestId=req_id,
            toolId=tool_id,
            status="timeout",
            error=f"Test runner timed out after {timeout} seconds",
        )
    except Exception as exc:
        return ToolInvocationResult(
            requestId=req_id,
            toolId=tool_id,
            status="failed",
            error=str(exc),
        )


default_tool_registry = ToolRegistry()
