# Repository Guidelines

## Project Structure & Module Organization
Use the following layout:
- `app/frontend`: Next.js App Router client with shadcn/ui, Zustand, React Query, and Tailwind.
- `app/backend`: FastAPI APIs, background jobs, and database models.
- `app/shared`: zod/pydantic schemas, locale strings, and utility constants.
- `data/seeds`: AWL/NGSL CSVs, CN glosses, and ETL scripts.
- `docs`: Specs, UX copy, analytics briefs, and experiment logs.
Ship vertical slices that update backend contracts, shared types, and UI together. Version seed files and explain them in `data/seeds/README.md`.

## Build, Test, and Development Commands
Frontend:
- `cd app/frontend && pnpm install`
- `pnpm dev`, `pnpm test`, `pnpm lint`, `pnpm build`
Backend:
- `cd app/backend && poetry install`
- `poetry run uvicorn app.main:app --reload`
- `poetry run pytest`, `poetry run ruff check`
- `poetry run alembic upgrade head`
Infra: `docker compose up web api db redis` once containers exist; tear down with `docker compose down`.

## Coding Style & Naming Conventions
TypeScript runs in strict mode with ESLint + Prettier (2-space indent). Components adopt PascalCase, hooks camelCase, and routes/file names kebab-case. Co-locate UI state in `app/frontend/features/<feature>/`. Python follows Ruff + Black defaults, 4-space indent, snake_case modules, and explicit `async def` handlers. Store Chinese copy in `app/shared/locales/cn/*.json`; never hardcode CN strings in components. Add concise TSDoc or docstrings when behavior is non-obvious.

## Testing Guidelines
Place frontend tests beside components as `*.test.tsx`; cover recognition flow, state stores, and API hooks with Vitest + Testing Library. Backend tests live in `app/backend/tests/test_*.py`; ensure FSRS scheduling, triage endpoints, and ETL scripts have regression coverage. Use integration tests under `tests/integration/` to replay Recognize/Barely/Not sessions and assert scheduler outputs. Target >80% coverage on learning-core modules.

## Commit & Pull Request Guidelines
Follow Conventional Commits (`feat`, `fix`, `refactor`, `chore`, `docs`). Keep subject ≤72 characters, describe migrations or seed updates in the body, and tag `BREAKING CHANGE` when contracts move. Pull requests must link the tracking ticket, outline user-visible impact, attach screenshots or cURL snippets when applicable, and list commands/tests executed. Request review from the SRS owner whenever scheduler or spaced-repetition code changes.

## Spaced Repetition & Localization Priorities
Implement the Recognize/Barely/Not loop first: scheduler resides in `app/backend/learning/fsrs/`, grade mapping (`recognize=5`, `barely=3`, `not=1`), and a single `TriageCard` UI that logs latency. Seed AWL list 1–3 with CN glosses before expanding. Track all copy in `app/shared/locales`, provide aria-labels, keyboard access, and respect reduced motion. Keep Chinese hints in simplified characters aligned with TOEFL terminology.
