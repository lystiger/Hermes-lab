"""Where agents and verification run inside a target repository.

A sprint may target a subfolder of a repository (`target_subdir`, for example `console`).
Git work still happens at the repository root; only the agent and verification
working directories move into the subfolder.
"""
from pathlib import Path, PurePosixPath
from typing import Optional


def normalize_target_subdir(value: Optional[str]) -> str:
    """Returns a contained relative POSIX path, or "" for the repository root."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text == ".":
        return ""
    if "\\" in text:
        raise ValueError(f"target_subdir must use '/' separators: {value!r}")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"target_subdir must be a relative path inside the repository: {value!r}")
    parts = [part for part in path.parts if part not in (".", "")]
    return "/".join(parts)


def subdir_path(root: Path, target_subdir: str) -> Path:
    """The directory inside a checkout where agents and verification run."""
    return root / target_subdir if target_subdir else root
