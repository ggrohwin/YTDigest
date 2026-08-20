# trigger_race_condition.ps1
# Fires two concurrent POST /api/videos requests for the same not-yet-saved
# video to reproduce the save_video() check-then-act race (IntegrityError:
# UNIQUE constraint failed: videos.id). Requires the artificial
# `await asyncio.sleep(3)` in save_video() (src/database.py) that widens the
# race window enough to hit reliably.
#
# Usage: scripts\trigger_race_condition.ps1 <video_id> [-Port <port>]

param(
    [string]$VideoId,
    [int]$Port = 8001
)

if (-not $VideoId) {
    Write-Host "Usage: trigger_race_condition.ps1 <video_id> [-Port <port>]"
    Write-Host "  <video_id> is the id from a YouTube URL, e.g. the XXXXXXXXXXX in youtube.com/watch?v=XXXXXXXXXXX"
    exit 1
}

$endpoint = "http://localhost:$Port/api/videos"
$videoUrl = "https://www.youtube.com/watch?v=$VideoId"
$body = @{ url = $videoUrl } | ConvertTo-Json

$requestJob = {
    param($endpoint, $body)
    try {
        Invoke-RestMethod -Uri $endpoint -Method Post -ContentType "application/json" -Body $body
    } catch {
        $_.ErrorDetails.Message
    }
}

$job1 = Start-Job -ScriptBlock $requestJob -ArgumentList $endpoint, $body
$job2 = Start-Job -ScriptBlock $requestJob -ArgumentList $endpoint, $body

Write-Host "=== response 1 ==="
Receive-Job -Job $job1 -Wait -AutoRemoveJob | ConvertTo-Json -Depth 5

Write-Host "=== response 2 ==="
Receive-Job -Job $job2 -Wait -AutoRemoveJob | ConvertTo-Json -Depth 5
