#!/usr/bin/env bash
# Fires two concurrent POST /api/videos requests for the same not-yet-saved
# video to reproduce the save_video() check-then-act race (IntegrityError:
# UNIQUE constraint failed: videos.id). Requires the artificial
# `await asyncio.sleep(3)` in save_video() (src/database.py) that widens the
# race window enough to hit reliably.
#
# Usage: scripts/trigger_race_condition.sh <video_id> [port]

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <video_id> [port]" >&2
  echo "  <video_id> is the id from a YouTube URL, e.g. the XXXXXXXXXXX in youtube.com/watch?v=XXXXXXXXXXX" >&2
  exit 1
fi

VIDEO_ID="$1"
PORT="${2:-8001}"
ENDPOINT="http://localhost:${PORT}/api/videos"
BODY="{\"url\":\"https://www.youtube.com/watch?v=${VIDEO_ID}\"}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -s -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY" -o "$TMP_DIR/resp1.json" &
curl -s -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY" -o "$TMP_DIR/resp2.json" &
wait

echo "=== response 1 ==="
cat "$TMP_DIR/resp1.json"; echo
echo "=== response 2 ==="
cat "$TMP_DIR/resp2.json"; echo
