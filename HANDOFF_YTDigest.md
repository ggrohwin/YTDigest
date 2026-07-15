# YTDigest — Technical Handoff

This document is intended for an AI assistant (or developer) picking up this project cold. It covers architecture, key decisions, working state, unfinished work, and hard problems that were solved. Where I'm inferring from code rather than verified by direct testing, I say so.

---

## What This Is

A personal daily digest app. It fetches recent videos from a configured list of YouTube channels, retrieves transcripts, generates AI summaries via the Claude API, and presents them in a local web UI. It also supports web articles (via URL or bookmarklet), semantic search with Voyage AI embeddings, and multi-turn chat about individual transcripts/articles.

It is a **single-user personal tool**, not a multi-tenant service. That constraint has driven most architectural decisions.

---

## Architecture Overview

```
config.yaml          .env
     |                 |
  AppConfig        API keys (YouTube, Anthropic, Voyage)
     |
src/main.py  ─── FastAPI app (Jinja2 + JSON endpoints)
     |
     ├── Two asyncio background tasks (started at lifespan):
     │     ├── background_transcript_fetcher()  — polls pending transcripts, adds jitter
     │     └── background_video_fetcher()       — refreshes channel metadata hourly
     │
     ├── src/youtube.py       — YouTube Data API v3 client (sync, google-api-python-client)
     ├── src/transcripts.py   — youtube-transcript-api fetcher
     ├── src/summarizer.py    — Claude API calls (summarize, chat, RAG answer)
     ├── src/embedder.py      — Voyage AI embeddings + cosine similarity search
     ├── src/database.py      — aiosqlite layer (no ORM)
     ├── src/models.py        — Pydantic models
     ├── src/tag_normalizer.py — structural tag deduplication
     ├── src/tagging_rules.py — TAGGING_PRINCIPLES constant (single source of truth)
     └── src/articles.py      — trafilatura-based web article extractor
```

**Runtime stack:** Python 3.11, FastAPI, uvicorn (single worker — multiple workers would duplicate background tasks), aiosqlite, SQLite at `data/ytdigest.db`.

**Templates:** Jinja2 server-rendered HTML at `templates/digest.html`. No frontend framework. All interactivity is vanilla JS with `fetch()` calls.

**Deployment:** Dockerized (`Dockerfile` + `docker-compose.yml`). CI via GitHub Actions (lint → test → docker build). Currently local-only; cloud deployment is planned but not done.

---

## Key Technical Decisions

### 1. SQLite over Postgres
**Why:** Personal single-user app with low write concurrency. SQLite is zero-config and the DB file is the entire persistence layer. **Debt:** Migration to Postgres is the next planned sprint (Epic 1, Step 3) because SQLite won't survive containerized cloud deployment properly. Schema migrations are currently a liability — see below.

### 2. No ORM — raw aiosqlite
**Why:** Lighter weight, no abstraction mismatch to debug. The DB schema is simple enough that hand-written SQL is readable. **Debt:** Schema is evolved via inline `try/except ALTER TABLE` in `init_db()` (see `src/database.py:39–192`). This is brittle — it works for additive changes but can't handle renames, drops, or re-ordering. Alembic migration is planned when Postgres is introduced.

### 3. Background tasks as asyncio.create_task (not Celery/RQ)
**Why:** The app is single-process, and asyncio tasks are sufficient for two simple polling loops. Using Celery would require Redis and a separate worker process — overkill for a personal app. **Constraint:** uvicorn must run with a single worker (`--workers` flag absent from CMD). Multiple workers would each start their own background tasks, causing duplicate transcript fetches and API charges.

### 4. Single worker + jitter on transcript fetcher
The `background_transcript_fetcher()` adds random jitter of -60 to +120 seconds per cycle to appear less bot-like to YouTube's transcript API (`src/main.py:269`). This was added after encountering rate-limit behavior. *Inferred: I haven't seen a specific incident documented, but the jitter and comment make the reason clear.*

### 5. Content truncated at 100k chars rather than chunked for summarization
`summarize_content()` truncates transcripts/articles to 100,000 characters before sending to Claude (`src/summarizer.py:38–71`). This is a pragmatic ceiling — Claude's context window can handle it, and most transcripts are well under. Chunk-level embeddings exist for search, but summarization is always whole-document.

### 6. Two embedding levels (summary + chunks)
The `embeddings` table stores both summary-level vectors (`video_summary`, `article_summary`) and chunk-level vectors (`video_chunk`, `article_chunk`). Search uses summary embeddings to find relevant items, then loads full content for the RAG answer. Chunk embeddings exist for future more granular retrieval (the `feature/chunked-rag` branch explores this).

