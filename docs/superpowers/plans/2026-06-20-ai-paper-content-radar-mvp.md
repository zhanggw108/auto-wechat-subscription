# AI Paper Content Radar MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first MVP that ingests AI paper/news signals, scores 5-10 topics, generates one reviewable WeChat draft package, and exposes a React cockpit for radar, topic pool, and article workshop.

**Architecture:** Use a Python FastAPI backend with a deterministic local pipeline and JSON/file storage so the workflow runs without external API keys. Use a Vite React frontend that reads the API and presents the three MVP pages described in `ARCHITECTURE.md`.

**Tech Stack:** FastAPI, Pydantic, pytest, httpx, Vite, React, TypeScript, Vitest, CSS custom properties with OKLCH tokens.

---

## File Structure

- `apps/api/ai_radar/models.py`: Pydantic domain models and enums.
- `apps/api/ai_radar/sample_data.py`: seed signals used when external sources are unavailable.
- `apps/api/ai_radar/storage.py`: JSON database and draft package file writer.
- `apps/api/ai_radar/pipeline.py`: normalize, score, select, evidence, article, review, and package generation.
- `apps/api/ai_radar/api.py`: FastAPI routes matching the MVP API in the architecture document.
- `apps/api/tests/`: API and pipeline tests.
- `apps/web/src/`: React cockpit, API client, utility formatting, and CSS.
- `storage/`: generated JSON database and draft packages.

## Tasks

### Task 1: Backend behavior tests

**Files:**
- Create: `apps/api/tests/test_pipeline.py`
- Create: `apps/api/tests/test_api.py`
- Create: `apps/api/pytest.ini`

- [ ] Write tests that require the pipeline to generate 5-10 topics, one selected long-paper draft, sources, checklist, evidence JSON, and HTML.
- [ ] Write API tests for `/health`, `/api/radar/today`, `/api/topics`, `/api/drafts`, topic selection/rejection, rerun stages, and mark-published.
- [ ] Run `python3 -m pytest apps/api/tests -q` and confirm the tests fail because implementation modules are absent.

### Task 2: Backend implementation

**Files:**
- Create: `apps/api/requirements.txt`
- Create: `apps/api/ai_radar/__init__.py`
- Create: `apps/api/ai_radar/models.py`
- Create: `apps/api/ai_radar/sample_data.py`
- Create: `apps/api/ai_radar/storage.py`
- Create: `apps/api/ai_radar/pipeline.py`
- Create: `apps/api/ai_radar/api.py`

- [ ] Implement deterministic sample ingestion, scoring, topic selection, evidence-first draft generation, Markdown/HTML/sources/checklist/evidence package output, and image prompt placeholders.
- [ ] Implement FastAPI routes from the MVP subset in `ARCHITECTURE.md`.
- [ ] Run `python3 -m pytest apps/api/tests -q` and confirm backend tests pass.

### Task 3: Frontend behavior and implementation

**Files:**
- Create: `package.json`
- Create: `apps/web/package.json`
- Create: `apps/web/index.html`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/api.ts`
- Create: `apps/web/src/App.test.tsx`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/styles.css`

- [ ] Write Vitest tests for radar summary rendering, topic score rendering, and workshop draft package rendering.
- [ ] Run `npm test -- --run` and confirm the tests fail until UI code exists.
- [ ] Implement the React cockpit with Today Radar, Topic Pool, and Article Workshop views.
- [ ] Run `npm test -- --run` and `npm run build`.

### Task 4: Runtime verification

**Files:**
- Modify only as needed after verification.

- [ ] Run the backend API locally with `uvicorn ai_radar.api:app --app-dir apps/api`.
- [ ] Run the frontend with `npm run dev --workspace apps/web -- --host 127.0.0.1`.
- [ ] Verify `/api/radar/today` returns current JSON and the browser renders all three MVP pages.
- [ ] Stop both servers cleanly.

### Task 5: MVP audit

**Files:**
- Create: `README.md`

- [ ] Document setup, run commands, generated draft package paths, API keys/adapters, and MVP limitations.
- [ ] Re-read `PRD-ai-paper-content-radar.md` and `ARCHITECTURE.md`.
- [ ] Create a requirement checklist and verify current files, tests, build output, and generated artifacts cover each MVP requirement.
