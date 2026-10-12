---
description: Check YTDigest's Sentry project for new/interesting activity
---

Check the Sentry project `ytdigest` (org `george-grohwin`) for activity in the
last $ARGUMENTS (default: 5d if no window given).

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

**Distinct open issues table**: after the summary, also produce a table of
every currently *unresolved* issue in the project, both environments,
collapsed into distinct problems. This is a current-state snapshot of
unresolved issues, not limited to the activity window above.
- Merge issues whose messages differ only in a video ID, URL, or similar
  per-item value (e.g. `Error fetching transcript for <id>: ...` with the
  same suffix). Messages that differ in *what failed* stay separate rows,
  even if they share a root cause. Don't merge the connectivity-type
  failures (DNS, SSL timeout, connection timeout, etc.) into one row.
- Columns: `#` | distinct issue (normalized message, bolded short label
  first) | Sentry issues (count, then short IDs) | events (total) | env
  (`prod` / `test` / `both`) | first → last seen | category.
- Category is **Known** or **New** relative to the baseline file, plus a
  short qualifier where useful (e.g. "Known (connectivity)", "Known, cause
  unknown", "Demo bug (YTD-32)"). Bold **New**.
- Determine env and event counts at the event level (`search_errors`
  grouped by issue + environment), since an issue's own last-seen and
  counts span all environments even when the list is filtered by one.
  Performance issues (N+1) aren't in the errors dataset, so take their env
  from the issue-level queries and say so in a note.
- First-seen dates are capped by Sentry's ~30-day retention; add a note
  when that understates an issue's real age.
- If the issue list comes back full at the search limit, filter out the
  dominant pattern and re-query so nothing is hidden by truncation.
- Below the table, add only brief notes: anything **New**, and any caveats
  about how the table was built.

**After summarizing**, update the baseline memory file (from
`.claude/memory-paths.local.md`) with any genuinely new findings: append new
issue IDs/patterns in the same structure and voice the file already uses
(dated "New as of <today>" notes, updated recurrence counts for existing
entries, etc.). Don't rewrite or reorganize existing content beyond what's
needed to fold in the new findings. Skip this step if no baseline file path
was found.
