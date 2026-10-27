# YTDigest API Endpoints

All 20 routes defined in `src/main.py`, in file order.

| Method | Path | Function | Purpose |
|---|---|---|---|
| GET | `/sentry-debug` | `trigger_sentry_error` | Deliberately raises `ZeroDivisionError` — Sentry setup verification route |
| GET | `/` | `index` | Renders the main digest page |
| GET | `/api/videos` | `api_videos` | Get all videos with summaries (JSON) |
| POST | `/api/videos` | `api_add_video` | Add a video by YouTube URL — fetches metadata, transcript, summary |
| GET | `/api/refresh` | `api_refresh` | Fetch new videos from all configured channels |
| POST | `/api/videos/{video_id}/complete` | `api_complete_video` | Mark a video completed, with sentiment |
| POST | `/api/videos/{video_id}/uncomplete` | `api_uncomplete_video` | Restore a video to active status |
| POST | `/api/videos/{video_id}/prioritize` | `api_prioritize_video` | Bump a video to the front of the transcript-fetch queue |
| POST | `/api/backfill-categories` | `api_backfill_categories` | Classify existing summaries missing a category |
| POST | `/api/embed-all` | `api_embed_all` | Generate embeddings for all items that need them |
| POST | `/api/ask` | `api_ask` | Answer a question via RAG over the library |
| POST | `/api/articles` | `api_add_article` | Add a web article by URL — extracts, saves, summarizes |
| POST | `/api/articles/{article_id}/complete` | `api_complete_article` | Mark an article completed, with sentiment |
| POST | `/api/articles/{article_id}/uncomplete` | `api_uncomplete_article` | Restore an article to active status |
| POST | `/api/chat` | `api_chat` | Multi-turn chat about a transcript/article |
| POST | `/api/videos/{video_id}/favorite` | `api_favorite_video` | Toggle a video's favorite status |
| POST | `/api/articles/{article_id}/favorite` | `api_favorite_article` | Toggle an article's favorite status |
| POST | `/api/videos/{video_id}/notes` | `api_save_video_notes` | Save notes on a video |
| POST | `/api/articles/{article_id}/notes` | `api_save_article_notes` | Save notes on an article |
| GET | `/api/articles` | `api_articles` | Get all articles with summaries (JSON) |

Note: `/sentry-debug` isn't listed in `CLAUDE.md`'s "Key Endpoints" section — it's a route added separately for Sentry verification, not part of the documented app surface.
