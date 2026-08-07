# Sprint 02 Task Instruction - Antigravity (Scaffold Phase)

## Context
In Sprint 01, we established a FastAPI service in `main.py` with `/health` and `/version` endpoints along with pytest validation in `test_main.py`.

## Objective
Scaffold the Sprint 02 features:
1. Extend `main.py` with a new endpoint `GET /info` returning JSON:
   ```json
   {"app": "Hermes Lab", "status": "running", "environment": "development"}
   ```
2. Extend `main.py` with a new endpoint `GET /metrics` returning JSON:
   ```json
   {"uptime_seconds": 100, "requests_handled": 0}
   ```
3. Add pytest test cases in `test_main.py` testing `GET /info` and `GET /metrics`.
4. Document all changes, verification commands, and pending items in `HANDOFF_AGY.md`.

## Constraints & Rules
- **Do NOT perform git commits, pushes, or branch creation.** Git operations are strictly owned by the controller.
- Keep total changed/created files to a minimum (fewer than 15 files).
- Ensure Python code contains no syntax errors.
- Ensure all tests in `test_main.py` pass cleanly.
