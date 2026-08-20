"""One-off probe: measure real transcript-fetch failure rates across a list of
candidate YouTube channels, to find which ones are naturally more error-prone
before adding them to a test instance's config.yaml.

Not part of the running app — run manually:
    .venv\\Scripts\\python scripts\\probe_channels.py

Deliberately does not import src.main, so it never calls sentry_sdk.init()
and never sends anything to Sentry.
"""

import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.transcripts import fetch_transcript  # noqa: E402
from src.youtube import (  # noqa: E402
    get_channel_uploads_playlist_id,
    get_youtube_client,
)

logging.basicConfig(level=logging.WARNING, format="  [%(levelname)s] %(message)s")

VIDEOS_PER_CHANNEL = 8
TRANSCRIPT_FETCH_DELAY_SECONDS = 2.5
CHANNELS_PER_BATCH = 3
BATCH_PAUSE_SECONDS = 120

# (category, display_name, search_query, known_channel_id)
# known_channel_id is set when we already have the exact ID from research,
# skipping the (quota-costly) search lookup.
#
# live_news is already covered by a prior clean run (LiveNOW from FOX 25%,
# NBC News 25%, Bloomberg Originals 0%) and intentionally left out here.
CANDIDATES = [
    ("age_restricted", "Wendigoon", "Wendigoon", None),
    ("age_restricted", "Rotten Mango", "Rotten Mango", None),
    ("non_english", "Hikakin", "Hikakin", None),
    ("non_english", "Koji Seto", "Koji Seto", None),
    ("members_only", "H3 Podcast", "H3 Podcast", None),
]


def resolve_channel_id(
    youtube, search_query: str
) -> tuple[str, str] | tuple[None, None]:
    """Resolve a channel name to (channel_id, matched_title) via search.list."""
    try:
        response = (
            youtube.search()
            .list(part="snippet", q=search_query, type="channel", maxResults=1)
            .execute()
        )
        items = response.get("items", [])
        if not items:
            return None, None
        snippet = items[0]["snippet"]
        return snippet["channelId"], snippet["title"]
    except Exception as e:
        print(f"  ! search failed for '{search_query}': {e}")
        return None, None


def get_recent_video_ids(youtube, channel_id: str, max_results: int) -> list[str]:
    uploads_playlist_id = get_channel_uploads_playlist_id(youtube, channel_id)
    if not uploads_playlist_id:
        return []
    try:
        response = (
            youtube.playlistItems()
            .list(
                part="snippet", playlistId=uploads_playlist_id, maxResults=max_results
            )
            .execute()
        )
        return [
            item["snippet"]["resourceId"]["videoId"]
            for item in response.get("items", [])
        ]
    except Exception as e:
        print(f"  ! could not list uploads for {channel_id}: {e}")
        return []


def main():
    youtube = get_youtube_client()
    results = []

    for i, (category, display_name, search_query, known_id) in enumerate(CANDIDATES):
        if i > 0 and i % CHANNELS_PER_BATCH == 0:
            print(f"\n--- batch pause: sleeping {BATCH_PAUSE_SECONDS}s ---")
            time.sleep(BATCH_PAUSE_SECONDS)

        print(f"\n=== {display_name} ({category}) ===")

        if known_id:
            channel_id, matched_title = known_id, display_name
        else:
            channel_id, matched_title = resolve_channel_id(youtube, search_query)

        if not channel_id:
            print("  could not resolve a channel ID, skipping")
            results.append(
                {
                    "category": category,
                    "requested_name": display_name,
                    "resolved_title": None,
                    "channel_id": None,
                    "videos_tested": 0,
                    "failures": 0,
                    "failure_rate": None,
                    "failure_reasons": {},
                }
            )
            continue

        if matched_title != display_name:
            print(
                f"  resolved to: '{matched_title}' ({channel_id}) — verify this is "
                "the right channel"
            )

        video_ids = get_recent_video_ids(youtube, channel_id, VIDEOS_PER_CHANNEL)
        if not video_ids:
            print("  no videos found in uploads playlist")

        reasons = Counter()
        failures = 0
        for video_id in video_ids:
            transcript, failure_reason = fetch_transcript(video_id)
            if transcript is None:
                failures += 1
                reasons[failure_reason] += 1
                print(f"  FAIL {video_id}: {failure_reason}")
            else:
                print(f"  ok   {video_id}")
            time.sleep(TRANSCRIPT_FETCH_DELAY_SECONDS)

        failure_rate = failures / len(video_ids) if video_ids else None
        results.append(
            {
                "category": category,
                "requested_name": display_name,
                "resolved_title": matched_title,
                "channel_id": channel_id,
                "videos_tested": len(video_ids),
                "failures": failures,
                "failure_rate": failure_rate,
                "failure_reasons": dict(reasons),
            }
        )

    results.sort(key=lambda r: (r["failure_rate"] is None, -(r["failure_rate"] or 0)))

    print("\n\n=== Summary (sorted by failure rate) ===")
    for r in results:
        if r["failure_rate"] is None:
            print(
                f"  {r['requested_name']:<20} [{r['category']}]  unresolved / no videos"
            )
        else:
            print(
                f"  {r['requested_name']:<20} [{r['category']}]  "
                f"{r['failures']}/{r['videos_tested']} failed "
                f"({r['failure_rate']:.0%})  {r['failure_reasons']}"
            )

    out_path = Path(__file__).parent / "probe_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
