<!-- 文件作用：记录全项目按功能分组的迁移范围、执行步骤与验证结果。
关联关系：对应 frontend、agent/documents、tests、scripts、requirements 和 docs/verification 的目录整理。 -->
# Project functional layout implementation plan

> **For agentic workers:** Use superpowers:executing-plans in the current checkout.

**Goal:** Group related project files by function, update all active imports/paths/docs, and preserve application behavior and existing data.

**Architecture:** Rename `fronted` to `frontend`; separate document handling from agent query tools in `agent/documents`; move tests to root `tests/{backend,agent,documents,frontend,integration}` with shared fixture/helpers; group operational commands in `scripts`, Python dependencies in `requirements`, and verification reports in `docs/verification`.

**Tech Stack:** Python, FastAPI, Agno, pytest, Node test runner, Markdown/Mermaid.

**Spec:** User authorizes organizing the entire folder according to similar functionality. Preserve original material, runtime data, startup behavior and source intelligent-agent definitions.

## Global constraints

- Preserve all existing uncommitted changes; do not commit, reset or change branches.
- Preserve `agent/server.py` byte for byte, including existing file-header notes; keep its CX/QWJS tool import paths valid.
- Keep `backend/.env`, default upload storage and `ziliao/` original/Markdown locations unchanged.
- Root `启动项目.bat` and website URL/API paths stay unchanged.
- Move source/config/test/document files explicitly; no recursive directory deletion or user data moves.
- Update active import paths, converter subprocess modules, test asset paths, package fixtures, maintenance commands, pip references, comments and README diagrams.
- Keep historical design/plan documents as historical records; current structure documentation is authoritative.

## Review focus

- Frontend static allowlist and browser resource URLs must remain correct after rename.
- `agent.server` must still load lazily; source tools keep their existing module paths.
- Real converter subprocesses and direct CLI calls must work; default Markdown output must remain project-relative.
- pytest must discover all categories and share its temporary client fixture without importing other test modules.
- Dev requirements must include the renamed runtime requirements relative to their new directory.

## Task 1: Baseline, inventory and consumer migration

- [x] Record protected source hashes and original material hashes; run existing Python/Node baseline.
- [x] Prepare exact file mapping, shared fixture/helpers and update test consumers before production module moves.
- [x] Confirm destination imports fail before moved implementation exists.

## Task 2: Functional grouping and path updates

- [x] Move frontend assets, document helper modules, categorized tests, maintenance scripts, requirements and verification docs.
- [x] Add package initializers and shared test support with Chinese role/relation headers.
- [x] Update imports, subprocess module prefix, static paths and converter install guidance.
- [x] Update current docs/README diagrams and file headers; preserve historical plan content.
- [x] Run migrated regression tests and CLI/import checks.

## Task 3: Completion

- [x] Confirm full Python and frontend suites retain coverage; report optional skipped integrations.
- [x] Verify protected source/data hashes, stale references, Markdown links and dependency includes.
- [x] Obtain independent read-only review and address actionable findings.
- [x] Remove obsolete empty/generated-cache-only source directories after checking their exact paths and contents.

## Execution record

- Work in the existing checkout because it contains the authorized current code and uncommitted Chinese file-header notes.
- Avoid unnecessary backend module churn: HTTP APIs, models, configuration and auth/chat services already have coherent responsibilities.
- Keep CX/QWJS tools at their current paths so the protected agent definition needs no compatibility wrappers or edits.
- Baseline full Python regression: 72 passed, 6 skipped (18.13 seconds).
- Red: migrated test consumers failed collection because the destination `scripts` package did not yet exist.
- Migrated discovery: 78 Python tests collected, preserving the baseline coverage count; common client/account helpers were extracted without behavior changes.
- Full migrated regression: `python -m pytest -q --basetemp=backend/data/refactor-verification/layout-migrated` → 72 passed, 6 skipped (20.52 seconds). Optional real database/service integrations remain explicitly skipped as in the baseline.
- Frontend: four categorized Node test files → 14 passed.
- CLI/import checks: `python -m scripts.manage_db --help`, `python -m agent.documents.convert_to_md --help`, backend/runtime imports and converter dependency guidance passed; imports did not load `agent.server`.
- Fixed converter installation guidance to reference the actual root `requirements/runtime.txt`; the previous adjacent-file assumption no longer matches the grouped dependencies.
- Protected source/config/material verification: all 36 files retained identical SHA256 values, including `agent/server.py`, `backend/.env`, original DOCX requirements, and all `ziliao` files present at task start.
- Documentation/dependencies: 15 local Markdown links, 46 concrete README diagram/table paths, code fences and all requirement entries/includes passed validation.
- `compileall` and `git diff --check` passed. Historical plans/specs retain historical paths; current structure and README document the replacements.

- Cleanup: removed the checked empty old frontend directory and the old backend/tests directory after verifying it contained generated bytecode only.
- Independent read-only review found no actionable issues in mapped paths, converter subprocess/default output, pytest shared support, maintenance commands, dependency references or current Markdown links.
