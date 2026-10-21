"""Hermes-owned model settings, shared by the API and runner processes."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import tomllib
from contextlib import contextmanager
try:
    import fcntl
except ImportError:  # Windows has no fcntl; msvcrt locks a byte range instead.
    fcntl = None
    import msvcrt

ROOT = Path(__file__).resolve().parent


def _lock_file(handle):
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            return
        except OSError:
            time.sleep(0.01)


def _unlock_file(handle):
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


# Claude models Hermes supports. Other models seen at runtime are appended after these.
CLAUDE_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5")
# Reasoning levels the Claude CLI accepts with --effort.
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def claude_label(model_id):
    """'claude-sonnet-5-5' -> 'Claude Sonnet 5.5'."""
    family, *version = model_id.split("-")[1:]
    return f"Claude {family.title()} {'.'.join(version)}"


def canonical(agent):
    return "antigravity" if agent in {"gemini", "agy"} else agent


class ModelRegistry:
    def __init__(self, path=None, codex_path=None):
        self.path = Path(path or os.environ.get("HERMES_AGENT_MODELS", ROOT / "config/agent_models.json"))
        self.codex_path = Path(codex_path or Path.home() / ".codex/config.toml")
        self._cache = None
        self._last_good = []
        self._lock = threading.RLock()

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return {}

    @contextmanager
    def _writing(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.with_suffix(".lock").open("a") as lock:
            _lock_file(lock)
            try:
                yield
            finally:
                _unlock_file(lock)

    @staticmethod
    def _atomic(path, data):
        fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            if hasattr(os, "O_DIRECTORY"):  # Windows cannot fsync a directory
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def configured(self, agent):
        agent = canonical(agent)
        data = self._read(self.path).get(agent, {})
        if agent == "codex" and "default" not in data:
            try:
                cli = tomllib.loads(self.codex_path.read_text())
            except (OSError, ValueError):
                cli = {}
            return {"default": cli.get("model"), "effort": data.get("effort", cli.get("model_reasoning_effort"))}
        return {"default": data.get("default"), "effort": data.get("effort")}

    @staticmethod
    def _agy_models(output):
        grouped = {}
        for line in output.splitlines():
            parts = line.split("\t", 1)
            model = parts[0].strip()
            if not model or model.lower() in {"id", "model", "model id"}:
                continue
            label = parts[1].strip() if len(parts) > 1 else model
            match = re.fullmatch(r"(.*)-(low|medium|high)", model)
            base, effort = match.groups() if match else (model, None)
            if effort:
                label = re.sub(r" \((?:High|Medium|Low)\)$", "", label)
            item = grouped.setdefault(base, {"id": base, "label": label, "efforts": []})
            if effort and effort not in item["efforts"]:
                item["efforts"].append(effort)
        for item in grouped.values():
            item["efforts"].sort(key=["low", "medium", "high"].index)
        return list(grouped.values())

    def models(self, agent):
        agent = canonical(agent)
        examples = self._read(ROOT / "config/agent_models.example.json")
        values = examples.get(agent, {}).get("allowed", [])
        if agent == "claude":
            seen = self._read(self.path.with_name("agent_models.seen.json")).get("claude", [])
            return [{"id": m, "label": claude_label(m), "efforts": list(CLAUDE_EFFORTS)} for m in CLAUDE_MODELS] + [
                {"id": m, "label": m, "efforts": []} for m in seen if m not in CLAUDE_MODELS]
        if agent == "codex":
            # Read on every request: mtime changes (including atomic replacement) cannot go stale.
            path = Path(os.environ.get("HERMES_CODEX_MODELS_CACHE", Path.home() / ".codex/models_cache.json"))
            try:
                entries = json.loads(path.read_text())["models"]
                if not isinstance(entries, list) or any(not isinstance(e, dict) or not isinstance(e.get("slug"), str)
                        or not isinstance(e.get("supported_reasoning_levels", []), list)
                        or any(not isinstance(level, dict) or not isinstance(level.get("effort"), str)
                               for level in e.get("supported_reasoning_levels", [])) for e in entries):
                    raise ValueError("Invalid models cache")
                def descriptor(e):
                    return {"id": e["slug"], "label": e.get("display_name") or e["slug"],
                            "efforts": [level["effort"] for level in e.get("supported_reasoning_levels", [])]}
                models = [descriptor(e) for e in entries if e.get("visibility") == "list"]
            except (OSError, ValueError, KeyError, TypeError):
                entries = []
                models = [{"id": m, "label": m, "efforts": ["low", "medium", "high"]} for m in values]
            try:
                configured = tomllib.loads(self.codex_path.read_text()).get("model")
            except (OSError, ValueError):
                configured = None
            if configured and configured not in [m["id"] for m in models]:
                entry = next((e for e in entries if e["slug"] == configured), None)
                models.append(descriptor(entry) if entry else {"id": configured, "label": configured, "efforts": []})
            return models
        if agent == "antigravity":
            with self._lock:
                now = time.monotonic()
                if self._cache is None or now - self._cache[0] >= self._cache[2]:
                    try:
                        output = subprocess.run(["agy", "models"], capture_output=True, text=True,
                            timeout=20, check=True, stdin=subprocess.DEVNULL).stdout
                        models, ttl = self._agy_models(output), 60
                    except (OSError, subprocess.SubprocessError):
                        models, ttl = [], 10
                    if models:
                        self._last_good = models
                    self._cache = (now, models, ttl)
                return self._cache[1] or self._last_good or self._agy_models("\n".join(values))
        return []

    def allowed(self, agent):
        return [m["id"] for m in self.models(agent)]

    def split_agy_model(self, model, effort=None):
        for item in self.models("antigravity"):
            for level in item["efforts"]:
                if model == item["id"] + "-" + level:
                    return item["id"], level
        match = re.fullmatch(r"(.*)-(low|medium|high)", model or "")
        return match.groups() if match else (model, effort)

    def agy_cli_model(self, model, effort=None):
        base, level = self.split_agy_model(model, effort)
        if base != model:
            return model
        item = next((m for m in self.models("antigravity") if m["id"] == model), None)
        if item and item["efforts"]:
            level = effort or ("medium" if "medium" in item["efforts"] else item["efforts"][0])
            return model + "-" + level
        return model

    def set(self, agent, model, effort):
        agent = canonical(agent)
        if agent == "antigravity":
            model, effort = self.split_agy_model(model, effort)
        item = next((m for m in self.models(agent) if m["id"] == model), None)
        if item is None:
            raise ValueError("Model is not in the agent allowlist")
        if effort is not None and effort not in item["efforts"]:
            raise ValueError("Unsupported reasoning effort for model")
        with self._writing():
            data = self._read(self.path)
            data[agent] = {"default": model, "effort": effort, "allowed": self.allowed(agent)}
            self._atomic(self.path, data)
        return self.configured(agent)

    def resolve(self, agent, options):
        setting = self.configured(agent)
        model = options.get("model") or setting["default"]
        effort = options.get("effort") if "effort" in options else setting["effort"]
        source = "phase" if options.get("model") else "config" if model else "cli-default"
        return {"model": model, "effort": effort, "source": source}

    def record(self, agent, metadata):
        with self._writing():
            path = self.path.with_name(self.path.stem + ".last_used.json")
            data = self._read(path)
            data[canonical(agent)] = {k: metadata.get(k) for k in ("model", "effort", "source")}
            if metadata.get("source") == "reported":
                data[canonical(agent)].update({k: metadata.get(k) for k in
                    ("requestedModel", "requestedEffort", "requestedSource")})
                if canonical(agent) == "claude" and metadata.get("model"):
                    seen_path = self.path.with_name("agent_models.seen.json")
                    seen = self._read(seen_path)
                    seen["claude"] = list(dict.fromkeys([*seen.get("claude", []), metadata["model"]]))
                    self._atomic(seen_path, seen)
            self._atomic(path, data)

    def describe(self, agent):
        last = self._read(self.path.with_name(self.path.stem + ".last_used.json"))
        models = self.models(agent)
        return {"configured": self.configured(agent), "allowed": [m["id"] for m in models],
                "lastUsed": last.get(canonical(agent)), "models": models}


model_registry = ModelRegistry()


def agy_cli_model(model, effort=None):
    return model_registry.agy_cli_model(model, effort)
