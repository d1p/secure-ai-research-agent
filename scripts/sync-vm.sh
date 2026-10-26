#!/usr/bin/env bash
# Sync a committed branch from the canonical host clone to the AI VM.
#
# The VM has no GitHub credentials. This builds a git bundle on the host and
# fast-forwards the VM's checkout, leaving .env and named volumes untouched.
# Run from the host repo root (or anywhere inside it) with a clean tree.
set -euo pipefail

BRANCH="${1:-main}"
VM_HOST="${VM_HOST:-root@10.0.0.210}"
VM_DIR="${VM_DIR:-/opt/ai-stack}"

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "$REPO_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "refusing to sync: host working tree is not clean" >&2
  git status --short >&2
  exit 1
fi
git rev-parse --verify "$BRANCH" >/dev/null

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
git bundle create "$TMP_DIR/repo.bundle" "$BRANCH"
scp -q "$TMP_DIR/repo.bundle" "$VM_HOST:/tmp/ai-stack-sync.bundle"

ssh "$VM_HOST" bash -s -- "$VM_DIR" "$BRANCH" <<'REMOTE'
set -euo pipefail
VM_DIR="$1"
BRANCH="$2"
cd "$VM_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "refusing to sync: VM working tree is dirty" >&2
  git status --short >&2
  exit 1
fi
CURRENT="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT" != "$BRANCH" ]; then
  echo "refusing to sync: VM is on '$CURRENT', expected '$BRANCH'" >&2
  exit 1
fi

git bundle verify /tmp/ai-stack-sync.bundle >/dev/null
BACKUP="pre-sync-$(date +%Y%m%d%H%M%S)"
git branch -f "$BACKUP" HEAD
git fetch /tmp/ai-stack-sync.bundle "$BRANCH"
git merge --ff-only FETCH_HEAD
git update-ref "refs/remotes/origin/$BRANCH" FETCH_HEAD
rm -f /tmp/ai-stack-sync.bundle
echo "VM $VM_DIR now at $(git rev-parse --short HEAD) (backup branch $BACKUP)"
REMOTE
