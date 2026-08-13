#!/usr/bin/env bash
# Pushes demo/seed_repo to a real GitHub repository so the debug loop has
# something it can actually clone, branch, and open a PR against — the
# loop only works over HTTPS clone URLs, not local paths.
#
# Usage: ./scripts/bootstrap_demo_repo.sh <owner>/<repo>
# Requires: an empty GitHub repo already created at that path, and either
# a GITHUB_TOKEN env var or an already-authenticated `git` credential
# helper for github.com.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <owner>/<repo>" >&2
  exit 1
fi

TARGET="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEED_DIR="$ROOT/demo/seed_repo"

REMOTE_URL="https://github.com/${TARGET}.git"
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${TARGET}.git"
fi

cd "$SEED_DIR"
if [[ ! -d .git ]]; then
  git init -q
  git checkout -q -b main
fi
git add -A
git commit -q -m "seed: broken orders-api (ZeroDivisionError on empty cart)" --allow-empty
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"
git push -u origin main --force

echo "Pushed to https://github.com/${TARGET}"
echo "Set repo_url in demo/seed_repo/sample_request.json to: https://github.com/${TARGET}.git"
