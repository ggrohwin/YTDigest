#!/usr/bin/env bash
# Creates and finalizes a Sentry release for the current commit, with
# commits synced from git, so Suspect Commits can attribute issues to
# the right commit and file/line. Run this after committing AND pushing
# (set-commits --auto needs the commit to exist on GitHub already).
#
# Requires sentry-cli (npm install -g @sentry/cli) and a .sentryclirc
# at the project root with an auth token.
#
# Usage: scripts/sentry_sync_release.sh

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VERSION="$(git rev-parse HEAD)"
echo "Syncing Sentry release for $VERSION"

sentry-cli releases new "$VERSION"
sentry-cli releases set-commits "$VERSION" --auto
sentry-cli releases finalize "$VERSION"
