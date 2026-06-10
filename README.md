# eStudent MCP

A local [MCP](https://modelcontextprotocol.io) server that lets Claude Code
operate the PolyU **eStudent** portal: check grades/GPA, view your timetable and
exam schedule, search subjects, and add/drop subjects — plus a restrained course
**sniper** for registration-open and vacancy-watch scenarios.

Everything runs on your machine. Your NetID and password never leave it.

## Status

- ✅ **Skeleton complete & tested** — architecture, 9 tools, two-step
  registration confirmation, sniper scheduler with frequency safety floors,
  parsers (against a documented table structure), full unit-test suite.
- ⏳ **Needs joint-debug calibration** — the live portal's URLs, login form
  selectors, and table layouts. Search the code for `NEEDS_CALIBRATION`.
  This step needs your account and a one-time walkthrough (see below).

## Setup

```bash
cd ~/Desktop/Entertain_Apps/estudent-mcp
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m playwright install chromium

cp .env.example .env   # then edit .env with your NetID + password
```

Run the tests:

```bash
.venv/bin/python -m pytest -q
```

## Register with Claude Code

```bash
claude mcp add estudent -s user -- /Users/longyuhan/Desktop/Entertain_Apps/estudent-mcp/.venv/bin/python -m estudent_mcp.server
```

Then in Claude Code you'll have these tools:

| Tool | What it does |
|------|--------------|
| `session_status` | Is there a live logged-in session? |
| `get_grades` | Grades & GPA (optional `term` filter) |
| `get_timetable` | Class timetable |
| `get_exam_schedule` | Exam dates/venues |
| `search_subjects` | Find offerings + vacancies by code/keyword |
| `preview_registration` | Preview add/drop — **does not submit** |
| `confirm_registration` | Submit add/drop (requires the preview `fingerprint`) |
| `start_course_sniper` | Automated grab (open-time or vacancy-watch) |
| `sniper_status` | List / inspect / stop sniper jobs |

### Two-step registration

`confirm_registration` only submits if you pass the `fingerprint` returned by a
`preview_registration` of the **same** actions. This makes it impossible to drop
or add a subject without first seeing exactly what will change.

### The sniper is deliberately restrained

High-frequency "bombing" is **not supported**, by design:

- it's the fastest way to get your account/IP rate-limited or banned (so you'd
  miss the course anyway),
- it may violate the university's acceptable-use policy, and
- it's unfair to other students sharing the server.

Frequency floors are enforced and sub-floor configs are rejected:

- **open_time** mode: retry interval ≥ 3s, total retry window ≤ 2 min.
- **watch_vacancy** mode: poll interval ≥ 60s.

Keep your Mac awake while a job runs; the server uses `caffeinate` during active
jobs. Set `ESTUDENT_HEADFUL=1` in `.env` to watch the browser for debugging.

## Architecture

```
src/estudent_mcp/
  server.py            # MCP tool layer (no browser code)
  backend/
    base.py            # EStudentBackend interface (stable)
    playwright_backend.py   # scheme A (current)
    # future: hybrid_backend.py  # scheme C: Playwright login + httpx fetch
  parsers/             # HTML -> dataclasses (pure, unit-tested, backend-agnostic)
  registration.py      # fingerprint + summary (two-step invariant)
  sniper.py            # scheduler + frequency floors
  models.py            # shared dataclasses
  config.py  errors.py
```

The `EStudentBackend` interface is what lets us later swap in a faster
HTTP-based backend (scheme C) without touching the tools or parsers.

## Joint-debug calibration (one-time, needs your account)

The parsers and navigation target a documented generic table structure. To point
them at the real pages:

1. Put your real credentials in `.env`, set `ESTUDENT_HEADFUL=1`.
2. With Claude Code, walk through login → grades → timetable → exams → subject
   search → registration. We save each page's HTML into `tests/fixtures/`
   (de-identified) and adjust the `NEEDS_CALIBRATION` URLs/selectors and the
   `HDR_*` header constants in `parsers/*.py` to match.
3. Re-run `pytest` against the real fixtures.
4. Verify read-only tools against your live account; verify registration only to
   the `preview` step until you actually need to add/drop.
```
