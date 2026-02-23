# Ideas

Exploratory ideas not yet committed to the roadmap.

## MCP Integration

Opportunities for integrating Model Context Protocol into YTDigest.

### MCP Server: Video Database
Expose the SQLite database (videos, transcripts, summaries) as MCP resources. Any MCP-compatible client (e.g. Claude Code) could query the video library conversationally. Lowest effort, most immediately useful starting point.

### Chat with Transcript via MCP
Instead of building a custom chat UI, expose transcripts via MCP and use any Claude-powered client to query them. Could replace or complement a built-in chat feature.

### MCP Client: YouTube API
Wrap the YouTube Data API as an MCP server, replacing or augmenting `youtube.py`. Makes YouTube querying reusable across projects.

### Export/Integration via Existing MCP Servers
Roadmap items like email digest, Notion export, and Slack notifications could leverage community MCP servers rather than building each integration from scratch.

### Semantic Search via MCP
Wrap a vector database as an MCP server for embedding-based search across transcripts and summaries.

## Web Article Digest

Extend the app beyond YouTube to capture and summarize web articles/posts. Goal: a single digest for all AI news sources, not just videos.

### Chrome Extension
A browser extension with a button to queue the current page into the digest. Sends the URL to the FastAPI backend for extraction and summarization.

### Incremental Approach
1. Start with a backend API endpoint and a bookmarklet (zero-install browser bookmark that runs JavaScript to POST the URL)
2. Validate the mixed content experience in the UI
3. Build the Chrome extension once the workflow is proven