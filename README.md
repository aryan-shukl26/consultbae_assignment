# ConsultBae Take-Home Assignment

## Overview

This repo merges 3 messy CSVs (Naukri job applicants, gig workers, CBNexus contacts) into a single clean database, with the same person appearing across multiple files resolved into one record — plus a no-code automation, a mini audio collection app, and supporting documentation.

## Project structure

```
.
├── data/
│   ├── df1_final.csv          # cleaned & normalized source1 (Naukri applicants)
│   ├── df2_final.csv          # cleaned & normalized source2 (gig workers)
│   └── df3_final.csv          # cleaned & normalized source3 (CBNexus contacts)
├── notebooks/
│   └── task1_consultbae.py    # source loading, normalization, dedup pipeline
├── reports/
│   └── data_issues_report.md  # Task 4 — full data quality findings & resolutions
├── STUCK_LOG.md                # hardest debugging moments & how they were resolved
└── README.md                   # this file
```

*(Structure will grow as Tasks 2/3 are added — no-code automation flow export and the audio app.)*

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

> **Note:** The unified SQLite database build (matching cascade across all 3 cleaned files into one `person` table) is the next step in this pipeline — see [Status](#status) below.

## Task 1 — Data Merge

Full methodology and matching strategy:
- **Email** is the primary match key between source1 (Naukri) and source2 (gig workers)
- **Phone** is the primary match key between source1/source2 and source3 (CBNexus), which has no email field
- **Fuzzy name + city matching** (with an email/phone conflict check to prevent false merges) is used as a fallback for records that don't share an email or phone with anything already on file

See [`reports/data_issues_report.md`](reports/data_issues_report.md) for the full list of data quality issues found in each source file and how each was resolved.

## Task 2 — No-code Automation

*(In progress — not yet started)*

## Task 3 — Audio Collection App

*(In progress — not yet started)*

## Task 4 — Data Issues Report

See [`reports/data_issues_report.md`](reports/data_issues_report.md).

## Task 5 — Stretch: Scaling to 5,000 workers

*(Not yet started)*

## Stuck Log

See [`STUCK_LOG.md`](STUCK_LOG.md) for the hardest problems hit during this assignment and exactly how each was resolved — including a fuzzy-matching false-positive bug, a stale-notebook-state debugging session, and a GitHub credential exposure incident and its fix.

## Status

- [x] Task 1 — source cleaning, normalization, and per-file dedup (all 3 sources)
- [ ] Task 1 — cross-file matching cascade → unified `person` table in SQLite
- [ ] Task 2 — no-code automation
- [ ] Task 3 — audio collection app
- [x] Task 4 — data issues report
- [ ] Task 5 — stretch (scaling considerations)
- [ ] Screen recording
