# YTDigest Roadmap

## How We Work

This project uses a lightweight Agile approach. Key concepts:

- **Epic** — a large initiative spanning multiple sessions (e.g. "Deploy to the public internet"). Epics contain ordered steps; each step is a story. Backlog items may be promoted to epics during sprint planning when they turn out to have multiple independently deliverable pieces.
- **Story** — one unit of deliverable work, framed from the user's perspective: *"As a user, I want X so that Y."* Keeps focus on value, not just tasks.
- **Spike** — a time-boxed investigation story. The deliverable is a *decision* backed by evidence, not working software. Use spikes when an approach has significant uncertainty — try it cheaply on a small sample before committing to a full implementation. Spikes have a hard time limit; when it expires, stop and report what you learned.
- **Backlog** — the prioritized list of stories below. Items flow: **Now → Next → Later → Maybe → Completed**.
- **Sprint** — a time-boxed commitment (typically one session). Has a goal, a set of stories, and a status. A sprint is a unit of execution — it may produce code, a decision, a process change, or an evaluation. The active sprint is documented in its own section below. When a sprint ends, its stories move to Completed and a new sprint is started.
- **Sprint planning** — at the start of each sprint, review the backlog and pick a goal. If a story has significant uncertainty ("I'm not sure this will work"), make it a spike first rather than committing to full implementation. Define exit criteria upfront for exploratory work. **No execution begins until both sides explicitly agree on the sprint contents.**
- **Sprint discipline** — new ideas or issues discovered mid-sprint go into the backlog, not into the current sprint, unless they block the sprint goal.
- **GitHub Issues** — used to capture detailed context behind deferred work or known limitations. A backlog item stays concise; the linked issue holds the specifics (root causes, edge cases, open questions). Not every backlog item needs an issue — only those with enough detail to warrant one.
- **Retrospective** — at the end of each sprint, reflect on what went well, what didn't, and what to change. This is how the process improves over time.
- **Definition of Done** — a story is done when it's implemented, manually verified in the app, and committed. A spike is done when the timebox expires and the decision is documented.

I (Claude) will suggest new stories and learning angles based on where the project is heading. You decide what goes into the sprint.

---

## Epics

### 1. Publish to the Public Internet
_Status: Later_

Deploy YTDigest to a public URL, accessible from anywhere. This epic teaches the full production stack: containerization → database migration → auth → cloud deployment.

| Step | Story | Effort | Status |
|------|-------|--------|--------|
| 1 | As a developer, I want the app in a Docker container so it runs identically anywhere | Medium | Done |
| 2 | As a developer, I want CI/CD so that tests and builds run automatically on every push | Medium | Done |
| 3 | As a developer, I want Postgres instead of SQLite so the database can scale and be managed properly | Medium | Pending |
| 4 | As a user, I want basic authentication so that only I can access my public instance | Medium | Pending |
| 5 | As a user, I want the app deployed to a public URL with HTTPS and persistent storage | Medium | Pending |

**Learning angles:** environment management, secrets handling, Alembic migrations, connection pooling, platform-as-a-service deployment.

---

### 2. Refine Topic Tags
_Status: Done (v1) — follow-up work tracked in Issue #6_

Make topic-based navigation actually useful by reducing tag bloat and improving consistency.

| Step | Story | Effort | Status |
|------|-------|--------|--------|
| 1 | As a user, I want case-insensitive tag grouping so "Workflow Automation" and "workflow automation" don't appear as separate groups | Quick | Done |
| 2 | As a user, I want existing tags retroactively cleaned up using tagging principles so navigation is immediately better | Medium | Done (v1) |
| 3 | As a user, I want new video tags normalized against existing ones so tag bloat doesn't grow back | Medium | Done (structural rules; embeddings deferred) |
| 4 | As a user, I want a display threshold that hides single-occurrence tags from navigation so the sidebar isn't overwhelming | Quick | Deferred to Issue #6 |
| 5 | As a developer, I want tagging principles encoded in the summarizer prompt so Claude generates better tags going forward | Quick | Done |

