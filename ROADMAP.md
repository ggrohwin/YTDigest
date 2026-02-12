# YTDigest Roadmap

## Priority Tiers

- **Now**: Currently working on or next up
- **Next**: Planned for near-term
- **Later**: Good ideas, not urgent
- **Maybe**: Exploring, not committed

---

## Features

### Now
| Item | Description | Effort |
|------|-------------|--------|

### Next
| Item | Description | Effort |
|------|-------------|--------|
| Filter/sort videos | Rethink grouping vs. filtering: currently Date/Source/Topic regroup the entire page, but clicking a specific date, source, or topic should probably filter to just those items (not rearrange everything). All three criteria should behave consistently. Include show/hide completed in filtered views. Also: sort options, filter by has-summary, video length, etc. | Medium |
| Add notes to digest entries | Let users add personal notes to any video or article card; stored in DB, displayed on the card | Medium |
| Daily engagement tracking | Track daily completions and engagement with digest items; streak counter, daily goal, progress dashboard to build a consistent habit | Medium |
| Local timezone support | All dates display in UTC; items added in the evening show as the next day. Add a timezone setting (config.yaml or UI) and convert dates to local time before display. | Quick |
| Refine topic tags | Too many unique topics make tag grouping unusable for navigation; consolidate to a controlled set or merge similar tags. Case-insensitive grouping needed (e.g. "Workflow Automation" vs "workflow automation" are separate groups — fix in `group_items` by normalizing keys to lowercase) | Medium |
| Chat with transcript | Ask questions about a video while watching; send transcript + question to Claude | Medium |

