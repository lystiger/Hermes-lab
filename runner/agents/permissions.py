import json
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def scoped_antigravity_permissions(wt_dir, canonical_repo, settings_path=None):
    """Install narrowly scoped Antigravity permissions and restore them exactly."""
    settings_path = Path(
        settings_path
        or Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    )
    original_content = None
    existed = settings_path.exists()

    if existed:
        # Never mutate settings unless an exact restoration snapshot was captured.
        original_content = settings_path.read_text(encoding="utf-8")

    try:
        try:
            settings = json.loads(original_content) if original_content else {}
        except (TypeError, json.JSONDecodeError):
            settings = {}

        if not isinstance(settings.get("permissions"), dict):
            settings["permissions"] = {"allow": [], "deny": []}
        permissions = settings["permissions"]
        if not isinstance(permissions.get("allow"), list):
            permissions["allow"] = []
        if not isinstance(permissions.get("deny"), list):
            permissions["deny"] = []
        if not isinstance(settings.get("trustedWorkspaces"), list):
            settings["trustedWorkspaces"] = []

        wt_path = str(wt_dir.resolve())
        repo_path = str(canonical_repo.resolve())
        worktree_git = str((wt_dir / ".git").resolve())
        canonical_git = str((canonical_repo / ".git").resolve())

        if wt_path not in settings["trustedWorkspaces"]:
            settings["trustedWorkspaces"].append(wt_path)

        allow_rules = [
            f"read_file({wt_path})",
            f"read_file({wt_path}/**)",
            f"write_file({wt_path})",
            f"write_file({wt_path}/**)",
            f"read_file({repo_path}/.git)",
            f"read_file({repo_path}/.git/**)",
            "command(pwd)",
            "command(ls -la)",
            "command(pwd && ls -la)",
            "command(python3 -m pytest -q)",
        ]
        deny_rules = [
            f"write_file({worktree_git})",
            f"write_file({worktree_git}/**)",
            f"write_file({canonical_git})",
            f"write_file({canonical_git}/**)",
        ]
        for rule in allow_rules:
            if rule not in permissions["allow"]:
                permissions["allow"].append(rule)
        for rule in deny_rules:
            if rule not in permissions["deny"]:
                permissions["deny"].append(rule)

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        yield
    finally:
        if existed:
            settings_path.write_text(original_content, encoding="utf-8")
        elif not existed and settings_path.exists():
            settings_path.unlink()
