---
description: Check YTDigest's Sentry project for new/interesting activity
---

Check the Sentry project `ytdigest` (org `george-grohwin`) for activity in the
last $ARGUMENTS (default: 24h if no window given).

Cover **both** `environment:production` and `environment:test` — query each
explicitly, never assume one.

Per the reading guidance in this repo's `CLAUDE.md`:
- Group findings by distinct error message, not raw event/issue count.
- Don't over-report expected background noise: the YouTube IP-block error
  ("YouTube is blocking requests from your IP") and the deliberately-staged
  Sentry demo bugs (N+1 query, artificial `save_video` race, `/sentry-debug`
  endpoint — Jira `YTD-32`).
- Call out specifically what's **new** — a message or pattern not already
  covered by those two categories — since that's the actual signal worth
  surfacing.

Summarize concisely: what's new, what's known noise (one line, don't detail),
and anything that looks worth acting on.
