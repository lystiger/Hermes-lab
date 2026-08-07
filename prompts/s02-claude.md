# Sprint 02 Task Instruction - Claude (Review & Extend Phase)

## Context
Antigravity has completed the initial Sprint 02 scaffold (`GET /info` and `GET /metrics` in `main.py`, along with tests in `test_main.py`).

## Objective
Review and extend the Sprint 02 implementation:
1. Inspect `main.py`, `test_main.py`, and `HANDOFF_AGY.md`.
2. Enhance `GET /metrics` to accept an optional query parameter `format` (e.g., `format=json` or `format=prometheus`), returning formatted output.
3. Enhance `test_main.py` with comprehensive unit tests for `GET /metrics?format=json` and invalid parameter handling.
4. Document review findings, enhancements, and verification instructions in `HANDOFF_CLAUDE.md`.

## Constraints & Rules
- **Do NOT perform git commits, pushes, or branch creation.** Git operations are strictly owned by the controller.
- Do NOT modify or remove existing tests for `/health`, `/version`, or `/info`.
- Ensure Python code contains no syntax errors.
- Keep total changed/created files to a minimum (fewer than 15 files).
