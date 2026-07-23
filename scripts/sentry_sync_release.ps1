# sentry_sync_release.ps1
# Creates and finalizes a Sentry release for the current commit, with
# commits synced from git, so Suspect Commits can attribute issues to
# the right commit and file/line. Run this after committing AND pushing
# (set-commits --auto needs the commit to exist on GitHub already).
#
# Requires sentry-cli (npm install -g @sentry/cli) and a .sentryclirc
# at the project root with an auth token.
#
# Usage: scripts\sentry_sync_release.ps1

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$version = (git rev-parse HEAD).Trim()
Write-Host "Syncing Sentry release for $version"

sentry-cli releases new $version
sentry-cli releases set-commits $version --auto
sentry-cli releases finalize $version