### Later
| Item | Description | Effort |
|------|-------------|--------|
| Search across transcripts | Keyword search across all saved transcripts | Medium |
| Proxy for transcripts | Replace cookies auth (risks account ban) with rotating proxy for youtube-transcript-api. Two options: **Webshare** (library's built-in `WebshareProxyConfig`, paid residential rotating proxies) or **Generic proxy** (`GenericProxyConfig` with any HTTPS proxy provider). Credentials via `.env`. | Medium |
| Retry failed transcripts | Button or automatic retry for rate-limited videos after cooldown | Quick |

### Maybe
| Item | Description | Effort |
|------|-------------|--------|
| Publish to public internet | Deploy to a public URL with auth, DB migration (SQLite→Postgres), secrets management, HTTPS | Large |
| Mobile-friendly UI | Responsive design improvements | Medium |
| Live updates via SSE | Server-Sent Events to push transcript/summary completion to the browser in real time | Medium |
| Consolidate card templates | Article, video, and search result cards share duplicated layout; extract a Jinja macro or partial to render cards once with type-specific conditionals | Medium |

---

## Infrastructure & DevOps

### Now
_Empty - ready for next task_

### Next
| Item | Description | Effort |
|------|-------------|--------|
| Code formatting | Set up black + ruff for consistent style | Quick |
| Pre-commit hooks | Run formatter, linter, tests before commit | Quick |
| Dependency pinning | Lock versions in requirements.txt | Quick |

### Later
| Item | Description | Effort |
|------|-------------|--------|
| Type checking | Add mypy, fix type errors | Medium |
| Feature branches | Adopt branch-based workflow | Quick |
| Database migrations | Replace ad-hoc ALTER TABLE with Alembic | Medium |

### Maybe
| Item | Description | Effort |
|------|-------------|--------|
| CI/CD | GitHub Actions to run tests on push | Medium |
| Error monitoring | Sentry integration for production errors | Medium |
| Database backups | Scheduled backup script | Quick |
| Docker | Containerize for easy deployment | Medium |

---

## Testing

### Next
_Empty - ready for next task_

---

## Completed
| Item | Date | Notes |
|------|------|-------|
| Un-complete a digest item | 2026-02-11 | Undo button on completed cards to restore items to active status with sentiment buttons |
| Log persistence | 2026-02-10 | RotatingFileHandler writing to logs/ytdigest.log (5 MB cap, 3 backups); console logging unchanged |
| Configurable summarization model | 2026-02-09 | Moved hardcoded Claude model to config.yaml; extracted summarize_and_save_video() helper to deduplicate three call sites |
| Mark as read/interested | 2026-02-04 | Superseded by video completion with sentiment (like/neutral/dislike) |
| Coverage reporting | 2026-02-09 | pytest-cov with terminal + HTML reports; 60% overall coverage, 188 tests passing |
| API endpoint tests | 2026-02-08 | 22 tests for 8 HTTP endpoints using httpx AsyncClient + ASGITransport; shared conftest.py with test_db, test_client fixtures, and seed helpers |
| Favorites list | 2026-02-08 | Star/unstar any digest item; dedicated favorites view with sidebar link; optimistic UI with fade-out on unfavorite |
| Push to GitHub | 2026-02-07 | Private repo with gh CLI; pushed master and feature branch, opened first PR |
| Clickable topic tags | 2026-02-07 | Topic labels in cards link to topic group view |
| Fix add-video-by-URL bugs | 2026-02-07 | Fix bookmarklet regex for standard watch URLs; remove age filter from display queries; sort by date added instead of date published |
| Add video by URL | 2026-02-07 | Paste any YouTube URL in sidebar or use bookmarklet; fetches metadata, transcript, and summary synchronously |
| Semantic search | 2026-02-07 | Voyage AI embeddings for summaries + transcript/article chunks; cosine similarity search with deduplication, threshold filtering, auto-embed on save, search UI with score badges |
| Article thumbnails | 2026-02-07 | Extract OG image from trafilatura, store in DB, display in article cards matching video card layout |
| Article bookmarklet and paste-URL | 2026-02-06 | Draggable bookmarklet and sidebar URL input for saving articles to digest |
| Article title and date fixes | 2026-02-06 | Enable trafilatura metadata extraction; group articles by added_at, show original pub date |
| Web articles feature | 2026-02-06 | Extract, summarize, and display web articles alongside videos in unified digest |
| Integration tests | 2026-02-06 | End-to-end tests for article fetch-summarize pipeline with pytest integration marker |
| Mocking external APIs | 2026-02-06 | Mock trafilatura in unit tests; fixed for trafilatura 2.0 Document return type |
| Skip completed videos in transcript queue | 2026-02-04 | Exclude completed videos from background transcript fetching |
| Unified page summary bar | 2026-02-04 | Single status bar with video counts, new-since-last-visit, and transcript status; replaced startup banner |
| Prioritize transcript fetch | 2026-02-04 | Button to bump a video to the front of the transcript queue |
| Truncate summaries in cards | 2026-02-04 19:59:04 | Show first ~3 lines with show more/less toggle |
| Refine AI categories | 2026-02-04 19:29:29 | Category hierarchy for topic sidebar (LLMs, MLOps, etc.) |
| Navigation sidebar | 2026-02-04 19:29:29 | Sidebar with links to groupings, scroll spy, collapsible months/categories |
| Video completion with sentiment | 2026-02-04 17:42:21 | Mark videos done with like/neutral/dislike; show/hide completed |
| Startup fetch status banner | 2026-02-04 17:42:21 | Show fetch results on first page load after server start |
| Group videos | 2026-02-03 13:43:44 | Group by date, channel, or topic with collapsible sections |
| Distinguish unavailable vs failed transcripts | 2026-02-03 13:05:52 | Different UI messages based on failure type |
| Automatic video refresh | 2026-02-03 12:48:34 | Hourly background refresh + dismissable status message |
| Track transcript status | 2026-02-02 21:13:33 | Skip failed videos, added jitter to intervals |
| Background transcript fetcher | 2026-02-02 20:10:06 | Avoids rate limiting with configurable interval |
| Unit testing | 2026-02-02 19:32:47 | pytest with HTML reports |
| Initial MVP | 2026-02-02 19:10:42 | Fetch videos, transcripts, summaries; display in web UI |

---

## How to Use This Roadmap

1. **Add ideas**: Drop them in the appropriate "Maybe" section
2. **Prioritize**: Move items up to "Later" → "Next" → "Now" as needed
3. **Track completion**: Move finished items to "Completed" with date
4. **Estimate effort**: Quick (<1 hour), Medium (1-4 hours), Large (4+ hours)
