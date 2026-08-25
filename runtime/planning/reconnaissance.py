import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from runtime.limits import RuntimeLimits

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't",
    "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some",
    "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then",
    "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's",
    "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "please", "add", "implement", "create", "make", "build", "write"
}

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", ".idea", ".vscode",
    ".tox", ".nox", "site-packages", ".eggs"
}


@dataclass
class EvidenceFile:
    """A discrete piece of repository evidence found during reconnaissance."""
    path: str
    reason: str
    excerpt: str
    confidence: float = 1.0
    exists: bool = True
    line_count: int = 0
    symbols: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceFile":
        return cls(
            path=str(data.get("path", "")),
            reason=str(data.get("reason", "")),
            excerpt=str(data.get("excerpt", "")),
            confidence=float(data.get("confidence", 1.0)),
            exists=bool(data.get("exists", True)),
            line_count=int(data.get("line_count", 0)),
            symbols=list(data.get("symbols") or []),
        )


@dataclass
class RepositoryEvidence:
    """Structured repository reconnaissance gathered prior to goal planning."""
    summary: str
    files: List[EvidenceFile] = field(default_factory=list)
    symbols_or_modules: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    contracts: List[str] = field(default_factory=list)
    architecture_clues: List[str] = field(default_factory=list)
    uncertainty: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "files": [f.to_dict() for f in self.files],
            "symbols_or_modules": self.symbols_or_modules,
            "tests": self.tests,
            "contracts": self.contracts,
            "architecture_clues": self.architecture_clues,
            "uncertainty": self.uncertainty,
            "languages": self.languages,
            "frameworks": self.frameworks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepositoryEvidence":
        files_data = data.get("files") or []
        files = [EvidenceFile.from_dict(f) if isinstance(f, dict) else f for f in files_data]
        return cls(
            summary=str(data.get("summary", "")),
            files=files,
            symbols_or_modules=list(data.get("symbols_or_modules") or []),
            tests=list(data.get("tests") or []),
            contracts=list(data.get("contracts") or []),
            architecture_clues=list(data.get("architecture_clues") or []),
            uncertainty=list(data.get("uncertainty") or []),
            languages=list(data.get("languages") or []),
            frameworks=list(data.get("frameworks") or []),
        )

    def render_for_prompt(self, max_bytes: int = 40000) -> str:
        """Renders evidence into a concise markdown section for the planner prompt."""
        sections = []
        sections.append("### Repository Architecture Summary")
        sections.append(self.summary or "Standard repository structure.")

        if self.languages or self.frameworks:
            lang_str = ", ".join(self.languages) if self.languages else "Unspecified"
            fw_str = ", ".join(self.frameworks) if self.frameworks else "None detected"
            sections.append(f"- **Languages**: {lang_str}\n- **Frameworks**: {fw_str}")

        if self.architecture_clues:
            sections.append("### Architecture Clues")
            for clue in self.architecture_clues:
                sections.append(f"- {clue}")

        if self.tests:
            sections.append("### Test Suite & Test Locations")
            for t in self.tests[:10]:
                sections.append(f"- {t}")

        if self.contracts:
            sections.append("### Existing Contracts & Schemas")
            for c in self.contracts[:10]:
                sections.append(f"- {c}")

        if self.files:
            sections.append("### Relevant Files & Excerpts")
            current_bytes = sum(len(s) for s in sections)
            for f in self.files:
                file_sec = f"#### File: `{f.path}` ({f.reason})\n```\n{f.excerpt.strip()}\n```"
                if current_bytes + len(file_sec) > max_bytes:
                    sections.append("*(Additional file excerpts omitted for brevity)*")
                    break
                sections.append(file_sec)
                current_bytes += len(file_sec)

        if self.uncertainty:
            sections.append("### Identified Uncertainties & Gaps")
            for u in self.uncertainty:
                sections.append(f"- [UNCERTAINTY] {u}")

        return "\n\n".join(sections)


