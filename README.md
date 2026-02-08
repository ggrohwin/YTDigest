# YTDigest

A personal digest app that fetches videos from YouTube channels, saves web articles, generates AI summaries, and provides semantic search — all in a local web interface.

## Features

- **YouTube digest** — Automatically fetches new videos from configured channels, retrieves transcripts, and generates summaries via Claude API
- **Web articles** — Save any web article via bookmarklet or URL paste; extracts content, summarizes, and displays alongside videos
- **Semantic search** — Find content by meaning using Voyage AI embeddings across summaries and full text
- **Add by URL** — Paste a YouTube or article URL to save and summarize immediately
- **Completion tracking** — Mark items as done with like/neutral/dislike sentiment

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

## API Keys Required

1. **YouTube Data API v3** — [Google Cloud Console](https://console.cloud.google.com/)
2. **Anthropic API** — [console.anthropic.com](https://console.anthropic.com/)
3. **Voyage AI** (optional, for semantic search) — [dash.voyageai.com](https://dash.voyageai.com/)

## Project Structure

```
src/
  main.py          FastAPI app and background tasks
  youtube.py       YouTube API client
  transcripts.py   Transcript fetching (youtube-transcript-api)
  summarizer.py    Claude API for summaries and categorization
  articles.py      Web article extraction (trafilatura)
  embedder.py      Voyage AI embeddings and search
  database.py      SQLite operations (aiosqlite)
  models.py        Pydantic models
templates/
  digest.html      Jinja2 web interface
config.yaml        Channel list and preferences
tests/             pytest test suite
```

## Running Tests

```bash
pytest tests/
```