**Known limitations (Issue #6):** 71% singletons despite structural normalization + prompt retagging; directional merge bug; `topics_retag` column needed; display threshold not implemented. Tagging approach needs fundamental rethinking (constrained vocab, embeddings, or different strategy entirely).

**Learning angles:** embedding similarity, cosine distance, semantic search, prompt engineering for structured output, evaluation-driven development, specification gaming.

---

### 3. Content Discovery
_Status: Done (v1) — follow-up items in backlog_

Help users find content that matches their interests across the entire digest, whether they know exactly what they're looking for or not.

| Step | Story | Effort | Status |
|------|-------|--------|--------|
| 1 | As a user, I want page controls always accessible so I don't lose them when scrolling | Quick | Done |
| 2 | As a user, I want tags on cards to link to related content so I can discover connections while reading | Quick | Done (pre-existing) |
| 3 | As a user, I want to ask questions across all my summaries so I can find and explore content conversationally | Medium | Done (v1) |

**Learning angles:** RAG, context engineering, prompt design for retrieval, chunking strategies.

---

## Active Sprint

_No active sprint. Next sprint to be planned from the backlog._

---

## Backlog

### Next
| Story | Type | Description | Effort |
|-------|------|-------------|--------|
_(empty)_

### Later
| Story | Type | Description | Effort |
|-------|------|-------------|--------|
| Server-side chat state management | Refactor | As a developer, I want multi-turn chat state managed server-side so I can summarize older turns and reduce token costs | Medium |
| Mobile-friendly UI | Feature | As a user on my phone, I want a responsive layout so I can read my digest anywhere | Medium |
| Progress dashboard | Feature | As a user, I want to see engagement metrics (videos watched, articles read, minutes) so I can understand my consumption habits | Medium |
| Proxy for transcripts | Infra | As a user, I want transcripts fetched via a rotating proxy so my account isn't at risk of being banned | Medium |
| Retry failed transcripts | Feature | As a user, I want a one-click retry for failed transcripts so I don't lose content permanently | Quick |
| Type checking | Infra | As a developer, I want mypy enforced so type errors are caught before runtime | Medium |

### Maybe
| Story | Type | Description | Effort |
|-------|------|-------------|--------|
| Claude Code skills & hooks | Learning | As a developer, I want to understand Claude Code's skills, hooks, and settings configuration so I can customize my workflow | Quick |
| Local timezone support | Feature | As a user, I want dates in my local timezone so "added yesterday" is accurate | Quick |
| Live updates via SSE | Feature | As a user, I want the page to update automatically when new summaries arrive so I don't have to refresh | Medium |
| MCP server: video database | Feature | As a Claude Code user, I want to query my video library conversationally via MCP so I can explore content without opening the browser | Medium |
| MCP client: YouTube API | Infra | As a developer, I want YouTube querying wrapped as an MCP server so it's reusable across projects | Medium |
| Email digest | Feature | As a user, I want a daily email summary so I can read my digest without opening the app | Medium |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Summarizer single source of truth (Sprint) | 2026-03-28 | Consolidated `summarize_video`/`summarize_article` into `summarize_content`; wired up `TAGGING_PRINCIPLES` from `tagging_rules.py` into summarizer and retag script |
| Clear question input | 2026-03-28 | X button in Ask input field; appears when text is present |
| Source card actions | 2026-03-28 | Search result cards now have full digest actions: complete, chat, notes, favorite |
| Answer markdown formatting | 2026-03-28 | Added Tailwind Typography plugin; prose classes now render headers, lists, code blocks properly |
| Clickable tags on cards (Content Discovery Story 2) | 2026-03-25 | Already implemented; confirmed working — links to topic group view |
| Sticky page controls (Content Discovery Story 1) | 2026-03-25 | Header, search, grouping controls stay visible when scrolling |
| Conversational search / RAG (Content Discovery Story 3) | 2026-03-25 | Ask questions across library; Claude synthesizes answers from retrieved content with source cards |
| Pin dependencies for reproducible builds | 2026-03-25 | Exact versions in requirements.txt; full lock file for Docker/CI |
| Tag validation & cleanup (Sprint 2) | 2026-03-24 | Consolidated tagging rules into shared module; validated tags in browser; concluded structural normalization has diminishing returns — needs rethinking |
| Filter YouTube Shorts from selected channels | 2026-03-07 | Per-channel `filter_shorts` flag + configurable `shorts_max_duration` threshold (default 120s) |
| Code formatting & pre-commit hooks | 2026-02-22 | black + ruff for formatting/linting, pre-commit hooks run both before every commit |
| CI/CD with GitHub Actions | 2026-02-22 | Two-job workflow: run pytest and build Docker image on every push/PR to master |
| Dockerize the app | 2026-02-22 | Dockerfile + Docker Compose with SQLite volume mount, non-root user, config editable without rebuilding |
| Add notes to digest entries | 2026-02-16 | Personal notes on any video or article card; stored in DB, displayed with amber indicator |
| Chat with transcript | 2026-02-16 | Multi-turn chat modal using Claude; system-prompt architecture keeps content constant across turns |
| Daily engagement tracking | 2026-02-11 | Skip sentiment to complete; today's stats in summary bar (watched, minutes, read, words, skipped) |
| Un-complete a digest item | 2026-02-11 | Undo button on completed cards |
| Log persistence | 2026-02-10 | RotatingFileHandler to logs/ytdigest.log (5 MB cap, 3 backups) |
| Configurable summarization model | 2026-02-09 | Moved hardcoded Claude model to config.yaml |
| Coverage reporting | 2026-02-09 | pytest-cov with terminal + HTML reports; 60% coverage, 188 tests passing |
| API endpoint tests | 2026-02-08 | 22 tests for 8 endpoints using httpx AsyncClient |
| Favorites list | 2026-02-08 | Star/unstar any item; dedicated favorites view |
| Push to GitHub | 2026-02-07 | Private repo; pushed master and feature branch, opened first PR |
| Clickable topic tags | 2026-02-07 | Topic labels in cards link to topic group view |
| Add video by URL | 2026-02-07 | Paste any YouTube URL or use bookmarklet; fetches metadata, transcript, and summary |
| Semantic search | 2026-02-07 | Voyage AI embeddings; cosine similarity search with deduplication and threshold filtering |
| Web articles feature | 2026-02-06 | Extract, summarize, and display web articles alongside videos |
| Integration tests | 2026-02-06 | End-to-end tests for article pipeline |
| Video completion with sentiment | 2026-02-04 | Mark videos done with like/neutral/dislike |
| Navigation sidebar | 2026-02-04 | Sidebar with groupings, scroll spy, collapsible sections |
| Group videos | 2026-02-03 | Group by date, channel, or topic with collapsible sections |
| Background transcript fetcher | 2026-02-02 | Avoids rate limiting with configurable interval |
| Unit testing | 2026-02-02 | pytest with HTML reports |
| Initial MVP | 2026-02-02 | Fetch videos, transcripts, summaries; display in web UI |
