<!-- 文件作用：记录后端维护命令、模型、请求校验及配置解析的合并迁移和验证结果。
关联关系：对应 manage_db.py、models/chat.py、models/knowledge.py、schemas.py 和 model_config.py。 -->
# Backend consolidation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement in the current checkout.

**Goal:** Reduce scattered backend maintenance and model modules while preserving API behavior, database definitions and protected agent source.

**Architecture:** Combine database scripts in `backend/manage_db.py` with explicit `check`, `init`, `upgrade` subcommands. Group Session/Message in `backend/models/chat.py` and IngestJob/Upload/Knowledge in `backend/models/knowledge.py`; keep `backend.models` exports unchanged. Move schemas to `backend/schemas.py` with unchanged imports. Move pure static model parsing to `agent/model_config.py` without importing runtime or source definitions.

**Tech Stack:** Python, argparse, FastAPI, SQLAlchemy, pytest.

**Spec:** User authorizes further backend consolidation using judgment. Prior constraint: preserve `agent/server.py`.

## Global constraints

- Preserve all existing uncommitted work and protected `agent/server.py` bytes.
- Do not connect to, initialize or upgrade the actual configured database during this reorganization.
- Keep ORM classes, table/column names, constraints, defaults and indexes unchanged.
- Keep authentication, middleware, database connection management and route groups separate.
- Keep initialization explicit and password entry interactive; no command/help/invalid arguments must never initialize anything.
- Update documented database maintenance commands and current imports; retain historical records as historical.
- No commits, branch changes or worktree copies.

## Review focus

- Missing/invalid subcommands and help must exit before settings or database work.
- Password mismatch must stop initialization before settings or writes.
- Check must remain read-only, and upgrade must retain existing rows and support repeated runs.
- Model consolidation must register the same six tables and preserve class bodies.
- Static model parsing must remain independent of runtime and never execute source configuration.

## Task 1: Baseline and failing consumers

- [x] Record source bytes/ASTs and protected source hashes; run current Python baseline.
- [x] Update existing upgrade integration test import to `backend.manage_db` and add CLI dispatch/safety and real temporary-SQLite upgrade tests.
- [x] Confirm tests fail because the new command module is absent before implementing it.

## Task 2: Consolidation

- [x] Combine three maintenance scripts, preserve `initialize(settings, admin_name=None, password=None)` and `upgrade(connection)`, and implement `main(argv=None)` with explicit subcommands.
- [x] Group related model classes without changing class definitions and update package exports.
- [x] Flatten the single-file schema package and relocate static config parsing; update current references.
- [x] Remove superseded implementations and run targeted tests.

## Task 3: Verification and documentation

- [x] Update README/current structure/database instructions, explaining new commands.
- [x] Run full Python and frontend suites; verify no stale imports and protected source/ORM/schema equivalence.
- [x] Obtain independent read-only review, address actionable findings and record results.

## Execution record

- Scope decision: replace the three database script entry points with one documented command rather than retain redundant wrappers. Website startup and HTTP endpoints remain unchanged.
- Scope decision: retain `database.py`, `middleware.py`, `config.py`, API groups and auth/chat services because their responsibilities remain distinct.
- Work in place on the authorized dirty checkout and leave changes uncommitted.
- Baseline: full Python suite → 60 passed, 6 skipped (17.53 seconds).
- Red: new maintenance CLI tests failed to collect because `backend.manage_db` did not exist before consolidation.
- Targeted validation: maintenance command safety, temporary SQLite upgrade, configuration parsing, API and ingestion tests → 32 passed.
- Full regression: `python -m pytest -q --basetemp=backend/data/refactor-verification/backend-final` → 72 passed, 6 skipped (17.41 seconds). Optional PostgreSQL/live-service coverage remains skipped as in the baseline.
- Frontend: all four Node test files → 12 passed.
- CLI help and import smoke checks passed. Importing backend server and schemas does not load `agent.server`.
- Equivalence: all five moved ORM class definitions, original `initialize` and original `upgrade` are AST-identical. Schemas and static model parser are byte-identical moves. Protected `agent/server.py` SHA256 remains `d0709f2243eab97a7dcbc88543073e24fa6f853bfd302631a73be2c407a16025`.
- Cleanup: removed the obsolete schemas package directory after verifying it contained only its generated `__pycache__/__init__.cpython-312.pyc` file.
- No active Python references to removed maintenance/model/config modules remain. Historical plans retain historical paths. `git diff --check` passed with only line-ending normalization notices.

- Independent read-only static review found no actionable issues in command safety, preserved database behavior, metadata/index registration or lazy imports. Its redundant sandboxed smoke execution stalled and was canceled; executable validation is the completed primary regression suite above.
