# ConsultBae Take-Home Assignment

## Overview

This repo merges 3 messy CSVs (Naukri job applicants, gig workers, CBNexus contacts) into a single unified database, resolving the same person appearing across multiple files into one record. On top of that database sits a no-code LLM automation that auto-classifies each person's skill category, and a mini web app for collecting audio submissions with automatic property extraction.

## Project structure

```
.
├── data/
│   ├── df1_final.csv                   # cleaned & normalized source1 (Naukri applicants)
│   ├── df2_final.csv                   # cleaned & normalized source2 (gig workers)
│   ├── df3_final.csv                   # cleaned & normalized source3 (CBNexus contacts)
│   └── consultbae.db                   # unified SQLite database
├── notebooks/
│   └── task1_task3_consolidated.py     # Tasks 1 & 3: cleaning, unified DB build, verification, audio app
├── reports/
│   ├── data_issues_report.md           # Task 4 — full data quality findings & resolutions
│   ├── task2_make_scenario.json        # Task 2 — exported Make.com automation blueprint
│   └── task5_scaling_considerations.md # Task 5 — stretch: scaling to 5,000 workers
├── STUCK_LOG.md                         # hardest debugging moments & how they were resolved
└── README.md                            # this file
```

## Setup

### Requirements
- Python 3.10+
- pandas, rapidfuzz, flask, pydub
- ffmpeg (system dependency, required by pydub for audio decoding)

```bash
pip install pandas rapidfuzz flask pydub
# ffmpeg must also be installed and on PATH
```

### Running the pipeline (Tasks 1 & 3)

Task 1 (data merge) and Task 3 (audio app) were consolidated into a single notebook/script sharing one database and one runtime, after repeatedly hitting sync issues from running them in separate Colab sessions with separately-copied `.db` files (see `STUCK_LOG.md`).

```bash
python notebooks/task1_task3_consolidated.py
```

