# Transcript Fetching Options

## Background

YTDigest fetches video transcripts using the `youtube-transcript-api` Python library. This library works by making HTTP requests to YouTube's web interface and parsing transcript data from the response — it does **not** use Google's official YouTube Data API (which has no transcript endpoint).

Most video transcripts are publicly accessible without any authentication. The main challenge is **rate limiting**: YouTube throttles or blocks IPs that make too many requests in a short period.

## Current Approach: Cookies

**How it works:** We export a `cookies.txt` file from a logged-in browser session and pass it to `youtube-transcript-api`. YouTube sees the requests as coming from a real user browsing the site, so authenticated users get more lenient rate-limit treatment.

**Implementation:** `src/transcripts.py` loads `cookies.txt` (if present) into a `requests.Session` and passes it to `YouTubeTranscriptApi`. If the file doesn't exist, the library works without it.

**Advantages:**
- Simple to set up (export cookies from browser)
- Fewer rate-limit failures than anonymous requests

**Disadvantages:**
- **Security risk:** The cookies contain Google session tokens that grant access to the entire Google account (Gmail, Drive, etc.), not just YouTube. Anyone who obtains the file can impersonate the account holder.
- **Cloud deployment liability:** Storing the file in a Docker image, server, or git repo exposes it to anyone with access to those systems.
- **Account ban risk:** If YouTube detects automated access on an authenticated session, they could restrict the Google account.
- **Maintenance burden:** Cookies expire periodically, requiring manual re-export from the browser. There's no automated refresh mechanism.

## Option 1: Proxy Rotation

**How it works:** Instead of authenticating, make unauthenticated requests from rotating IP addresses. If one IP gets rate-limited, the next request comes from a different one. No cookies or account credentials involved.

**Implementation:** `youtube-transcript-api` has built-in support for proxies via `WebshareProxyConfig` (Webshare's paid residential rotating proxy service) or `GenericProxyConfig` (any HTTPS proxy provider). Credentials would be stored in `.env`.

**Advantages:**
- No Google account exposure — personal account is never involved
- If an IP gets blocked, just rotate to a new one
- Works well for cloud deployment (proxy credentials are low-risk, scoped to the proxy service)
- Automated — no manual maintenance like cookie re-export

**Disadvantages:**
- Ongoing cost (Webshare residential proxies start at ~$5/month)
- Adds a dependency on a third-party proxy service
- Some latency overhead per request

**Best for:** Cloud deployments, or local setups where rate limiting is a frequent problem.

## Option 2: No Authentication

**How it works:** Make anonymous requests with no cookies and no proxies. Rely on the background fetcher's built-in pacing (configurable interval + random jitter) to stay under YouTube's rate limits. Transcripts that fail get retried later.

**Implementation:** Already supported — if `cookies.txt` doesn't exist, `_create_api_client()` creates a plain `YouTubeTranscriptApi()` with no credentials.

**Advantages:**
- Zero cost
- Zero security risk
- Nothing to configure or maintain
- Simplest possible setup for cloud deployment

**Disadvantages:**
- Higher rate of temporary failures, especially with many channels
- Some transcripts may take multiple retry cycles to fetch
- Rate limits are tied to the server's IP, which in a cloud environment is static

**Best for:** Small-scale usage (few channels), or situations where transcript fetch latency is acceptable.

## Recommendation

For **local development**, no-auth (Option 2) is fine. The background fetcher with its 3-minute interval and jitter handles 16 channels without much trouble.

For **cloud deployment**, proxy rotation (Option 1) is the most robust choice. It eliminates the security concerns of cookies, handles rate limits gracefully, and the cost is minimal. The `youtube-transcript-api` library's built-in proxy support makes it straightforward to implement.

Cookies (the current approach) should be treated as a temporary convenience for local development only.

## References

- `src/transcripts.py` — current implementation
- `src/youtube.py` — official YouTube Data API usage (separate from transcript fetching)
- ROADMAP.md — "Proxy for transcripts" item under Later
