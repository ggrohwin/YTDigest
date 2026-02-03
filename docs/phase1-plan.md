# YTDigest Phase 1: Digest MVP

## Goal
Build a functional daily digest that fetches new videos from specified YouTube channels, retrieves transcripts, generates summaries via Claude API, and displays them in a local web interface.

## Tech Stack
- **Language**: Python 3.11+
- **Web framework**: FastAPI + Uvicorn
- **LLM**: Claude API (Anthropic)
- **Database**: SQLite (simple, no setup required)
- **Frontend**: HTML + Tailwind CSS (via CDN) + vanilla JS

## Project Structure
```
YTDigest/
├── CLAUDE.md
├── config.yaml              # Channel list, preferences
├── .env                     # API keys (gitignored)
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── youtube.py           # YouTube API client
│   ├── transcripts.py       # Transcript fetching
│   ├── summarizer.py        # Claude API summarization
│   ├── database.py          # SQLite operations
│   └── models.py            # Pydantic models
├── templates/
│   └── digest.html          # Jinja2 template for digest view
└── data/
    └── ytdigest.db          # SQLite database (gitignored)
```

## Configuration

### config.yaml
```yaml
channels:
  - id: "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # Google Developers
    name: "Google Developers"
  - id: "UCVHFbqXqoYvEWM1Ddxl0QKg"
    name: "Another Channel"

digest:
  max_videos_per_channel: 5
  max_age_days: 7
```

### .env
```
YOUTUBE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

## Implementation Steps

### Step 1: Project Setup
- Create directory structure
- Create `requirements.txt` with dependencies:
  - fastapi, uvicorn, jinja2
  - anthropic
  - google-api-python-client
  - youtube-transcript-api
  - python-dotenv, pyyaml
  - aiosqlite (async SQLite)
- Create `.env.example` and `.gitignore`
- Create starter `config.yaml`

### Step 2: Database Layer (`database.py`)
SQLite schema:
- **videos**: id, channel_id, channel_name, title, published_at, thumbnail_url, video_url
- **transcripts**: video_id, content, fetched_at
- **summaries**: video_id, summary, generated_at

Functions:
- `init_db()` - Create tables if not exist
- `save_video()`, `get_video()`, `get_videos_since()`
- `save_transcript()`, `get_transcript()`
- `save_summary()`, `get_summary()`

### Step 3: YouTube API Client (`youtube.py`)
- Load API key from environment
- `get_channel_uploads(channel_id, max_results, published_after)` - Fetch recent videos
- `get_video_details(video_ids)` - Get metadata for multiple videos
- Return Pydantic models for type safety

### Step 4: Transcript Fetcher (`transcripts.py`)
- `fetch_transcript(video_id)` - Returns transcript text or None
- Handle videos without transcripts gracefully
- Combine transcript segments into single text

### Step 5: Summarizer (`summarizer.py`)
- Initialize Anthropic client
- `summarize_video(title, channel, transcript)` - Returns summary
- Prompt engineering: Request concise summary (2-3 paragraphs) that helps decide if video is worth watching
- Include key topics covered

### Step 6: FastAPI App (`main.py`)
Routes:
- `GET /` - Render digest page
- `GET /api/refresh` - Trigger fetch of new videos (manual refresh)
- `GET /api/videos` - JSON endpoint for video list with summaries

On startup:
- Initialize database
- Load config

### Step 7: Frontend (`templates/digest.html`)
- Clean, scannable layout
- Video cards showing:
  - Thumbnail
  - Title (linked to YouTube)
  - Channel name
  - Published date
  - Summary
  - Topic tags (extracted by summarizer)
- Manual refresh button
- Loading states

## YouTube API Setup Instructions

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "YTDigest")
3. Enable the "YouTube Data API v3":
   - Go to APIs & Services > Library
   - Search for "YouTube Data API v3"
   - Click Enable
4. Create credentials:
   - Go to APIs & Services > Credentials
   - Click "Create Credentials" > "API Key"
   - Copy the key to your `.env` file
5. (Optional) Restrict the key to YouTube Data API only for security

## Verification

After implementation, test end-to-end:
1. `pip install -r requirements.txt`
2. Configure `.env` with both API keys
3. Add at least one channel to `config.yaml`
4. Run: `uvicorn src.main:app --reload`
5. Open `http://localhost:8000`
6. Click refresh, verify:
   - Videos appear from configured channels
   - Transcripts are fetched (check logs for any failures)
   - Summaries are generated and displayed
   - Links to YouTube work

## Out of Scope (Phase 2)
- Feedback buttons (thumbs up/down)
- Topic weighting and embeddings
- Analytics view
- Scheduled automatic refresh
