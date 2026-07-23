#!/usr/bin/env bash
# Fires two concurrent POST /api/videos requests for the same not-yet-saved
# video to reproduce the save_video() check-then-act race (IntegrityError:
# UNIQUE constraint failed: videos.id). Requires the artificial
# `await asyncio.sleep(3)` in save_video() (src/database.py) that widens the
# race window enough to hit reliably.
#
# Usage: scripts/trigger_race_condition.sh [video_url] [port]

set -euo pipefail

VIDEO_URL="${1:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"
PORT="${2:-8001}"
ENDPOINT="http://localhost:${PORT}/api/videos"
BODY="{\"url\":\"${VIDEO_URL}\"}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -s -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY" -o "$TMP_DIR/resp1.json" &
curl -s -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY" -o "$TMP_DIR/resp2.json" &
wait

echo "=== response 1 ==="
cat "$TMP_DIR/resp1.json"; echo
echo "=== response 2 ==="
cat "$TMP_DIR/resp2.json"; echo
