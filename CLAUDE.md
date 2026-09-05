# YTDigest

A daily digest application that fetches new videos from specified YouTube channels, retrieves transcripts, generates AI summaries via Claude API, and displays them in a local web interface.

## Test mode: a channel-selection proof of concept

`scripts/start-test.ps1` runs this same codebase in a second mode, on
**port 8002**, using `config.test.yaml` instead of `config.yaml`, a separate
DB (`data/ytdigest-test.db`), a separate log dir (`logs/test/`), and
`SENTRY_ENVIRONMENT=test` (the normal `scripts/start.ps1` / port 8001 run
defaults to `environment:production`). Both modes report to the **same**
Sentry project (org `george-grohwin`, project `ytdigest`) — distinguished
only by that `environment` tag, so any Sentry query needs an explicit
`environment:production` or `environment:test` filter rather than assuming
one or the other.

(A separate `../YTDigest-test` clone was used earlier for the same purpose
and has been retired/folded into this setup — its `CLAUDE.md` is no longer
maintained; this file is now the source of truth.)

**Why test mode exists**: to generate real, organically-occurring Sentry
error activity as raw material for a separate portfolio project — a
Sentry → ticketing-system (e.g. JIRA) integration that reads Sentry's API
and creates tickets from real issues. The data needs to be genuine app
behavior, not synthetic/fabricated errors, so the approach is to make
*real* failures more likely (via `config.test.yaml`'s channel list), never
to fake them.

### Channel list: an initial proof of concept, not a settled result

`config.test.yaml`'s channels were deliberately chosen to be more
failure-prone for this app's fetch/transcript pipeline than the curated
`config.yaml` list, grouped by hypothesis:

- **live_news** (LiveNOW from FOX, NBC News, Bloomberg Originals, FOX
  Weather, Sky News, Al Jazeera English, LIVE STREAM NEWS) — 24/7 live
  streams often have missing or delayed captions.
- **age_restricted** (Wendigoon, Rotten Mango, Lazy Masquerade, Sam and
  Colby) — horror/true-crime creators frequently get individual videos
  age-gated, which surfaces as "video unavailable" without authentication.
- **non_english** (HikakinTV, HikakinGames, Koji Seto, Takomaru,
  KingDaddyDMAC, buzzbean11) — Japanese/Korean channels; this also doubles
  as a live test of the Unicode-logging-on-Windows bug tracked in Jira
  (`YTD-34`).
- **members_only** (H3 Podcast) — hypothesized to trigger access errors, but
  flagged as uncertain: members-only videos are typically excluded from a
  channel's *public* uploads feed entirely, so this app's
  `get_channel_uploads()` may never even see them.

**Treat this as a first pass, expected to change.** As real `environment:test`
Sentry activity accumulates, expect to revisit which channels/categories
actually produce useful signal vs. noise, and prune or expand the list
accordingly — this was never meant to be the final channel selection.

### The probe test, and why its results were mostly inconclusive

`scripts/probe_channels.py` was written to validate the channel hypothesis
empirically before committing to the list: it resolves each candidate
channel and calls the app's real `fetch_transcript()` against ~8 recent
videos per channel, measuring actual failure rates. It deliberately never
imports `src.main` (so it never calls `sentry_sdk.init()` and never
pollutes Sentry with probe noise).

**The result was mostly a lesson in YouTube's anti-scraping IP blocking,
not a clean answer.** `youtube-transcript-api` (used by
`src/transcripts.py`) scrapes YouTube's internal caption endpoints rather
than an official API, and bulk-probing many videos in a short window
repeatedly triggered a real, persistent IP block — evidenced by the literal
"YouTube is blocking requests from your IP" error, not a content-based
failure. This affects the probe *and* test mode's own background transcript
fetcher equally, since the block is IP-based, not per-process. Refreshing
`cookies.txt` with a real logged-in browser session doesn't fix an
already-active block either — cookies only reduce the odds of *triggering*
a block, they don't lift one already in effect; only time does.

**Only three channels ever got a clean read** before the block hit, all in
`live_news`: LiveNOW from FOX (25% failure), NBC News (25% failure),
Bloomberg Originals (0% failure) — modest, believable numbers. Every other
channel's result in `scripts/probe_results.json` showing ~100% failure
should be read as **inconclusive due to the IP block, not confirmation
that channel is error-prone**. Treat the category groupings above as a
reasonable, evidence-informed hypothesis that real Sentry activity is what
actually validates over time — not something the probe itself confirmed.

### Reading Sentry `environment:test` activity — what actually matters

When asked to check Sentry for "interesting activity" from test mode, the
useful signal is **novel error types/patterns, not more of what's already
been seen**. Two categories of already-known noise to recognize and not
over-report:

1. **The YouTube IP-block error** ("YouTube is blocking requests from your
   IP") — the dominant, sometimes only, failure mode seen so far (see the
   probe test above). A handful of these is expected background noise, not
   the channel-specific signal the experiment is looking for.
2. **The deliberately-staged demo bugs** below — pre-existing and unrelated
   to this experiment.

So: when summarizing `environment:test` Sentry activity, group by distinct
error message rather than just raw event/issue count, and call out
specifically what's **new** — a message or pattern not already covered by
the two categories above — since that's the actual signal this experiment
is trying to surface.

### Deliberately-staged demo bugs

This codebase currently contains bugs staged for an unrelated Sentry-product
interview — an unfixed N+1 query in `get_digest_items()`, an
`await asyncio.sleep(3)` artificial race window in `save_video()`, and a
`/sentry-debug` endpoint that raises a `ZeroDivisionError` on demand (see
Jira `YTD-32`, "Remove contrived Sentry demo bugs"). Issues from these
are pre-existing/intentional in both run modes — don't mistake them for
real signal from either the normal app or the test-mode experiment.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API keys
cp .env.example .env

# Edit config.yaml to add your preferred YouTube channels

# Run the app (use python -m to avoid Smart App Control blocking uvicorn.exe)
.venv\Scripts\python -m uvicorn src.main:app --reload --port 8001
```

Open http://localhost:8001 in your browser (see "Test mode: a
channel-selection proof of concept" above — test mode uses 8002).

## Project Structure

- `src/main.py` - FastAPI application entry point
- `src/youtube.py` - YouTube API client for fetching videos
- `src/transcripts.py` - Transcript fetching using youtube-transcript-api
- `src/summarizer.py` - Claude API integration for generating summaries
- `src/database.py` - SQLite database operations
- `src/models.py` - Pydantic models for type safety
- `templates/digest.html` - Jinja2 template for the web interface
- `config.yaml` - Channel list and digest preferences
- `.env` - API keys (not committed to git)

## API Keys Required

1. **YouTube Data API v3** - Get from Google Cloud Console
2. **Anthropic API** - Get from console.anthropic.com

## Workflow

- **Backlog/roadmap tracking lives in Jira**, not `ROADMAP.md`. Project `YTD` on
  `ggrohwin.atlassian.net` (Story Points, Priority, and a custom "Category"
  field — Feature/Infra/Cleanup/Refactor/Learning — cover what the old
  Type/Effort columns did). `ROADMAP.md` was retired 2026-08-24: it's a frozen
  historical snapshot of the pre-Jira backlog, not updated on new commits.
  Detailed analysis/spike write-ups that used to go in GitHub Issue
  descriptions now go in Confluence pages in the same space instead.

## Key Endpoints

- `GET /` - Main digest page
- `GET /api/refresh` - Trigger manual refresh of videos
- `GET /api/videos` - JSON endpoint for video list with summaries
