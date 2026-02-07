# YTDigest Roadmap

## Priority Tiers

- **Now**: Currently working on or next up
- **Next**: Planned for near-term
- **Later**: Good ideas, not urgent
- **Maybe**: Exploring, not committed

---

## Features

### Now
_Empty - ready for next task_

### Next
| Item | Description | Effort |
|------|-------------|--------|
| Chat with transcript | Ask questions about a video while watching; send transcript + question to Claude | Medium |
| Retry failed transcripts | Button or automatic retry for rate-limited videos after cooldown | Quick |

### Later
| Item | Description | Effort |
|------|-------------|--------|
| Filter/sort videos | Filter by channel, date, has-summary; sort options | Medium |
| ~~Mark as read/interested~~ | ~~Track which videos you've watched or want to watch~~ | ~~Medium~~ |
| Search across transcripts | Keyword search across all saved transcripts | Medium |
| Semantic search | Embed transcripts, query by meaning ("what did anyone say about fine-tuning?") | Large |

### Maybe
| Item | Description | Effort |
|------|-------------|--------|
| Email digest | Daily/weekly email summary of new videos | Medium |
| Mobile-friendly UI | Responsive design improvements | Medium |
| Export summaries | Export to markdown, PDF, or Notion | Quick |
| Multiple summary styles | Bullet points vs prose, length options | Quick |
| Live updates via SSE | Server-Sent Events to push transcript/summary completion to the browser in real time | Medium |

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
| Virtual environment | Document venv setup in README | Quick |
| Type checking | Add mypy, fix type errors | Medium |
| Feature branches | Adopt branch-based workflow | Quick |
| Database migrations | Replace ad-hoc ALTER TABLE with Alembic | Medium |

### Maybe
| Item | Description | Effort |
|------|-------------|--------|
| CI/CD | GitHub Actions to run tests on push | Medium |
| Error monitoring | Sentry integration for production errors | Medium |
| Log persistence | Write logs to file, rotation | Quick |
| Database backups | Scheduled backup script | Quick |
| Docker | Containerize for easy deployment | Medium |

---

## Testing

### Next
| Item | Description | Effort |
|------|-------------|--------|
| API endpoint tests | Test HTTP endpoints with FastAPI TestClient | Medium |
| Coverage reporting | Add pytest-cov, track coverage | Quick |

---

## Completed
| Item | Date | Notes |
|------|------|-------|
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
