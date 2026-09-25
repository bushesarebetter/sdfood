#!/usr/bin/env bash
# Remove every historical, facility-level version of dashboard.html from ALL branches and tags.
#
# Why: every earlier dashboard.html embedded one row per active facility (first with city, ZIP,
# exact scores and visit timing; later "de-identified" with type, risk, history bands and months
# since the last visit, which still made ~80-90% of rows unique and linkable to named businesses
# in the County's public search). The current dashboard.html is aggregate-only and passes
# privacy_gate.py; the old blobs are still reachable in history until this is run.
#
# Run AFTER the v2 branch is merged, from a machine with push rights:
#   pip install git-filter-repo
#   tools/purge_history.sh git@github.com:bushesarebetter/sdfood.git          # dry run
#   tools/purge_history.sh git@github.com:bushesarebetter/sdfood.git --push   # rewrite + force-push
#
# Then: (1) ask GitHub Support to purge cached views and pull-request refs (docs/PUBLISHING.md),
# (2) have every collaborator re-clone -- old clones still contain the blobs.
set -euo pipefail
URL=${1:?usage: purge_history.sh <repo-url> [--push]}
PUSH=${2:-}
command -v git-filter-repo >/dev/null || { echo "install git-filter-repo first: pip install git-filter-repo"; exit 1; }
WORK=$(mktemp -d)
echo "working in $WORK"
git clone --quiet --mirror "$URL" "$WORK/repo.git"
cp -r "$WORK/repo.git" "$WORK/backup.git"          # untouched copy, in case you need to roll back
cd "$WORK/repo.git"

# Keep only the dashboard.html on the default branch tip, and only if it passes the privacy gate.
GATE="$(cd "$(dirname "$0")/.." && pwd)/privacy_gate.py"
DEFAULT=$(git symbolic-ref --short HEAD)
KEEP=$(git rev-parse "$DEFAULT:dashboard.html" 2>/dev/null || true)
if [ -n "$KEEP" ]; then
  git cat-file -p "$KEEP" > "$WORK/keep.html"
  python "$GATE" "$WORK/keep.html" || { echo "the default branch's dashboard.html fails the privacy gate; fix it first"; exit 1; }
fi
git log --all --full-history --format=%H -- dashboard.html | while read -r c; do
  git rev-parse --quiet --verify "$c:dashboard.html" 2>/dev/null || true
done | sort -u | grep -v "^${KEEP:-none}$" > "$WORK/blobs.txt" || true
echo "blobs to strip: $(wc -l < "$WORK/blobs.txt")"
[ -s "$WORK/blobs.txt" ] || { echo "nothing to strip"; exit 0; }
git filter-repo --force --strip-blobs-with-ids "$WORK/blobs.txt"

LEFT=$(git log --all --full-history --format=%H -- dashboard.html | while read -r c; do
  git rev-parse --quiet --verify "$c:dashboard.html" 2>/dev/null || true; done | sort -u | grep -Fxf "$WORK/blobs.txt" || true)
[ -z "$LEFT" ] || { echo "ERROR: blobs still reachable: $LEFT"; exit 1; }
echo "verified: no stripped blob is reachable from any ref"

if [ "$PUSH" = "--push" ]; then
  git remote add origin "$URL" 2>/dev/null || git remote set-url origin "$URL"
  git push --force --all origin
  git push --force --tags origin
  echo "pushed. Now contact GitHub Support (docs/PUBLISHING.md) and re-clone everywhere."
else
  echo "dry run only. Inspect $WORK/repo.git, then re-run with --push."
fi
