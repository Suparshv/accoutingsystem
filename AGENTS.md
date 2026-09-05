# AGENTS.md

Operating rules for any AI agent working in this repository.

**Read this file fully before your first edit of a session.** It is short by design.
`SPEC.md` is the reference manual — 3,300 lines, read the sections you need. This file
is the working agreement: what you may do, what you must never do, and how to hand work
back to a human.

---

## 0. What this project is

A double-entry accounting system for a furniture business. Odoo Hackathon 2026, 24-hour
build, three human developers plus agents.

The system's defining property: **every financial transaction produces a balanced journal
entry, and every report is an aggregation over those entries.** Nothing stores a balance.
If you find yourself adding a `balance` column, you have taken a wrong turn — reread
`SPEC.md §6`.

---

## 1. The seven rules that are never broken

These are not style preferences. Violating any one produces silently corrupt financial
data. If a task appears to require breaking one, **stop and ask a human.**

### R1 — One writer to the ledger

`app/services/accounting.py::post_journal_entry()` is the **only** function in this
repository that may INSERT into `journal_entries` or `journal_entry_lines`.

Routers do not. Other services do not. Scripts do not. They all call it.

```bash
# Self-check before every commit that touches accounting:
grep -rn "JournalEntry(\|JournalEntryLine(" backend/app/ --include=*.py
# Expected: hits ONLY in services/accounting.py
```

_Why:_ one place to enforce the balance rule, one place to test, one place to fix.

### R2 — Never `float` in a money path

`Decimal` in Python. `NUMERIC(14,2)` in Postgres. Strings on the JSON wire.

```python
Decimal("199.99") * 3   # 599.97          correct
199.99 * 3              # 599.9699999...  corrupts the balance sheet
```

Never write `float(`, never use `type="number"` on a money input, never do money
arithmetic in JavaScript. Display server-computed values.

```bash
grep -rn "float(" backend/app/ --include=*.py   # expected: no hits
```

### R3 — Never `commit()` inside the posting engine

`post_journal_entry` calls `db.flush()`, never `db.commit()`. The **caller** owns the
transaction boundary so that a document and its journal entry commit together or roll
back together.

This is the most dangerous rule to break because **nothing looks wrong when you do.**
The app works, the demo works, and the database quietly accumulates confirmed documents
with no ledger entry.

### R4 — Posted entries are immutable

No UPDATE, no DELETE, ever. No `PUT` or `DELETE` route may exist for journal entries.
To undo, reverse (create an opposite entry). Same for confirmed documents — their lines
cannot change.

### R5 — Derive, never store

Payment status, account balances, report totals, budget achievement: **computed on read.**
Never a column. See `SPEC.md §7.9.1` for the reasoning.

The one permitted exception is `journal_entries.total_amount`, for list-view display
only. It is never read by a report.

### R6 — The server never trusts the client

- `line_total` is recomputed server-side from quantity × unit_price; any client value
  is discarded.
- `state`, totals, `number`, and every `*_id` link are never accepted from a request body.
- Authorisation is enforced in the route dependency. A hidden button is not a security
  control.
- Ownership filters derive from the verified JWT, never from a query parameter.

### R7 — Every behaviour traces to a scenario

`SPEC.md §10` has 105 Gherkin scenarios. They are the definition of correct.

**If you are about to implement behaviour that has no scenario, stop and ask.** Do not
invent business rules. Do not "improve" the spec mid-implementation.

---

## 2. Before you write code

1. **Read the relevant `SPEC.md` sections.** For accounting work, `§6` (the domain model)
   is mandatory — the logic is not intuitive and guessing produces plausible-looking
   wrong answers.
2. **Find the scenarios** in `§10` that cover your task. They are your acceptance criteria.
3. **Check the priority tier** in `§17`. If your task is P1 and any P0 item is unfinished,
   say so and work the P0 item instead.
4. **State your plan** in one short paragraph before editing: which files, which scenarios
   you are satisfying, what you are _not_ doing.

---

## 3. Architecture you must respect

```
routers/  →  services/  →  models/
```

| Layer       | Owns                                               | Never does                                                         |
| ----------- | -------------------------------------------------- | ------------------------------------------------------------------ |
| `routers/`  | parse, authorise, call one service, shape response | business logic, `if` on business conditions, import another router |
| `services/` | all business logic, all transaction boundaries     | HTTP concerns, status codes                                        |
| `models/`   | structure, constraints, relationships              | behaviour beyond simple properties                                 |

A router function that exceeds ~15 lines is a signal that logic leaked downward.
Move it to a service.

Full file layout: `SPEC.md §4`.

---

