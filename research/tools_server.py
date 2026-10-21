"""The RESEARCHER role's tools, served over MCP (stdio).

Four tools: watch_releases (dependencies and fixed sources, budgeted), research_save (sourced findings
into LysStack/research), source_check (is a quote on its page), and nothing else. Network access is
limited to the hosts in research.watch and config/research_hosts.json.
"""

import argparse
import json
import sys
from pathlib import Path

from research.records import RecordError, save_research
from research.verify import verify_quote
from research.watch import DEFAULT_BUDGET, ResearchError, run

PROTOCOL_VERSION = "2024-11-05"
TOOL_NAMES = ("watch_releases", "research_save", "source_check")

TOOLS = [
    {
        "name": "watch_releases",
        "description": "Check the repo's dependencies against their latest releases, and the fixed release sources "
                       "against their last snapshot. Read-only; budgeted. Returns dated findings.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "research_save",
        "description": "Save sourced findings to LysStack/research/<topic>.md. Each finding needs a claim, an https "
                       "source link and the retrieval date. Never overwrites.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "lowercase letters, digits and hyphens"},
                "findings": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"claim": {"type": "string"}, "source_url": {"type": "string"},
                                   "retrieved": {"type": "string"}, "quote": {"type": "string"},
                                   "licence": {"type": "string"}},
                    "required": ["claim", "source_url", "retrieved"]}},
            },
            "required": ["topic", "findings"],
            "additionalProperties": False,
        },
    },
    {
        "name": "source_check",
        "description": "Check that a quote appears on its source page. VERIFIED, NOT_FOUND or UNPROVEN. "
                       "Only allowlisted hosts are read.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["url", "quote"],
            "additionalProperties": False,
        },
    },
]


class ResearchTools:
    def __init__(self, root, requirements, sources, state, budget=DEFAULT_BUDGET):
        self.root = Path(root)
        self.requirements = Path(requirements)
        self.sources = Path(sources)
        self.state = Path(state)
        self.budget = budget

    def watch_releases(self):
        try:
            return run(self.requirements, self.sources, self.state, budget_limit=self.budget)
        except (ResearchError, OSError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    def research_save(self, topic, findings):
        try:
            path = save_research(topic, findings, self.root)
        except RecordError as exc:
            raise ToolError(str(exc)) from exc
        return {"saved": str(path.relative_to(self.root))}

    def source_check(self, url, quote):
        return verify_quote(url, quote)


class ToolError(Exception):
    """A tool call cannot be served. Reported to the model as an error result."""


def _text(value, is_error=False):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle(message, tools):
    if "id" not in message:
        return None
    request_id = message["id"]
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "research", "version": "0.1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        name, args = params.get("name"), params.get("arguments") or {}
        try:
            if name == "watch_releases":
                result = _text(tools.watch_releases())
            elif name == "research_save":
                result = _text(tools.research_save(args.get("topic", ""), args.get("findings", [])))
            elif name == "source_check":
                result = _text(tools.source_check(args.get("url", ""), args.get("quote", "")))
            else:
                result = _text(f"unknown tool: {name}", is_error=True)
        except ToolError as exc:
            result = _text(str(exc), is_error=True)
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(tools, stdin=sys.stdin, stdout=sys.stdout):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message, tools)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research tools for the RESEARCHER role (MCP over stdio)")
    parser.add_argument("--root", required=True, type=Path, help="LysStack repository")
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    args = parser.parse_args(argv)
    serve(ResearchTools(args.root, args.requirements, args.sources, args.state, args.budget))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
