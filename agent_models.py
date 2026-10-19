"""Hermes-owned model settings, shared by the API and runner processes."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import tomllib
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent


def canonical(agent):
    return "antigravity" if agent in {"gemini", "agy"} else agent


class ModelRegistry:
    def __init__(self, path=None, codex_path=None):
        self.path = Path(path or os.environ.get("HERMES_AGENT_MODELS", ROOT / "config/agent_models.json"))
        self.codex_path = Path(codex_path or Path.home() / ".codex/config.toml")
        self._cache = None
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
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

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

    def allowed(self, agent):
        agent = canonical(agent)
        examples = self._read(ROOT / "config/agent_models.example.json")
        if agent == "claude":
            return ["sonnet", "opus", "haiku"]
        values = self._read(self.path).get(agent, {}).get("allowed", examples.get(agent, {}).get("allowed", []))
        if agent == "codex":
            try:
                model = tomllib.loads(self.codex_path.read_text()).get("model")
            except (OSError, ValueError):
                model = None
            return list(dict.fromkeys([*values, *([model] if model else [])]))
        if agent == "antigravity":
            with self._lock:
                if self._cache is None or time.monotonic() - self._cache[0] >= 60:
                    try:
                        output = subprocess.run(["agy", "models"], capture_output=True, text=True, timeout=5, check=True).stdout
                        models = [line.split("\t", 1)[0].strip() for line in output.splitlines() if line.strip()]
                        models = [m for m in models if m.lower() not in {"id", "model", "model id"}]
                    except (OSError, subprocess.SubprocessError):
                        models = []
                    self._cache = (time.monotonic(), models)
                return list(dict.fromkeys(self._cache[1] or values))
        return values

    def set(self, agent, model, effort):
        agent = canonical(agent)
        if model not in self.allowed(agent):
            raise ValueError("Model is not in the agent allowlist")
        efforts = {"codex": {None, "minimal", "low", "medium", "high", "xhigh"},
                   "antigravity": {None, "low", "medium", "high"}, "claude": {None}}
        if effort not in efforts.get(agent, {None}):
            raise ValueError("Unsupported reasoning effort for agent")
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
            self._atomic(path, data)

    def describe(self, agent):
        last = self._read(self.path.with_name(self.path.stem + ".last_used.json"))
        return {"configured": self.configured(agent), "allowed": self.allowed(agent),
                "lastUsed": last.get(canonical(agent))}


model_registry = ModelRegistry()
