# ConsultBae Take-Home Assignment

## Overview

This repo merges 3 messy CSVs (Naukri job applicants, gig workers, CBNexus contacts) into a single clean database, with the same person appearing across multiple files resolved into one record — plus a no-code automation, a mini audio collection app, and supporting documentation.

## Project structure

```
.
├── data/
│   ├── df1_final.csv          # cleaned & normalized source1 (Naukri applicants)
│   ├── df2_final.csv          # cleaned & normalized source2 (gig workers)
│   ├── df3_final.csv          # cleaned & normalized source3 (CBNexus contacts)
│   └── consultbae.db          # unified SQLite database (person, skill, audio_submission, etc.)
├── notebooks/
│   ├── task1_consultbae.py           # source loading, normalization, per-file dedup
│   ├── build_unified_database.py     # cross-file matching cascade -> unified person table
│   └── task3_audio_app.py            # Flask audio collection app
├── reports/
│   └── data_issues_report.md  # Task 4 — full data quality findings & resolutions
├── STUCK_LOG.md                # hardest debugging moments & how they were resolved
└── README.md                   # this file
```

*(Structure will grow as Task 2's no-code automation flow export is added.)*

## Setup

### Requirements
- Python 3.10+
- pandas
- rapidfuzz

```bash
pip install pandas rapidfuzz
```

### Running the Task 1 pipeline

The pipeline was built and run in Google Colab, reading from CSVs mounted via Google Drive. To run locally instead:

1. Clone this repo
2. Place the 3 raw source CSVs in the same directory as the script (or update the file paths at the top of `notebooks/task1_consultbae.py`)
3. Run:
```bash
python notebooks/task1_consultbae.py
```
This produces the 3 cleaned dataframes found in `data/`.

4. Then run the matching cascade to build the unified database:
```bash
python notebooks/build_unified_database.py
```
This produces `data/consultbae.db` — the unified `person` table plus `person_source_record`, `skill`, and `audio_submission`.

### Running the Task 3 audio app

```bash
pip install pydub flask
# ffmpeg must also be installed and on PATH (pydub depends on it)
python notebooks/task3_audio_app.py
```
The app was developed and demoed in Colab using an `ngrok` tunnel for a public URL; see the script for the tunnel setup if running there instead of locally.

## Task 1 — Data Merge

Full methodology and matching strategy:
- **Email** is the primary match key between source1 (Naukri) and source2 (gig workers)
- **Phone** is the primary match key between source1/source2 and source3 (CBNexus), which has no email field
- **Fuzzy name + city matching** is used as a fallback for records that don't share an email or phone with anything already on file — but only when the candidate's email/phone don't actively conflict with what's already on record. Two people can share a name; if their contact details disagree, they're kept as separate records and flagged `manual_review` rather than force-merged.
- A final consolidation pass groups any remaining same-name/same-city entries and merges only the subsets with no internal conflicts

Every person record carries a `match_confidence` (`high` / `medium` / `manual_review`) so merge certainty is visible, not hidden. Final result: **55 unique people** merged across all 3 sources, with 2 confirmed same-name-different-person cases correctly kept separate.

See [`reports/data_issues_report.md`](reports/data_issues_report.md) for the full list of data quality issues found in each source file and how each was resolved.

## Task 2 — No-code Automation

*(Not yet started)*

## Task 3 — Audio Collection App

A Flask app (`notebooks/task3_audio_app.py`) where a person enters their name and phone number, then either records audio directly in the browser or uploads a file. On submission:
- The audio file is saved to disk
- Duration, sample rate (kHz), bitrate, and loudness (dB) are extracted using `pydub`
- A rough quality estimate is derived from the loudness reading (flags unusually quiet or clipped recordings)
- The submitter is matched to an existing `person` record by phone number, or a new one is created if they weren't in any of the original 3 source files
- The submission is linked to that person and stored in `audio_submission`

A second view (`/submissions`) lists every submission with a working audio player and the extracted properties.

## Task 4 — Data Issues Report

See [`reports/data_issues_report.md`](reports/data_issues_report.md).

## Task 5 — Stretch: Scaling to 5,000 workers

*(Not yet started)*

## Stuck Log

See [`STUCK_LOG.md`](STUCK_LOG.md) for the hardest problems hit during this assignment and exactly how each was resolved — including a malformed-row detection bug, a data-integrity verification step, a GitHub credential exposure incident, and a silent partial-database-write bug in the audio app.

## Status

- [x] Task 1 — source cleaning, normalization, and per-file dedup (all 3 sources)
- [x] Task 1 — cross-file matching cascade → unified `person` table in SQLite (55 people)
- [ ] Task 2 — no-code automation
- [x] Task 3 — audio collection app (recording/upload, property extraction, DB linking, submissions view)
- [x] Task 4 — data issues report
- [ ] Task 5 — stretch (scaling considerations)
- [ ] Screen recording
