# YTDigest Roadmap

## How We Work

This project uses a lightweight Agile approach. Key concepts:

- **Epic** — a large initiative spanning multiple sessions (e.g. "Deploy to the public internet"). Epics contain ordered steps; each step is a story.
- **Story** — one unit of deliverable work, framed from the user's perspective: *"As a user, I want X so that Y."* Keeps focus on value, not just tasks.
- **Backlog** — the prioritized list of stories below. Items flow: **Now → Next → Later → Maybe → Completed**.
- **Sprint** — what we commit to finishing in a session or week. The **Now** column is the active sprint.
- **Definition of Done** — a story is done when it's implemented, manually verified in the app, and committed.

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

**Known limitations (Issue #6):** directional merge bug (more-specific tag can win over more-general); `topics_retag` column needed to preserve retag output across normalize runs; display threshold not yet implemented.

**Learning angles:** embedding similarity, cosine distance, semantic search, prompt engineering for structured output, evaluation-driven development, specification gaming.

---

## Feature Backlog

### Now
_Empty — finish Epic 2 first_

### Next
| Story | Description | Effort |
|-------|-------------|--------|
| Filter/sort videos | As a user, I want to filter by topic/channel/date rather than rearranging the entire page, so I can drill into what I care about | Medium |

### Later
| Story | Description | Effort |
|-------|-------------|--------|
| Mobile-friendly UI | As a user on my phone, I want a responsive layout so I can read my digest anywhere | Medium |
| Progress dashboard | As a user, I want to see engagement metrics (videos watched, articles read, minutes) so I can understand my consumption habits | Medium |
| Proxy for transcripts | As a user, I want transcripts fetched via a rotating proxy so my account isn't at risk of being banned | Medium |
| Retry failed transcripts | As a user, I want a one-click retry for failed transcripts so I don't lose content permanently | Quick |

### Maybe
| Story | Description | Effort |
|-------|-------------|--------|
| Local timezone support | As a user, I want dates in my local timezone so "added yesterday" is accurate | Quick |
| Live updates via SSE | As a user, I want the page to update automatically when new summaries arrive so I don't have to refresh | Medium |
| MCP server: video database | As a Claude Code user, I want to query my video library conversationally via MCP so I can explore content without opening the browser | Medium |
| MCP client: YouTube API | As a developer, I want YouTube querying wrapped as an MCP server so it's reusable across projects | Medium |
| Email digest | As a user, I want a daily email summary so I can read my digest without opening the app | Medium |

---

## Infrastructure & DevOps Backlog

### Next
| Story | Description | Effort |
|-------|-------------|--------|
| Pin dependencies | As a developer, I want pinned versions in requirements.txt so installs are reproducible | Quick |

### Later
| Story | Description | Effort |
|-------|-------------|--------|
| Type checking | As a developer, I want mypy enforced so type errors are caught before runtime | Medium |
| Feature branches | As a developer, I want a branch-based Git workflow so experiments don't touch master | Quick |

---

## Career Track

**Goal:** Apply AI skills commercially in AI application and adoption — targeting roles such as AI Adoption Consultant, AI Solutions Architect, or AI Product Manager.

**Structure:** Each sprint should have both a feature goal and a learning objective. At the end of each session, Claude will summarize the skill practiced and its commercial relevance.

**Skills demonstrated so far (evidence from this project):**
- Requirements precision — articulating tagging principles that a model can follow
- Evaluation instinct — spotting bad model outputs and diagnosing root causes
- System thinking — recognizing patterns across many examples and finding general principles
- Stakeholder thinking — consistently reasoning from the reader/user perspective, not the implementation perspective
- Prompt engineering — iterating prompts at the right level of abstraction

**Learning path toward commercial AI roles:**

| Stage | Focus | Project Vehicle | Commercial Value | Status |
|-------|-------|----------------|-----------------|--------|
| 1 | Prompt engineering & model behavior | Tag normalization | Diagnose and fix LLM output problems | In Progress |
| 2 | Context engineering & RAG | Improve semantic search | Design information retrieval pipelines | Pending |
| 3 | AI evaluation & testing | Build eval framework for summaries | Rare, high-value skill — measuring whether AI is working | Pending |
| 4 | AI system architecture | Multi-model pipeline (fast+smart layering) | Design production AI systems | Pending |
| 5 | Adoption & change management | Document YTDigest as a case study | Advise organizations on AI adoption | Pending |

---

## Learning Track

Topics to explore for deeper understanding. Claude will proactively suggest new entries and flag when a learning topic should take priority over feature work.

### Suggested (my recommendations)
| Topic | Why Now | Learning Angle |
|-------|---------|----------------|
| Postgres + Alembic migrations | Next logical step in the DevOps epic; SQLite limitations will become real when deploying | Schema versioning, connection pooling, migration safety |
| Agile story writing | We just introduced it — practice framing the next 3 features as proper user stories | Value-driven thinking, acceptance criteria |
| Embedding distance and clustering | Tag normalization exposed the limits of cosine similarity for short phrases | When embeddings work well vs. poorly; t-SNE visualization |
| Python async patterns | The app uses asyncio heavily but some patterns (background tasks, semaphores) haven't been fully explained | Concurrency vs. parallelism, event loops |
| Prompt engineering as specification | Tag normalization revealed that models optimize for literal instructions, not intent — a general challenge in AI app development | Diagnosing model/human assumption mismatches; framing prompts around outcomes rather than rules; iterating at the right level of abstraction |
| General-purpose vs. fine-tuned embeddings | Tag normalization exposed that Voyage AI's general embeddings don't enforce canonical terminology — `Prompt Engineering` and `Prompting Techniques` aren't close enough to merge | When general-purpose embeddings are sufficient vs. when domain adaptation is needed; few-shot prompting as a lightweight alternative to fine-tuning |
| Cheap-fast vs. smart-slow model layering | Tag normalization revealed that embeddings can't catch real-world distinctions (`Google` vs `Google Gemini`) but Claude can — at higher cost | Using fast/cheap models for bulk work and capable models as a validation layer; a common pattern in production AI systems |

### To Explore
| Topic | Context | Resources |
|-------|---------|-----------|
| Separation of concerns | Arose when adding grouping logic — where should presentation vs. business logic live? | |
| Testing with mocks | How to test code that calls external APIs without making real requests | |

### Explored
| Topic | Date | Notes |
|-------|------|-------|
| pytest fixtures and mocking | 2026-02 | Covered in learnings-pytest.md |
| Docker and CI/CD | 2026-02 | Completed the DevOps epic steps 1-2 |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
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
