# How YTDigest Works

What the app does from the moment it starts: the startup sequence, the
background loops that run on a schedule, and what only happens when you click
something.

There is no external scheduler (no cron, no Task Scheduler). Everything runs
inside the single FastAPI process as plain `asyncio` loops, started in the
`lifespan` function in [`src/main.py`](../src/main.py).

## Startup sequence

Runs once, in this order, before the app serves any request:

1. **`init_db()`** creates the SQLite tables and runs small column migrations.
2. **`load_config()`** reads `config.yaml`, or the file named by the
   `YTDIGEST_CONFIG_PATH` environment variable (test mode uses this to load
   `config.test.yaml`).
3. **Tag normalizer setup.** Existing tags are loaded from the database so new
   summaries reuse tag names you already have instead of inventing near-duplicates.
4. **Blocking refresh.** `refresh_video_metadata()` runs once and the web UI
   is not available until it finishes. It does two things:
   - **Fetch metadata.** For each configured channel it calls the YouTube Data
     API, gets recent uploads, and inserts any new ones. Only metadata is
     stored (title, channel, duration, ...), not transcripts. Limits come from
     `max_age_days`, `max_videos_per_channel`, and `filter_shorts` /
     `shorts_max_duration`.
   - **Summarize leftovers.** Videos that already have a transcript but no
     summary are summarized with Claude. New videos have no transcript yet, so
     this only catches backlog.
5. **Two background loops are started** (below), then the app begins serving.

On shutdown both loops are cancelled.

## Background loops

| Loop | Interval (`config.yaml`) | Does |
|------|--------------------------|------|
| Video fetcher | `video_refresh_interval` (3600s) | Discovers new videos, records metadata |
| Transcript fetcher | `transcript_fetch_interval` (300s) +/- jitter, `transcript_batch_size` (1) | Fetches a transcript, then summarizes and embeds it |

### Video fetcher (`background_video_fetcher`)

- Sleeps `video_refresh_interval`, then runs the same `refresh_video_metadata()`
  used at startup.
- The sleep comes first, so its first run is an hour after startup (the
  startup refresh covers the gap).
- It only discovers videos. It never fetches transcripts.

### Transcript fetcher (`background_transcript_fetcher`)

- Sleeps `transcript_fetch_interval` plus random jitter of -60 to +120
  seconds, to look less bot-like.
- Asks the database for up to `transcript_batch_size` videos whose
  `transcript_status` is `pending`, `NULL`, or `priority`. `priority` videos
  come first.
- For each video it calls `fetch_transcript()` (youtube-transcript-api):
  - **Success:** saves the transcript, sets status `fetched`, then immediately
    summarizes with Claude, saves the summary (with category and tags), and,
    if a Voyage key is configured, saves embeddings for the summary and for
    chunks of the full text.
  - **Failure:** sets status to `unavailable` or `failed` depending on the
    error. These videos are **not** retried automatically.
- At the defaults this is about one transcript every 5 minutes, roughly 12 an
  hour. The slow pace is deliberate: bulk fetching trips YouTube's IP
  blocking (see the probe-test section of `CLAUDE.md`).

Both loops catch and log their own exceptions and keep running, so one bad
cycle does not stop them.

## Pipeline for a video

```
YouTube API --(startup + hourly)--> videos row, status=pending
                                          |
                          (every ~5 min, one at a time)
                                          v
                  fetch_transcript() --fail--> status=unavailable/failed (stops)
                                          | ok
                                          v
                   save transcript -> Claude summary + category + tags
                                          v
                          Voyage embeddings (if key set)
```

## Transcript status values

| Status | Meaning |
|--------|---------|
| `pending` / `NULL` | Waiting for the transcript fetcher |
| `priority` | Set by the Prioritize action; fetched before `pending` |
| `fetched` | Transcript saved (and summarized) |
| `unavailable` | Fetch failed because the video has no usable transcript |
| `failed` | Fetch failed for another reason |

## On-demand endpoints

These do not run on a schedule; they run when called from the UI or the
bookmarklet. The highlights are below; see [api-endpoints.md](api-endpoints.md)
for the complete route table.

- `GET /` renders the digest page.
- `GET /api/refresh` triggers a manual metadata refresh (same function as the
  hourly loop).
- `POST /api/videos` and `POST /api/articles` add a single video or article by
  URL, fetching and summarizing immediately rather than waiting for the
  5-minute loop.
- `POST /api/videos/{id}/prioritize` sets status to `priority` so the
  transcript fetcher picks that video next.
- `POST /api/ask`, `POST /api/chat`: semantic Q&A over your digest and chat
  with a single item.
- `POST /api/embed-all` bulk-generates embeddings;
  `POST /api/backfill-categories` categorizes old summaries.
- Complete / uncomplete / favorite / notes endpoints track what you have read.

## Things to know

- **Slow startup.** The startup refresh blocks serving. With ~22 channels that
  is ~22 YouTube API calls plus any summarization before the page loads.
- **No automatic retry** of `unavailable` / `failed` videos. Retrying means
  resetting their status or using Prioritize.
- **Test mode** (port 8002, `scripts/start-test.ps1`) runs the same loops
  against `config.test.yaml`, a separate database, and a separate log
  directory. See `CLAUDE.md`.
- **Intentional demo bugs** exist for an unrelated Sentry demo (an N+1 query
  in `get_digest_items()`, an `asyncio.sleep(3)` in `save_video()`, and the
  `/sentry-debug` endpoint). They are tracked in Jira `YTD-32`; don't treat
  them as real problems.