## 4. Commands

```bash
# Database
docker compose up -d
docker compose down -v          # wipes data — the schema-change protocol

# Backend
cd backend && source .venv/bin/activate
pip install -r requirements.txt
python -c 'from app.database import init_db; init_db()'
python seed.py                  # must end with the balance assertion passing
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Quality gates — run before every commit
cd backend && ruff check . && ruff format --check . && pytest
cd frontend && npx tsc --noEmit && npm run lint
```

**Schema changed?** There are no migrations by design (`SPEC.md §3`). Tell the humans in
team chat, then everyone runs `docker compose down -v && docker compose up -d`, `init_db()`,
`seed.py`.

---

## 5. Verification before you claim something works

Do not report a task complete on the basis that the code looks right.

```yaml
always:
  - "ruff, tsc and eslint pass with zero warnings"
  - "the specific §10 scenarios for this task were walked and hold"
  - "no console.log, no print(), no commented-out code"

when_touching_the_ledger:
  - "pytest tests/test_posting_engine.py passes"
  - "GET /reports/trial-balance returns is_balanced: true"
  - "the R1 and R2 greps come back clean"

when_touching_a_confirm_flow:
  - "confirming produces exactly the journal entry lines in §8.2's worked example"
  - "a forced failure mid-confirm leaves NO partial data — document still draft,
    no orphan entry (SPEC.md §10.5, the atomicity scenario)"

when_touching_the_frontend:
  - "loading, error and empty states all render — not just the happy path"
  - "usable at 375px, 768px and 1440px"
  - "money is right-aligned with tabular figures"
```

---

## 6. Scope discipline

This is a 24-hour build. The most common failure is not bad code — it is too much code.

- **Build the smallest thing that satisfies the scenario.** Nothing more.
- **Do not add libraries.** The stack in `SPEC.md §3` is closed. If you believe something
  is genuinely missing, ask; do not install it.
- **Do not refactor adjacent code** you were not asked to touch.
- **Do not add features you think would be nice.** They are not in the scope, they will
  not be demoed, and they will break something that would have been.
- **If you are unsure whether something is in scope, it is not.** Ask.

Prefer deleting code over adding a flag.

---

## 7. Committing

```
<type>(<scope>): <imperative summary>

feat(accounting): add balance validation to posting engine
fix(budgets): exclude draft bills from achievement
test(posting): cover unbalanced entry rejection
```

Types: `feat` `fix` `refactor` `test` `docs` `chore` `style`.

- One logical change per commit.
- **Never commit** `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `uploads/`.
- **Never commit secrets.** Not even placeholder ones that look real.
- Work on a feature branch (`feat/<area>-<description>`), never directly on `main`
  after the first hour.

Humans review and merge. Do not merge your own PRs.

---

## 8. When you get stuck or find a conflict

**Ask. Do not guess.** A wrong guess in accounting logic produces output that looks
entirely plausible and is wrong, which is worse than no output.

| Situation                           | What to do                                                                   |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| The mockup and `SPEC.md` disagree   | Follow `SPEC.md`, and flag the conflict in your response                     |
| A scenario is ambiguous             | Ask. Do not pick an interpretation silently.                                 |
| A task seems to need breaking R1–R7 | Stop. Explain why. Wait.                                                     |
| A pinned version fails to install   | Report it and stop. Do not upgrade.                                          |
| A test fails and you cannot see why | Report the failure with the actual output. Do not delete or weaken the test. |
| You are about to write `# TODO`     | Either finish it or tell a human it is unfinished                            |

Never disable, skip, or loosen a test to make a build pass.

---

## 9. Session close

End every working session with:

1. What you changed, in two or three lines.
2. Which `§10` scenarios you verified, and how.
3. Anything you left unfinished or uncertain — explicitly, not buried.
4. Anything you noticed that a human should decide.

Silence about a problem is worse than the problem.

---

## Quick reference

| I need to know…                             | Read                             |
| ------------------------------------------- | -------------------------------- |
| How accounting actually works               | `SPEC.md §6`                     |
| Exact table and column definitions          | `SPEC.md §7`                     |
| How to build a journal entry for a document | `SPEC.md §8.2` (worked examples) |
| The API shape for an endpoint               | `SPEC.md §9`                     |
| What "correct" means for my task            | `SPEC.md §10`                    |
| Validation rules                            | `SPEC.md §11`                    |
| Error codes and security rules              | `SPEC.md §12`                    |
| Component and styling rules                 | `SPEC.md §13`                    |
| What to build and in what order             | `SPEC.md §17`                    |
| Whether I am done                           | `SPEC.md §18.1`                  |
