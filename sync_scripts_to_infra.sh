#!/usr/bin/env bash
#
# sync_scripts_to_infra.sh
#
# On-demand sync of the Python scripts in this workspace's src/ folder to the
# WGU Communication-Infrastructure repo.
#
# What it does:
#   1. Clones (or reuses) the target repo into a local, git-ignored cache dir.
#   2. Mirrors every *.py file directly under src/ into the target subfolder:
#        Dev Tools/Python Scipts/Sandbox/Alice/
#      (the "Scipts" spelling matches the actual folder in that repo).
#   3. Commits and pushes if anything changed.
#
# What it syncs:
#   - Only *.py files that live DIRECTLY in src/ (no recursion).
#   - Excludes __pycache__/ and Not_My_Scripts/ automatically (they aren't
#     top-level .py files, and the copy is limited to *.py anyway).
#
# Sync behavior (.py-only mirror):
#   - .py files present in the target but no longer in src/ are REMOVED from
#     the target, so the set of .py files stays in sync both ways.
#   - Non-.py files in the target (README.md, requirements.txt, etc.) are left
#     untouched.
#
# Usage:
#   ./sync_scripts_to_infra.sh            # sync and push
#   ./sync_scripts_to_infra.sh --dry-run  # show what would change, no push

set -euo pipefail

# --- Configuration ---------------------------------------------------------

TARGET_REPO_URL="https://github.com/WGU-edu/Communication-Infrastructure.git"
TARGET_BRANCH="main"

# Subfolder inside the target repo that mirrors our src/ scripts.
# NOTE: "Scipts" is misspelled in the actual repo; keep it as-is to match.
TARGET_SUBDIR="Dev Tools/Python Scipts/Sandbox/Alice"

# Local source folder (resolved relative to this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/src"

# Local cache clone of the target repo. Lives under the workspace but is
# git-ignored so it never gets committed to THIS repo.
CACHE_DIR="${SCRIPT_DIR}/.sync-cache/Communication-Infrastructure"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# --- Helpers ---------------------------------------------------------------

log() {
    echo "[sync] $*"
}

# --- Steps -----------------------------------------------------------------

# Step 1: sanity-check the source folder.
if [[ ! -d "$SRC_DIR" ]]; then
    echo "ERROR: source folder not found: $SRC_DIR" >&2
    exit 1
fi

# Step 2: clone the target repo if we don't have it yet, otherwise refresh it.
if [[ -d "$CACHE_DIR/.git" ]]; then
    log "Refreshing existing clone at $CACHE_DIR"
    git -C "$CACHE_DIR" fetch --quiet origin "$TARGET_BRANCH"
    git -C "$CACHE_DIR" checkout --quiet "$TARGET_BRANCH"
    git -C "$CACHE_DIR" reset --hard --quiet "origin/${TARGET_BRANCH}"
else
    log "Cloning $TARGET_REPO_URL"
    mkdir -p "$(dirname "$CACHE_DIR")"
    git clone --quiet --branch "$TARGET_BRANCH" "$TARGET_REPO_URL" "$CACHE_DIR"
fi

DEST_DIR="${CACHE_DIR}/${TARGET_SUBDIR}"
mkdir -p "$DEST_DIR"

# Step 3: remove .py files in the target that no longer exist in src/.
# Only touch .py files directly in the destination folder; leave everything
# else (README.md, requirements.txt, subfolders) alone.
shopt -s nullglob
for dest_file in "$DEST_DIR"/*.py; do
    name="$(basename "$dest_file")"
    if [[ ! -f "${SRC_DIR}/${name}" ]]; then
        log "Removing stale: ${TARGET_SUBDIR}/${name}"
        rm "$dest_file"
    fi
done

# Step 4: copy every top-level .py file from src/ into the target folder.
for src_file in "$SRC_DIR"/*.py; do
    name="$(basename "$src_file")"
    cp "$src_file" "${DEST_DIR}/${name}"
    log "Synced: ${name}"
done
shopt -u nullglob

# Step 5: commit and push if anything changed.
cd "$CACHE_DIR"

if git diff --quiet && git diff --cached --quiet; then
    log "No changes to sync. Target is already up to date."
    exit 0
fi

log "Changes detected:"
git status --short -- "$TARGET_SUBDIR"

if [[ "$DRY_RUN" == true ]]; then
    log "Dry run: not committing or pushing. Changes left in $CACHE_DIR"
    exit 0
fi

git add -- "$TARGET_SUBDIR"
git commit --quiet -m "Sync Alice sandbox Python scripts from Script Development workspace"
log "Pushing to ${TARGET_REPO_URL} (${TARGET_BRANCH})"
git push --quiet origin "$TARGET_BRANCH"
log "Done. Scripts synced to ${TARGET_SUBDIR}"
