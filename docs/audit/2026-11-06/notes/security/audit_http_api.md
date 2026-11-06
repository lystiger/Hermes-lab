# HTTP API security investigation

Scope: static review of `main.py`, its included routers, goal launcher, startup documentation, and route tests. No live HTTP requests were made; the running service's actual bind address and any external proxy controls were not checked. Likelihood assumes the documented local deployment, not a publicly exposed listener.

## Unauthenticated control and disclosure — likelihood: high; impact: high

`main.py:88-90` constructs the application and includes the orchestrator and design routers without authentication dependencies. The only application HTTP middleware counts requests (`main.py:127-132`); the code explicitly states the API has no authentication (`main.py:93-95`). Reachable callers can read jobs, tasks, runs and events (`main.py:384-392`, `main.py:412-451`, `main.py:468-484`) and launch, cancel, or resume jobs (`main.py:494-506`, `main.py:540-573`, `main.py:578-598`). They can change model settings (`main.py:362-367`), interact with orchestrator conversations (`orchestrator/api.py:20`, `orchestrator/api.py:60-68`), and record a design decision (`design_decision/api.py:37-42`). This permits unauthorized job execution and access to runtime data if an untrusted local process or allowed-origin page can reach the service.

CORS permits the explicit localhost origins on ports 3000, 3001 and 5173 by default, or origins configured by `HERMES_CORS_ORIGINS`, with all methods and headers (`main.py:93-120`). CORS is a browser policy, not authentication or a restriction on non-browser clients. A page served from an allowed origin can read and drive the API, as the code comment notes. The documented command runs `.venv/bin/uvicorn main:app --port 8000` (`README.md:45-51`); the installed Uvicorn `Config` defaults to `127.0.0.1`, so that command defaults to loopback. This is not enforced by the application: an operator can configure another host or expose it through a proxy. Actual deployment binding is unverified.

Smallest guardrail: require a strong per-install secret on all API routes, including internal routes, and retain loopback binding unless an authenticated deployment deliberately changes it. Restrict allowed browser origins to trusted frontends.

## Internal ingress can be forged — likelihood: high; impact: medium to high

The `/internal` prefix is not an access boundary. There is no authentication on these handlers (`main.py:162-163`, `main.py:233-234`, `main.py:260-261`, `main.py:290-291`). A caller can submit arbitrary source, event kind, job ID and metadata (`main.py:139-155`); the event updates agent and job reducers, publishes to the event bus, and may update the execution registry (`main.py:168-215`). Callers can create threads, send actor-attributed messages, and register artifact references (`main.py:226-241`, `main.py:244-277`, `main.py:280-294`). Payload validation constrains some lengths and types; it does not establish sender identity or truth. Forged telemetry can mislead operators and contaminate state; artifact references are registered, with trust assessed separately by the registry (`artifacts/artifact_registry.py:209-214`).

Smallest guardrail: authenticate internal producers with a distinct per-run or service credential and reject unauthenticated ingress. Bind event identity and permitted job IDs to the credential where practical.

## Goal repository path check — likelihood: low for direct traversal; impact: high if bypassed

`HERMES_GOAL_REPOS_ROOT` defaults to `~/Projects` (`main.py:537`). The route resolves both root and absolute or root-relative `targetRepo`, then requires the resolved repository's immediate parent to equal the resolved root and requires an existing `.git` entry (`main.py:549-553`). Thus ordinary `..` traversal, sibling-prefix tricks, nested repositories, and symlinks resolving outside the root fail the parent check at validation time. Absolute paths directly under the configured root are accepted. The check requires only that `.git` exists; it does not establish that it is a valid Git repository or that a `.git` file or symlink points inside the root. The existing test checks an absolute repository outside the root is rejected (`tests/test_goal_route.py:77-83`); it does not demonstrate symlink, traversal, or race cases.

The validated resolved path is passed to `launch_goal_background` (`main.py:555-558`), then `launch_goal` resolves it again (`jobs/job_launcher.py:575`, `jobs/job_launcher.py:660-665`). The launcher does not independently enforce the HTTP root, and other direct launcher callers are outside this route's boundary. Since validation and later use are separate, a local actor able to replace path components may race the check; no race was tested. The path check confines the selected path at validation time, not the contents or Git metadata it may reference.

Smallest guardrail: add route tests for traversal, symlinks, nested paths and absolute paths. If the projects root is writable by untrusted users, revalidate immediately before use and protect root entries against replacement; enforce the same policy at the launcher boundary if direct callers must obey it.

## Check result

The required pytest command completed with 921 passed, 110 failed, 27 errors, 8 skipped, and 79 subtests passed. To obey the workspace rule forbidding Git, `PATH` supplied a stub that rejects Git invocations; tests that require Git therefore fail or error, and this run is not a valid clean-suite result. No live request was made to localhost:8000.
