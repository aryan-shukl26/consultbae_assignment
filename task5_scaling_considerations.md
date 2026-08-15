# Task 5 — Stretch: Scaling to 5,000 Workers Over a Weekend

The current build (SQLite, local file storage, a single Flask process on one Colab/local machine) is a working prototype, not something that survives 5,000 gig workers hitting it in one weekend. Here's what breaks first, and what I'd change before launch.

## What breaks first

**1. SQLite's single-writer lock.** SQLite allows many concurrent readers but only one writer at a time — every other write blocks or times out until the current one finishes. With thousands of workers submitting audio and each submission triggering a write (`handle_submission`'s person lookup/insert + audio_submission insert), concurrent traffic would queue up fast, and under real load this shows up as slow or failing submissions, not a clean error. This is the first thing to fail, and it would fail silently at first (just getting slower) before it failed loudly (timeouts, dropped requests).

**2. Local file storage for audio.** Audio files currently save to a local `audio_submissions/` folder on whatever machine is running the app. That has two problems at scale: disk fills up (a few thousand recordings, even short ones, add up), and it doesn't survive the app restarting, redeploying, or running on more than one server — there's no way to horizontally scale a Flask app with local-disk state, since a second server instance wouldn't see files saved by the first.

**3. A single Flask process, single thread per request.** The current `app.run()` setup handles one request at a time by default. At real concurrency, this becomes the bottleneck before the database even does — requests would simply queue behind each other.

**4. No upload validation or size limits.** Nothing currently caps file size, rejects malformed/corrupt audio before processing, or handles a worker submitting a 45-minute file by accident. `pydub`/`ffmpeg` processing a large or corrupted file could hang or crash the single worker thread handling it, taking that request down with it.

**5. Duplicate submissions.** There's currently no protection against the same worker submitting twice (network retry, accidental double-tap, or intentionally gaming a per-submission payment). The `handle_submission` phone-lookup logic finds the same *person*, but nothing stops a second, third, or hundredth `audio_submission` row from being created for that person.

## What I'd change before launch

**Storage**
- Move audio files to object storage (S3, GCS, or similar) rather than local disk — durable, doesn't depend on any one server staying alive, and scales storage independently of compute
- Keep only the object storage *key/URL* in the database, not the file itself

**Database**
- Move from SQLite to a real client-server database (Postgres is the natural choice) — supports genuine concurrent writes, connection pooling, and doesn't have SQLite's single-writer constraint
- Add a unique constraint or application-level check on `(person_id, submitted_at)` within a short window, or a client-generated idempotency key per submission, to reject accidental duplicate submits

**Compute**
- Run the Flask app behind a proper WSGI server (gunicorn/uwsgi) with multiple worker processes, behind a load balancer, so requests aren't serialized through one thread
- Move audio processing (`extract_audio_properties`) off the request thread entirely — into a background job queue (Celery, or a simpler task queue) so a slow/large file doesn't block other people's submissions while it decodes

**Validation and failure handling**
- Enforce a max file size and reject oversized uploads before they're saved or processed
- Validate the audio file is genuinely decodable before committing anything to the database, and return a clear, specific error if not (rather than a generic 500)
- Add retry-safe design on the client side: if a submission fails partway through, the worker should be able to safely resubmit without creating a duplicate record, once idempotency keys are in place

**Cost**
- Object storage + a small managed Postgres instance is cheap at this scale (a few thousand short audio files is a small storage footprint, well under most free/low tiers)
- The main cost driver would be compute for audio processing if done synchronously at peak load — moving it to a background queue also smooths out cost, since it can process at a steady rate rather than needing to provision for burst traffic

## What I'd explicitly NOT over-build for a weekend launch

Given the actual scale (5,000 workers, one weekend — not millions of users indefinitely), I would not reach for a distributed message broker cluster, multi-region deployment, or a custom-built audio processing pipeline. A single Postgres instance, object storage, a handful of Flask worker processes behind a load balancer, and a simple background job queue for audio processing is enough headroom for this scale without introducing operational complexity that a small team can't reasonably maintain over a single weekend.