### 7. Chat: content in system prompt
`chat_with_content()` passes the transcript/article as a system message, keeping it constant across turns (`src/summarizer.py:230–278`). This is intentional — the content token cost is paid once and cached by the Anthropic API, rather than being repeated in each user turn. **Debt:** Multi-turn chat state is managed client-side (the frontend sends the full message history). Server-side state management with summarization of older turns is in the backlog.

### 8. DigestItem as unified model
Videos and articles are different DB tables with different schemas, but the UI treats them identically. `DigestItem` in `src/models.py:111` is a union model with optional fields for each type. `get_digest_items()` in `main.py:1235` assembles both types into a single sorted list. This is clean for the UI but means some fields are always `None` depending on item type — not enforced by the type system.

### 9. Tag normalizer singleton
`TagNormalizer` is initialized at app startup with all existing tags from the DB, builds a canonical tag cache, and normalizes new tags against it (`src/summarizer.py:15–35`). It's a module-level global, which is fine for a single-worker app. **Known limitation:** Tag bloat is still significant despite this — 71% of tags are singletons. A fundamental rethink (constrained vocab, embeddings-based normalization) is tracked in Issue #6.

### 10. Summarizer as single source of truth
`summarize_content()` handles both videos and articles via a `content_type` parameter. The tagging rules live in `src/tagging_rules.py` and are imported by both the real-time summarizer and any batch retag scripts. This was refactored in commit `fadb281` to eliminate a prior duplication where video and article summarizers had diverged.

---

## What's Working

- **Core pipeline:** fetch videos → fetch transcripts (background, with jitter) → summarize via Claude → display in UI. Fully functional.
- **Web articles:** Add by URL or bookmarklet. Extracted via trafilatura, summarized the same way as videos.
- **RAG / conversational search:** Ask questions across the library. Voyage AI retrieves top-5 relevant items by cosine similarity; Claude synthesizes an answer with source citations.
- **Chat with transcript:** Multi-turn conversation about a single video or article. Content in system prompt.
- **Engagement tracking:** Mark items complete (like/neutral/dislike/skip). Today's stats shown in the header (videos watched, minutes, words read).
- **Favorites:** Star/unstar any item.
- **Notes:** Per-item personal notes, stored in DB.
- **Shorts filtering:** Per-channel `filter_shorts` flag with configurable duration threshold.
- **Topic tag navigation:** Group by topic, channel, or date. Sidebar with hierarchy.
- **YouTube MCP server:** `mcp_servers/youtube_server.py` — FastMCP server exposing channel, metadata, and transcript tools to Claude Desktop. Registered in Claude Desktop config. *I'm inferring the Desktop registration works since the commit notes say so; I haven't verified the Claude Desktop config file.*
- **CI/CD:** GitHub Actions — lint (ruff), test (pytest, 192 tests), docker build. Runs on push/PR to master.
- **Docker:** `Dockerfile` + `docker-compose.yml`. Mounts `./data`, `./logs`, `./config.yaml` as volumes. Runs as non-root `appuser`.

---

## What's Unfinished

### Epic 1: Publish to the Public Internet (Steps 3–5 pending)
| Step | What | Status |
|------|------|--------|
| 3 | Migrate SQLite → Postgres with Alembic | Not started |
| 4 | Basic authentication | Not started |
| 5 | Deploy to public URL (Railway planned) | Not started |

**Current blocker:** The DB is SQLite. Postgres migration requires adding `asyncpg`/`psycopg`, writing Alembic migrations for the existing schema, and updating Docker Compose to add a Postgres service.

### Schema migrations
`init_db()` uses `try/except ALTER TABLE` for every column added after initial creation. This pattern cannot handle renames, drops, or column reordering. It also runs on every startup, which is slow and noisy. Alembic is the fix, but it's coupled to the Postgres migration.

### Tag quality
Despite structural normalization and prompt engineering, 71% of tags are singletons. The `TagNormalizer` catches exact duplicates and simple case/whitespace variants, but semantic duplicates ("AI Agents" vs "Agentic Systems") slip through. The `feature/chunked-rag` branch has a spike exploring embedding-based normalization.

### Server-side chat state
Multi-turn chat history is managed client-side — the frontend sends the full conversation on every request. For long conversations this grows unbounded. Summarizing older turns server-side would reduce token costs. Tracked in backlog.