Run top to bottom in one session. This:
1. Loads and cleans all 3 source CSVs
2. Runs the tiered matching cascade to merge them into one `person` table
3. Builds `consultbae.db` with the full schema (Task 1 tables + Task 3's `audio_submission` table together)
4. Runs a built-in verification pass that asserts data integrity and prints a pass/fail banner
5. Starts the Flask audio collection app against that same database, in the same runtime

Once running:
- `/` — submission form (name, phone, record or upload audio)
- `/submissions` — list of all submissions with playback and extracted properties
- `/db-test` — quick health check confirming DB connectivity and row counts

### Running Task 2 — the automation

The automation (Make.com) is not code you run locally — it's a hosted scenario that calls two API endpoints exposed by the Flask app above. To re-run it:
1. Start the app (above) and note its public ngrok URL
2. Open the scenario in Make.com (or re-import [`reports/task2_make_scenario.json`](reports/task2_make_scenario.json) as a new scenario)
3. Update the two Flask HTTP modules' URLs to match your current ngrok URL if it's changed
4. Run the scenario

See [Task 2](#task-2--no-code-automation) below for the full design.

## Task 1 — Data Merge

**Matching strategy** (tiered, in order of certainty):
- **Tier 1 — exact match**: email between source1 (Naukri) and source2 (gig workers); phone between source1/source2 and source3 (CBNexus), which has no email field
- **Tier 2 — fuzzy name+city fallback**: for anyone left unmatched, name+city similarity is used, but only accepted if the candidate's email/phone don't actively conflict with what's already on record. Two people can share a name — if their contact details disagree, they're kept as separate records and flagged `manual_review` rather than force-merged
- **Tier 3 — confidence tagging**: every person record carries `match_confidence` (`high` / `medium` / `manual_review`) so merge certainty is visible, not hidden
- **Tier 4 — consolidation pass**: a final union-find grouping catches any remaining same-name/same-city duplicates, merging only the subsets with no internal conflicts

**Result**: 55 unique people merged across all 3 sources, with 2 confirmed same-name-different-person cases (Arjun Mehta, Deepak Nair) correctly kept separate rather than wrongly merged.

**Built-in verification**: the pipeline ends with an assertion-based check that reopens the database from disk and confirms table presence, person/skill counts, no duplicate skill rows, the two known ambiguous cases are still separate, CTC values are stored as real numbers (not corrupted by a numpy-type serialization bug hit during development), and no orphaned foreign keys — before printing a final pass/fail banner. If anything is wrong, the script throws rather than silently reporting success.

See [`reports/data_issues_report.md`](reports/data_issues_report.md) for the full list of data quality issues found in each source file and exactly how each was resolved.

## Task 2 — No-code Automation

**Tool used**: Make.com (free tier — no card required, unlike n8n Cloud's trial signup, and no self-hosting overhead compared to n8n Community Edition).

**What it does**: reads every person in the database without a `skill_category`, asks an LLM to classify their skills into one of `automation-heavy` / `web dev` / `data` / `other`, and writes the result back — the "LLM auto-tag" option from the assignment brief.

**Architecture**:
```
Make.com (cloud) ──public internet──> ngrok tunnel ──> Flask app (port 5000)
                                                              │
                                                    reads/writes consultbae.db
```
Make.com is a fully hosted service and can't reach a local database directly, so the Flask app was extended with two small API endpoints as a bridge:
- `GET /api/untagged-people` — returns people with no `skill_category` yet, plus their combined skill list
- `POST /api/tag-person` — receives `{person_id, category}` and writes it to the database

**Scenario flow** (5 modules, exported to [`reports/task2_make_scenario.json`](reports/task2_make_scenario.json)):
1. **HTTP** — `GET /api/untagged-people`
2. **Iterator** — processes one person at a time
3. **Sleep (3s)** — throttles requests to stay under Groq's free-tier rate limit (30 requests/minute)
4. **HTTP** — `POST` to Groq's chat completion API, prompting classification based on the person's skills
5. **HTTP** — `POST /api/tag-person` with the returned category

**Result**: all 55 people successfully classified — 30 `web dev`, 15 `automation-heavy`, 10 `data` — verified directly against the database after the run, not just trusted from Make's UI.

## Task 3 — Audio Collection App

A Flask app where a person enters their name and phone number, then either records audio directly in the browser or uploads a file. On submission:
- The audio file is saved to disk
- Duration, sample rate (kHz), bitrate, and loudness (dB) are extracted using `pydub`
- A rough quality estimate is derived from the loudness reading (flags unusually quiet or clipped recordings)
- The submitter is matched to an existing `person` record by phone number, or a new one is created if they weren't present in any of the original 3 source files
- The submission is linked to that person and stored in `audio_submission`, as a single atomic transaction (a two-step version of this caused a real bug during development — see `STUCK_LOG.md`)

A second view (`/submissions`) lists every submission with a working audio player and the extracted properties.

## Task 4 — Data Issues Report

See [`reports/data_issues_report.md`](reports/data_issues_report.md) — a full, specific accounting of every data quality problem found across the 3 source files (inconsistent formats, exact and near-duplicates, malformed rows, ambiguous same-name records, unit inconsistencies) and exactly what was done about each.

## Task 5 — Stretch: Scaling to 5,000 Workers

See [`reports/task5_scaling_considerations.md`](reports/task5_scaling_considerations.md) for the full write-up. Short version: the current architecture (SQLite, local file storage, a single Flask process) is a prototype, not a launch-ready system — SQLite's single-writer lock and local disk storage would be the first things to break under concurrent load from thousands of workers in one weekend.

## Stuck Log

See [`STUCK_LOG.md`](STUCK_LOG.md) for the hardest problems hit during this assignment and exactly how each was resolved — including a malformed-row detection bug, a data-integrity verification step, a GitHub credential exposure incident, and a silent partial-database-write bug in the audio app.

## Status

- [x] Task 1 — source cleaning, normalization, and per-file dedup (all 3 sources)
- [x] Task 1 — cross-file matching cascade → unified `person` table in SQLite (55 people, verified)
- [x] Task 2 — no-code automation (Make.com, LLM skill-category auto-tagging)
- [x] Task 3 — audio collection app (recording/upload, property extraction, DB linking, submissions view)
- [x] Task 4 — data issues report
- [x] Task 5 — stretch (scaling considerations)
- [ ] Screen recording
