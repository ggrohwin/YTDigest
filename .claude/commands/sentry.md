---
description: Check YTDigest's Sentry project for new/interesting activity
---

Check the Sentry project `ytdigest` (org `george-grohwin`) for activity in the
last $ARGUMENTS (default: 24h if no window given).

Cover **both** `environment:production` and `environment:test` — query each
explicitly, never assume one.

**Baseline**: read `.claude/memory-paths.local.md` (machine-local, not in
git) for the path to the Sentry open-issues baseline memory file, then read
that file. Treat every issue/pattern already listed there as known — don't
re-report it as new. Report it again only if something about it has
materially changed (new recurrence, escalated volume, spread to a new
environment, etc.), in the same spirit as that file's own "No longer a
one-off" / "New as of" notes. If `.claude/memory-paths.local.md` doesn't
exist, skip this step and note in the summary that no baseline was found.

Noise-filtering rules:
- Group findings by distinct error message, not raw event/issue count.
- Don't over-report expected background noise: the YouTube IP-block error
  ("YouTube is blocking requests from your IP") and the deliberately-staged
  Sentry demo bugs (N+1 query, artificial `save_video` race, `/sentry-debug`
  endpoint — Jira `YTD-32`).
- Call out specifically what's **new** — a message or pattern not already
  covered by those two categories or by the baseline file above — since
  that's the actual signal worth surfacing.

Summarize concisely: what's new, what's known noise (one line, don't detail),
and anything that looks worth acting on.

**After summarizing**, update the baseline memory file (from
`.claude/memory-paths.local.md`) with any genuinely new findings: append new
issue IDs/patterns in the same structure and voice the file already uses
(dated "New as of <today>" notes, updated recurrence counts for existing
entries, etc.). Don't rewrite or reorganize existing content beyond what's
needed to fold in the new findings. Skip this step if no baseline file path
was found.