### `feature/chunked-rag` branch (open, not merged)
4 commits not in master. Contains a spike evaluating question-focused summaries for conversational search (Issue #10), plus some unrelated fixes that should probably have gone to master separately. Status: exploratory, no decision made.

---

## Hardest Problems Solved

### 1. SQLite UNIQUE constraint and NULL chunk_index
SQLite treats `NULL != NULL` for UNIQUE constraint matching, so `INSERT OR REPLACE` would silently create duplicate rows when `chunk_index IS NULL` (summary embeddings). The fix: explicit `DELETE` before `INSERT` using `IS NULL` in the WHERE clause (`src/database.py:965–994`). This is subtle and easy to break if you switch to `INSERT OR REPLACE` thinking it's equivalent.

### 2. YouTube rate limiting without a queue
The app can't use a job queue (Celery, etc.) without adding infrastructure. The solution is a polling background task with per-cycle jitter and a `priority` status that lets the user front-queue a specific video. The `transcript_status` field has five values (`pending`, `fetched`, `failed`, `unavailable`, `priority`) and the query in `get_videos_without_transcripts()` orders by priority first (`src/database.py:502–515`).

### 3. Proxy/certificate issues with article fetching
`fetch_article` had to be switched from `urllib` to `requests.get` to honour `REQUESTS_CA_BUNDLE` — the corporate proxy cert environment variable. Fixed in commit `ef140fc`. If you're running behind a corporate proxy, this matters. *Inferred context from commit message and the fact that the fix targets a specific env var.*

### 4. Chat content token efficiency
The naive implementation would re-send the full transcript on every chat turn. Using the system prompt keeps the content pinned and allows the Anthropic API's prompt caching to amortize the cost. The system prompt is assembled fresh each request but is structurally identical across turns for the same item, which is what the cache key matches on.

### 5. Windows Smart App Control blocking pre-commit
The pre-commit hook was configured to use `black`, which pre-commit downloads into its own isolated environment. Windows Smart App Control blocked the freshly-downloaded `black` binary as untrusted. Solved by switching to `ruff-format` for formatting (commit `7376b21`) — ruff is already installed and trusted. The CI workflow was updated to match (`ruff format --check` instead of `black --check`).

---

## Five Questions a Skeptical Technical Interviewer Would Ask

**1. Your `init_db()` runs `ALTER TABLE` on every startup. What happens when two instances start simultaneously in production?**
Both instances race to add columns that already exist. The `try/except` silently swallows the error from the second instance, so it works — but only because SQLite's default locking serializes the writes. In Postgres with concurrent app instances this pattern would fail under load. The real answer is Alembic with a migration lock table, which is the planned fix.

**2. You store embedding vectors as BLOBs in SQLite and do cosine similarity in Python. At what scale does this break, and what would you do about it?**
Cosine similarity is computed by loading all vectors into memory and doing a numpy dot product. At a few thousand embeddings this is fast. At tens of thousands it becomes a memory and latency issue. The fix is a dedicated vector store (pgvector for Postgres, or a hosted service like Pinecone/Weaviate). For YTDigest's actual scale (hundreds of items), this is not a real problem today.

**3. Your RAG endpoint loads full transcript content for each retrieved item after embedding search. What's the token cost worst case, and how does it blow up?**
`answer_question()` retrieves 5 items and passes each full transcript (up to 100k chars each) into the context. Worst case is 5 × 100k = 500k characters, which is several hundred thousand tokens. At Claude's pricing this could be a meaningful per-query cost. The fix is to use chunk-level retrieval — retrieve the specific chunks that matched rather than the full transcript. The chunk embeddings exist; the retrieval path hasn't been updated to use them yet.

**4. CORS is configured with `allow_origins=["*"]`. Why, and what's the risk?**
The bookmarklet feature POSTs from arbitrary domains (wherever the user is browsing), so wildcard CORS is intentional. The risk: any website the user visits can make authenticated requests to the app — but since there's no auth yet, there's nothing to protect. When auth is added this must be tightened to a specific origin or the bookmarklet flow needs to be rethought (e.g., a separate unauthenticated endpoint).

**5. The background transcript fetcher catches all exceptions and continues running. What class of bugs does that hide?**
Any bug that throws an exception inside the loop is silently logged and the loop continues. This means a recurring error (e.g., a DB corruption, an API key expiry) will fill the logs but never stop the app or alert anyone. The right fix is a dead-man's-switch: if the fetcher fails N times in a row, stop it and expose a health endpoint that returns unhealthy. Currently there is no health endpoint.

---

## Files You Need to Know

| File | Why it matters |
|------|----------------|
| [src/main.py](src/main.py) | All FastAPI routes + background tasks + startup logic |
| [src/database.py](src/database.py) | All DB operations — the schema lives here implicitly |
| [src/summarizer.py](src/summarizer.py) | All Claude API calls |
| [src/models.py](src/models.py) | Pydantic models — `DigestItem` is the key abstraction |
| [src/tagging_rules.py](src/tagging_rules.py) | Single source of truth for tag generation rules |
| [config.yaml](config.yaml) | Channel list + digest settings (editable without rebuild) |
| [.env](/.env) | API keys — not in git, must be provided manually |
| [ROADMAP.md](ROADMAP.md) | Epics, active sprint, backlog — start here for what's next |
