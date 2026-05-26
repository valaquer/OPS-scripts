#!/usr/bin/env bash
# Rescue script for the OpenCode fork binary.
# Restores ~/.opencode/bin/opencode from the most reliable source available.
#
# Tiers (used automatically unless --tier is specified):
#   1 — Download from GitHub Release (valaquer/opencode-fork v1.14.30-honeybloom)
#   2 — Rebuild from local source + patch (chica/opencode-fork/)
#   3 — Fall back to upstream backup (~/.opencode/bin/opencode.upstream)
#
# Verification uses a temp copy since --version hangs when testing the
# running process's own binary path.
#
# Usage: ./rescue-opencode.sh [--tier 1|2|3] [--force]

set -euo pipefail

DEPLOY_PATH="$HOME/.opencode/bin/opencode"
BACKUP_PATH="$HOME/.opencode/bin/opencode.upstream"
RELEASE_TAG="v1.14.30-honeybloom-3"
RELEASE_REPO="valaquer/opencode-fork-v2"
FORK_DIR="$HOME/honeybloom/chica/opencode-fork"
BUILD_SCRIPT="$FORK_DIR/build-fork.sh"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[rescue]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[rescue]${NC} $*" >&2; }
die()  { echo -e "${RED}[rescue]${NC} $*" >&2; exit 1; }

cleanup() { rm -f /tmp/opencode-rescue /tmp/opencode-ver-* /tmp/opencode-deploy-*; }
trap cleanup EXIT

# Verify a binary without exec'ing it (avoids hang when testing the
# running process's own path). Uses file type + size check instead.
check_binary_safe() {
  local path="$1"
  if [[ ! -f "$path" ]]; then return 1; fi
  if [[ ! -x "$path" ]]; then return 1; fi
  local ftype
  ftype="$(file "$path" 2>/dev/null)" || return 1
  if [[ "$ftype" != *"Mach-O 64-bit executable arm64"* ]]; then return 1; fi
  local size
  size="$(stat -f%z "$path" 2>/dev/null)" || return 1
  if [[ "$size" -lt 1000000 ]]; then return 1; fi
  return 0
}

# Get version from a temp copy (exec from a path different from the
# running process to avoid hangs).
get_version() {
  local src="$1"
  local tmp
  tmp="$(mktemp /tmp/opencode-ver-XXXXXX)"
  cp "$src" "$tmp"
  chmod +x "$tmp"
  "$tmp" --version 2>/dev/null
  local rc=$?
  rm -f "$tmp"
  return $rc
}

backup_current() {
  if [[ -f "$DEPLOY_PATH" ]]; then
    local backup="$DEPLOY_PATH.bak.$(date +%Y%m%d%H%M%S)"
    cp "$DEPLOY_PATH" "$backup"
    log "Backed up current binary to $backup"
  fi
}

# Atomically replace the deploy path. Writes to a temp file, verifies,
# then mv (atomic on same filesystem).
deploy_binary() {
  local src="$1"
  local tmp
  tmp="$(mktemp /tmp/opencode-deploy-XXXXXX)"
  cp "$src" "$tmp"
  chmod +x "$tmp"
  if ! check_binary_safe "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  backup_current
  mv "$tmp" "$DEPLOY_PATH"
  cp "$DEPLOY_PATH" "$BACKUP_PATH"
  chmod +x "$BACKUP_PATH"
  log "Backup seeded at $BACKUP_PATH"
}

tier1_github() {
  log "Tier 1: Downloading from GitHub Release ($RELEASE_REPO $RELEASE_TAG)..."
  if ! command -v gh &>/dev/null; then
    warn "gh not available — skipping Tier 1"
    return 1
  fi
  gh release download "$RELEASE_TAG" -R "$RELEASE_REPO" -p opencode --output /tmp/opencode-rescue 2>/dev/null || {
    warn "GitHub Release download failed"
    return 1
  }
  chmod +x /tmp/opencode-rescue
  if ! check_binary_safe /tmp/opencode-rescue; then
    warn "Downloaded binary fails verification"
    rm -f /tmp/opencode-rescue
    return 1
  fi
  if ! get_version /tmp/opencode-rescue >/dev/null 2>&1; then
    warn "Downloaded binary --version check failed"
    rm -f /tmp/opencode-rescue
    return 1
  fi
  deploy_binary /tmp/opencode-rescue
  rm -f /tmp/opencode-rescue
}

tier2_rebuild() {
  log "Tier 2: Rebuilding from local fork source..."
  if [[ ! -d "$FORK_DIR" ]]; then
    warn "Fork source not found at $FORK_DIR"
    return 1
  fi
  if [[ ! -f "$BUILD_SCRIPT" ]]; then
    warn "Build script not found at $BUILD_SCRIPT"
    return 1
  fi
  pushd "$FORK_DIR" >/dev/null
  if ! bash "$BUILD_SCRIPT" 2>&1; then
    warn "Build failed"
    popd >/dev/null
    return 1
  fi
  local arch platform_dir
  arch="$(uname -m)"
  case "$arch" in
    arm64) platform_dir="opencode-darwin-arm64" ;;
    x86_64) platform_dir="opencode-darwin-x64" ;;
    *) warn "Unknown arch: $arch"; popd >/dev/null; return 1 ;;
  esac
  local built="$FORK_DIR/packages/opencode/dist/${platform_dir}/bin/opencode"
  if [[ ! -f "$built" ]]; then
    warn "Built binary not found at $built"
    popd >/dev/null
    return 1
  fi
  if ! check_binary_safe "$built"; then
    warn "Built binary fails verification"
    popd >/dev/null
    return 1
  fi
  if ! get_version "$built" >/dev/null 2>&1; then
    warn "Built binary --version check failed"
    popd >/dev/null
    return 1
  fi
  deploy_binary "$built"
  popd >/dev/null
}

tier3_upstream() {
  log "Tier 3: Falling back to upstream binary..."
  if [[ ! -f "$BACKUP_PATH" ]]; then
    die "Upstream backup not found at $BACKUP_PATH — nothing to restore from"
  fi
  if ! check_binary_safe "$BACKUP_PATH"; then
    die "Upstream backup is also broken — manual intervention required"
  fi
  deploy_binary "$BACKUP_PATH"
}

summary() {
  if check_binary_safe "$DEPLOY_PATH"; then
    local size ver
    size="$(stat -f%z "$DEPLOY_PATH" 2>/dev/null)"
    ver="$(get_version "$DEPLOY_PATH" 2>/dev/null || echo "version unavailable")"
    log "Rescue complete — $DEPLOY_PATH ($ver, ${size} bytes)"
  else
    die "Rescue failed — binary at $DEPLOY_PATH is not a valid executable"
  fi
}

TIER=""
FORCE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    *) die "Unknown option: $1 (usage: --tier 1|2|3, --force)" ;;
  esac
done

if [[ "$FORCE" != true ]] && check_binary_safe "$DEPLOY_PATH"; then
  log "Binary at $DEPLOY_PATH is working — nothing to rescue (use --force to override)"
  exit 0
fi

if [[ -n "$TIER" ]]; then
  case "$TIER" in
    1) tier1_github || tier2_rebuild || tier3_upstream ;;
    2) tier2_rebuild || tier1_github || tier3_upstream ;;
    3) tier3_upstream ;;
    *) die "Invalid tier: $TIER (must be 1, 2, or 3)" ;;
  esac
else
  tier1_github || tier2_rebuild || tier3_upstream
fi

summary
