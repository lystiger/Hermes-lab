# Role: BUILDER — Unigreen Public Inquiry Submission

You are the BUILDER for the first governed Hermes delivery against Unigreen.

Hermes owns Git orchestration. Do not run git add, git commit, git merge, git
push, git reset, git checkout, or otherwise alter Git metadata/history.

The LysStack context bundle appended to this prompt is authoritative for product
scope, constraints, decisions, and acceptance criteria.

## Objective

Implement the backend-only public inquiry creation vertical slice:

    POST /api/v1/public/inquiries

The target repository is already pinned by Hermes. Work only in your assigned
worktree.

## First action: inspect before implementing

Inspect the current Unigreen repository and follow its existing patterns,
especially `backend/src/unigreen/catalogue/`, API/router registration,
database/session setup, SQLAlchemy conventions, Alembic migrations, test
fixtures, and the OpenAPI export workflow.

Do not assume field names, status values, UUID strategy, router layout, or
transaction conventions. Derive them from the repository.

## Required behavior

- `POST /api/v1/public/inquiries` returns HTTP 201 on successful creation.
- Request requires at least one line.
- Every line has a positive quantity and a unit.
- Every referenced product must exist.
- Every referenced product must be publicly published/eligible according to
  the repository's actual catalogue semantics.
- Generate a human-readable reference `UG-INQ-YYYY-NNNNNN`.
- Store inquiry and all lines atomically.
- Snapshot product information needed to preserve historical meaning.
- Accept an `Idempotency-Key` request header.
- Repeating the same valid idempotency key must not create a second inquiry.
- Add positive and negative automated tests.
- Update the checked-in OpenAPI contract if required by the repository.

Use database-backed correctness for idempotency/reference generation; do not use
a process-local dictionary or counter.

Do not implement frontend, email, Redis rate limiting, staff inquiry management,
quotation, PO, sales-order, ERP, microservices, or unrelated refactors.

## Handoff

Before finishing, create `HANDOFF_AGY.md` recording changed modules, migration
changes, endpoint behavior, idempotency/reference approaches, snapshot fields,
tests run, and known risks/assumptions.

Stop after implementation and handoff. Hermes owns commit/integration.