class RepositoryReconnaissance:
    """
    Deterministic, bounded repository evidence collector.
    Performs goal-directed static reconnaissance over target codebase before planning.
    """

    @classmethod
    def extract_goal_keywords(cls, goal: str, constraints: Optional[List[str]] = None) -> Set[str]:
        """Extracts significant search keywords from goal and constraints."""
        text = goal
        if constraints:
            text += " " + " ".join(constraints)

        tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
        keywords = {t for t in tokens if len(t) > 2 and t not in STOPWORDS}
        return keywords

    @classmethod
    def collect(
        cls,
        repo_dir: Path,
        goal: str,
        constraints: Optional[List[str]] = None,
        limits: Optional[RuntimeLimits] = None,
    ) -> RepositoryEvidence:
        """
        Scans repo_dir, scores relevance against goal keywords, and gathers bounded evidence.
        """
        limits = limits or RuntimeLimits()
        max_files = limits.max_evidence_files
        max_bytes = limits.max_evidence_bytes
        repo_dir = Path(repo_dir).resolve()

        if not repo_dir.exists() or not repo_dir.is_dir():
            return RepositoryEvidence(
                summary="Target repository directory does not exist or is empty.",
                uncertainty=["Repository path does not exist on disk."],
            )

        keywords = cls.extract_goal_keywords(goal, constraints)
        scanned_files = []

        # 1. Walk directory tree (respecting IGNORED_DIRS)
        for root, dirs, filenames in os.walk(repo_dir):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.endswith(".egg-info")]

            rel_root = Path(root).relative_to(repo_dir)
            for fname in filenames:
                if fname.startswith(".") or fname.endswith((".pyc", ".pyo", ".pyd", ".so", ".dll")):
                    continue
                full_path = Path(root) / fname
                rel_path = (rel_root / fname).as_posix()
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                scanned_files.append((full_path, rel_path))

        if not scanned_files:
            return RepositoryEvidence(
                summary="Repository is currently empty (greenfield project).",
                uncertainty=["No existing files found in repository."],
            )

        # 2. Analyze global architecture, languages, frameworks
        languages: Set[str] = set()
        frameworks: Set[str] = set()
        tests_found: List[str] = []
        contracts_found: List[str] = []
        architecture_clues: List[str] = []
        uncertainties: List[str] = []

        for full_path, rel_path in scanned_files:
            suffix = full_path.suffix.lower()
            if suffix == ".py":
                languages.add("python")
            elif suffix in (".ts", ".tsx"):
                languages.add("typescript")
            elif suffix in (".js", ".jsx"):
                languages.add("javascript")
            elif suffix == ".go":
                languages.add("go")
            elif suffix == ".rs":
                languages.add("rust")
            elif suffix == ".sql":
                languages.add("sql")

            if "test" in rel_path.lower() or fname_is_test(rel_path):
                tests_found.append(rel_path)

        # 3. Score and rank files against goal keywords
        scored_files = []
        for full_path, rel_path in scanned_files:
            score = 0
            reasons = []
            rel_lower = rel_path.lower()

            # Path matches keywords
            matched_kws = [kw for kw in keywords if kw in rel_lower]
            if matched_kws:
                score += len(matched_kws) * 4
                reasons.append(f"path matches keywords: {', '.join(matched_kws)}")

            # Core architecture paths
            if any(p in rel_lower for p in ("api", "route", "model", "schema", "service", "controller", "app")):
                score += 3
                reasons.append("core module convention")
            if "test" in rel_lower:
                score += 2
                reasons.append("test location")

            # Try inspecting content for keyword matches and frameworks
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                line_count = len(lines)

                content_lower = content.lower()
                content_matches = [kw for kw in keywords if kw in content_lower]
                if content_matches:
                    score += min(len(content_matches) * 2, 6)
                    reasons.append(f"content matches: {', '.join(content_matches)}")

                # Detect frameworks from content
                if "fastapi" in content_lower:
                    frameworks.add("FastAPI")
                if "pydantic" in content_lower or "basemodel" in content_lower:
                    frameworks.add("Pydantic")
                if "sqlalchemy" in content_lower:
                    frameworks.add("SQLAlchemy")
                if "pytest" in content_lower:
                    frameworks.add("Pytest")
                if "alembic" in content_lower:
                    frameworks.add("Alembic")
                if "react" in content_lower:
                    frameworks.add("React")

                # Extract contracts / symbols
                symbols = []
                for line in lines:
                    line_s = line.strip()
                    if line_s.startswith("class ") or line_s.startswith("def ") or line_s.startswith("async def "):
                        sym = line_s.split(":")[0].strip()
                        symbols.append(sym)
                        if "model" in sym.lower() or "schema" in sym.lower() or "basemodel" in sym.lower():
                            contracts_found.append(f"{rel_path}: {sym}")

                scored_files.append((score, full_path, rel_path, reasons, content, line_count, symbols))
            except Exception:
                continue

        # Sort files by relevance score descending
        scored_files.sort(key=lambda x: x[0], reverse=True)

        # 4. Select bounded evidence files
        evidence_files: List[EvidenceFile] = []
        collected_symbols: List[str] = []
        total_excerpt_bytes = 0

        for score, full_path, rel_path, reasons, content, line_count, symbols in scored_files:
            if len(evidence_files) >= max_files:
                break

            # Build bounded excerpt (max 1500 chars per file)
            excerpt = content[:1500]
            if len(content) > 1500:
                excerpt += f"\n... (truncated from {line_count} lines)"

            if total_excerpt_bytes + len(excerpt) > max_bytes and evidence_files:
                break

            total_excerpt_bytes += len(excerpt)
            collected_symbols.extend([f"{rel_path}:{s}" for s in symbols[:5]])

            reason_str = "; ".join(reasons) if reasons else "repository component"
            confidence = min(1.0, max(0.5, score / 10.0)) if score > 0 else 0.5
            evidence_files.append(
                EvidenceFile(
                    path=rel_path,
                    reason=reason_str,
                    excerpt=excerpt,
                    confidence=confidence,
                    exists=True,
                    line_count=line_count,
                    symbols=symbols[:10],
                )
            )

        # 5. Detect architecture clues & uncertainties
        if "FastAPI" in frameworks:
            architecture_clues.append("Uses FastAPI REST framework with route decorators.")
        if "Pydantic" in frameworks:
            architecture_clues.append("Uses Pydantic BaseModel for request/response validation schemas.")
        if "Pytest" in frameworks or tests_found:
            architecture_clues.append(f"Testing convention: pytest with {len(tests_found)} existing test file(s).")
        else:
            uncertainties.append("No existing test framework or test files detected in repository.")

        # Check for keywords with 0 matches in existing files
        for kw in keywords:
            if not any(kw in f.path.lower() or kw in f.excerpt.lower() for f in evidence_files):
                uncertainties.append(f"No existing domain component found for concept '{kw}'; will require new component implementation.")

        # Summary
        summary = (
            f"Repository contains {len(scanned_files)} files across {', '.join(languages) or 'unknown languages'}. "
            f"Found {len(tests_found)} test file(s) and {len(evidence_files)} goal-relevant evidence file(s)."
        )

        return RepositoryEvidence(
            summary=summary,
            files=evidence_files,
            symbols_or_modules=collected_symbols[:20],
            tests=tests_found[:15],
            contracts=contracts_found[:15],
            architecture_clues=architecture_clues,
            uncertainty=uncertainties[:10],
            languages=sorted(list(languages)),
            frameworks=sorted(list(frameworks)),
        )


def fname_is_test(path_str: str) -> bool:
    name = Path(path_str).name.lower()
    return name.startswith("test_") or name.endswith("_test.py") or name.endswith(".test.ts") or name.endswith(".test.js")
