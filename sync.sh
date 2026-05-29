#!/usr/bin/env bash
# Push the current branch (and reachable tags) to both Bitbucket and GitHub.
#
# Bitbucket (origin) is the source of truth; GitHub is the mirror that HACS reads.
# Run this after every push so the mirror stays current.
#
#   ./sync.sh
#
# Prereqs: both remotes already configured (run `git remote -v` to check) and
# SSH auth set up for both bitbucket.org and github.com.

set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"

echo "→ pushing $branch + tags to origin (Bitbucket)..."
git push --follow-tags origin "$branch"

echo "→ pushing $branch + tags to github (GitHub mirror)..."
git push --follow-tags github "$branch"

echo "✓ $branch is in sync on both remotes"
