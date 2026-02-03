# YTDigest

A daily digest application that fetches new videos from specified YouTube channels, retrieves transcripts, generates AI summaries via Claude API, and displays them in a local web interface.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API keys
cp .env.example .env

# Edit config.yaml to add your preferred YouTube channels

# Run the app
uvicorn src.main:app --reload
```

Open http://localhost:8000 in your browser.

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

## Key Endpoints

- `GET /` - Main digest page
- `GET /api/refresh` - Trigger manual refresh of videos
- `GET /api/videos` - JSON endpoint for video list with summaries
