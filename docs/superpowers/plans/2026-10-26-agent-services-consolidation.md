# Agent services consolidation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan in the current session.

**Goal:** Consolidate AI execution and document processing under `agent/` without changing `agent/server.py` or existing application behavior.

**Architecture:** Combine `backend/agent_adapter.py` and `backend/services/agent.py` in `agent/runtime.py`. Move embedding to `agent/embedding.py` and document utilities to `agent/tools/{attachments,chunker,converter}.py`. Keep authentication, session authorization, generation locking and SSE formatting in `backend/services/`.

**Tech Stack:** Python, FastAPI, Agno, SQLAlchemy, pytest, Node test runner.

**Spec:** User-approved scope in the conversation: organize the previously recommended modules while preserving `agent/server.py`.

## Global constraints

- Preserve the starting bytes of `agent/server.py`, including its pre-existing uncommitted changes.
- Preserve existing behavior, function signatures, request isolation and authenticated tool scope.
- Keep fixed 500-character attachment chunking separate from structural Markdown chunking.
- Preserve subprocess timeout/cancellation cleanup and embedding batching/retry/validation.
- Work from the current uncommitted application state; do not commit unrelated changes or alter database data.
- Remove superseded implementations after updating all current consumers; historical design documents may retain historical paths.

## Review focus

- Imports must not eagerly import `agent.server` or start its AgentOS.
- Test monkeypatches must target the actual runtime module after consolidation.
- Source teams and members must remain independently copied per request.
- Converter subprocess module names must continue to resolve from the project root.
- Both attachment uploads and background ingestion must use the moved helpers without changing processing behavior.

## Task 1: Verify baseline and prepare consumer tests

- [x] Run the existing Python suite and record its baseline.
- [x] Record hashes of protected files and source modules before moving them.
- [x] Update existing behavioral tests to import `agent.runtime`, `agent.embedding` and the new document helper paths.
- [x] Run those tests before moving implementation; confirm missing destination modules cause failure.

## Task 2: Consolidate implementations and consumers

- [x] Combine adapter functions and `stream_answer(history, question, settings)` in `agent/runtime.py`, keeping `create_agent` lazy with respect to `agent.server`.
- [x] Move `embed(texts, settings)`, vector validation and exceptions to `agent/embedding.py` without changing their bodies.
- [x] Move the three document helper modules to `agent/tools/` without changing behavior.
- [x] Update imports in `backend/server.py`, upload/ingest APIs, `agent/dr.py` and the CX knowledge tool.
- [x] Remove the old five service modules and adapter; keep `auth.py`, `chat.py`, and the service package initializer.
- [x] Run the migrated behavioral tests.

## Task 3: Documentation and completion verification

- [x] Update README and current structure/verification documentation to the new paths; document remaining backend dependencies.
- [x] Run the complete Python suite and all four frontend Node test files.
- [x] Check for stale imports, inspect changes, and verify protected hashes and unchanged moved implementations.
- [x] Record results here and report skipped integration coverage explicitly.

## Execution record

- Ruling: Execute in the existing checkout because the requested baseline includes uncommitted deletions and new attachment processing code; no commits, branch changes or worktree copies are needed for this scoped reorganization.
- Ruling: Use existing behavioral tests with updated imports rather than adding tests that merely duplicate the directory mapping.
- Baseline: `python -m pytest backend/tests -q --basetemp=backend/data/refactor-verification/baseline-unsandboxed` → 60 passed, 6 skipped. Windows sandbox runs encountered temp-directory errors and stalled asynchronous execution; verification therefore used the approved unsandboxed test runner.
- Red: Updated consumer tests failed to collect because `agent.runtime` did not exist yet; implementations were moved only after confirming this missing-module failure.
- Targeted migration validation: 27 passed, including request isolation, actual Agno HTTP transport with a controlled upstream, chat routing, embedding retries, document conversion and attachment uploads.
- Final Python suite: `python -m pytest -q --basetemp=backend/data/refactor-verification/final` → 60 passed, 6 skipped in 17.49 seconds. Optional PostgreSQL and live-service integration coverage remained skipped, matching the baseline.
- Frontend suite: `node --test backend/tests/test_sse.cjs backend/tests/test_chat_ui.cjs backend/tests/test_ingest_ui.cjs backend/tests/test_markdown_ui.cjs` → 12 passed.
- Import check: importing `agent.runtime` and `backend.server` does not load `agent.server`. No Python imports reference removed modules.
- SHA256 verification: `agent/server.py`, backend auth/chat, and all four moved helper files match their starting bytes. Protected `agent/server.py`: `d0709f2243eab97a7dcbc88543073e24fa6f853bfd302631a73be2c407a16025`.
- `git diff --check` passed; Git emitted only existing line-ending normalization notices.

- Independent read-only review: no actionable issues; adapter functions were AST-identical to their originals, module imports and subprocess paths remained valid, and the protected source hash matched.
