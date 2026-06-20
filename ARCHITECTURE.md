# OPS-scripts — Architecture

Last updated: 2026-06-13

---

## Directory Structure

```
library/scripts/                          # Repo root (valaquer/OPS-scripts)
├── hooks/                              # Shell/Python hooks for Claude Code + OpenCode
│   ├── facade-relay.sh                 # ACTIVE — PostToolUse live mirror relay
│   ├── inject-timestamp.sh            # ACTIVE — UserPromptSubmit per-turn directive
│   ├── block-subagents.py             # ACTIVE — PreToolUse Task tool block
│   ├── protect-outbox.py              # ACTIVE — PreToolUse outbox protection
│   ├── transcript-protection-hook.py  # ACTIVE — PreToolUse transcript protection
│   ├── session-start-time.sh          # ACTIVE — SessionStart timestamp recorder
│   ├── log-config-change.sh           # ACTIVE — ConfigChange logger
│   ├── statusline-huddles.sh          # ACTIVE — statusLine command (not a hook)
│   └── red-mist.sh                    # RETIRED — broken symlink, target deleted. Parked by Boss.
├── mcp-reddit/
│   └── server.py                       # ACTIVE — Reddit MCP server (4 tools)
├── kitty-open-teammate.sh             # ACTIVE — Main teammate launcher (Raycast)
├── close-tabs.py                       # ACTIVE — Tab/process closer (group-aware)
├── start-all.sh                        # ACTIVE — Raycast "Start" (22 tabs + 7 huddles)
├── mini-launch.sh                      # ACTIVE — Mini-side launcher (NFS-shared)
├── open-facade.sh                      # ACTIVE — Raycast "Facade"
├── open-workbench.sh                   # ACTIVE — Raycast "Workbench" (3 tabs)
├── open-markwhen.sh                    # ACTIVE — Raycast "Markwhen"
├── reminder-agent.sh                   # ACTIVE — Launchd reminder agent
├── com.honeybloom.reminder-agent.plist # ACTIVE — Launchd plist for reminder agent
├── vault.py                            # ACTIVE — Encrypted vault (SQLCipher)
├── safe.sh                             # ACTIVE — Encrypted disk image mount/unmount
├── watermark.py                        # ACTIVE — PixelSeal watermarking CLI
├── reel-smart-extract.py              # ACTIVE — Smart frame extraction from video
├── transcript-search.py               # ACTIVE — Facade/JSONL conversation search
├── failover-to-v4.sh                  # ACTIVE — Emergency failover to OpenCode
├── failover-to-46.sh                  # ACTIVE — Emergency failover to Claude Code
├── janus-config.csv                    # ACTIVE — Teammate-model matrix (canonical)
├── honeybloom-succinct-language.md     # ACTIVE — Per-turn directive source
├── espanso-base.yml                    # LEGACY — Text expansion config
├── bw-get.sh                           # LEGACY — Bitwarden retrieval
├── ig-reel-dl.sh                       # ACTIVE — Instagram reel download
├── calendar-wake.sh                    # LEGACY — Calendar-based teammate wake
├── clean-memory-file-cruft.sh         # LEGACY — Memory file cleanup
├── meeting-status.sh                   # LEGACY — Meeting status check
├── mirror-system-config.sh            # LEGACY — System config mirror
├── setup-from-drive.sh                # ACTIVE — Setup from Google Drive backup
├── transfer-to-drive.sh              # ACTIVE — Transfer to Google Drive backup
├── skills-to-pdf.sh                   # LEGACY — Skills to PDF conversion
└── .gitignore
```

Runtime artifacts (not tracked):
- `.failover-backup/` — created by failover scripts via `mkdir -p` during execution

---

## Dependency Graph

### 1. Lifecycle Cluster

```
kitty-open-teammate.sh
  ├── reads: janus-config.csv (harness, model, machine)
  ├── reads: ORG.md (Groups section — DUO/TRIO/SINGLE)
  ├── discovers: Kitty socket (/tmp/honeybloom-kitty-*.sock)
  ├── calls: mini-launch.sh (via SSH for machine=mini)
  ├── calls: Facade /api/rooms/activate
  ├── calls: Facade /api/huddle (auto-start for groups)
  ├── reads: macOS Keychain (hanover-keychain for Mini password)
  └── writes: NFS .tmp/ (wakeup prompt + password files for Mini)

mini-launch.sh (runs on Mac Mini via SSH)
  ├── reads: NFS .tmp/ (wakeup prompt + password files)
  ├── calls: security unlock-keychain (Mini Keychain)
  ├── exports: FACADE_URL (LAN IP for hooks)
  └── exec: claude or opencode binary

close-tabs.py
  ├── reads: ORG.md (Groups section)
  ├── reads: janus-config.csv (machine column)
  ├── discovers: Kitty socket
  ├── calls: SSH to Mini (pgrep + kill for mini tabs)
  ├── calls: safe.sh unmount (if teammate has a safe)
  └── calls: Facade /api/rooms/deactivate

start-all.sh
  ├── calls: kitty-open-teammate.sh --solo (22 times, parallel)
  └── calls: Facade /api/huddle (7 huddles, parallel)
```

### 2. Hook Cluster

See **Hook Registration** section below for full mapping.

```
facade-relay.sh (PostToolUse)
  ├── reads: livemirror-global flag file
  ├── reads: Facade /api/active-rooms (room resolution)
  ├── applies: CRED_REGEX credential filter (FP-12)
  ├── generates: summary for read tools, full detail for write tools
  └── POSTs: Facade /api/tool-activity

inject-timestamp.sh (UserPromptSubmit)
  ├── reads: honeybloom-succinct-language.md (canonical directive)
  ├── reads: Facade /api/rooms/active-room (active rooms)
  └── outputs: JSON hookSpecificOutput (timestamp + directive)

block-subagents.py (PreToolUse)
  └── blocks: Task tool (dual-protocol: stdout "deny" + exit 2)

protect-outbox.py (PreToolUse)
  └── blocks: rm/mv on ~/honeybloom/mailbox/outbox/

transcript-protection-hook.py (PreToolUse)
  └── blocks: rm/mv on ~/.claude/projects/-Users-d-patnaik-honeybloom-*/*.jsonl

session-start-time.sh (SessionStart)
  └── writes: /tmp/.claude-session-start-{teammate}

log-config-change.sh (ConfigChange)
  └── appends: /tmp/claude-config-changes.log

statusline-huddles.sh (statusLine command)
  ├── reads: /tmp/kitty-huddles.json
  └── outputs: huddle status string for Kitty status bar
```

### 3. CLI Tools Cluster

```
vault.py → SQLCipher CLI (/opt/homebrew/bin/sqlcipher) + macOS Keychain (vault-{teammate})
safe.sh → hdiutil + macOS Keychain (safe-{teammate})
watermark.py → PyTorch + videoseal repo (library/watermark/)
reel-smart-extract.py → FFmpeg + OpenCV
transcript-search.py → Facade SQLite (library/facade/facade.db) + JSONL files
reminder-agent.sh → ORG.md roster + REMINDERS.md files + Facade /api/pulse
```

### 4. Raycast Shortcuts Cluster

```
open-facade.sh → starts Facade dev server (port 51730) + opens Safari
open-workbench.sh → starts Workbench dev server (port 51740) + opens 3 Safari tabs
open-markwhen.sh → ensures Facade running + opens markwhen-fork.html
```

### 5. Emergency Failover Cluster

```
failover-to-v4.sh
  ├── reads: ORG.md roster (excludes natalie as safety net)
  ├── rewrites: janus-config.csv (atomic via mktemp+mv)
  ├── backs up: janus-config.csv to .failover-backup/
  ├── strips: hooks from opencode.json files (prevents Medusa + shell duplication)
  ├── kills: all Kitty tabs
  └── relaunches: via kitty-open-teammate.sh (group-aware)

failover-to-46.sh (reverse of above)
  ├── restores: hooks from .failover-backup/hooks/
  ├── rewrites: janus-config.csv
  ├── kills: all Kitty tabs
  └── relaunches: via kitty-open-teammate.sh
```

### 6. MCP Server Cluster

```
mcp-reddit/server.py
  ├── 4 tools: get_posts, search_posts, get_thread, get_user_activity
  ├── JSON-first with old.reddit.com HTML fallback
  └── registered in: ~/.claude.json (mcpServers.honeybloom-reddit)
```

---

## Hook Registration

### Claude Code (settings.json at ~/.claude/settings.json)

| Event | Script | Matcher | Timeout | Harness |
|-------|--------|---------|---------|---------|
| PreToolUse | transcript-protection-hook.py | Bash | 5s | Claude Code only |
| PreToolUse | protect-outbox.py | Bash | 5s | Claude Code only |
| PreToolUse | block-subagents.py | Task | 5s | Both (dual-protocol) |
| UserPromptSubmit | inject-timestamp.sh | — | 5s | Claude Code only |
| PostToolUse | facade-relay.sh | — | 5s | Claude Code only |
| SessionStart | session-start-time.sh | — | 5s | Claude Code only |
| ConfigChange | log-config-change.sh | * | 5s | Claude Code only |

Additionally, `statusline-huddles.sh` is called from the `statusLine` config block (not a hook — a status bar command).

### OpenCode (Medusa plugin at ~/.config/opencode/plugins/medusa.ts)

Medusa handles 3 functions natively via OpenCode's plugin system:
- `tool.execute.before` — Task tool block + transcript protection (replaces block-subagents.py + transcript-protection-hook.py)
- `tool.execute.after` — Facade relay with summaries (replaces facade-relay.sh)
- `experimental.chat.system.transform` — Timestamp + succinct directive injection (replaces inject-timestamp.sh)

**Pattern 4 warning:** Changes to facade-relay.sh, inject-timestamp.sh, or block-subagents.py may require parallel changes in Medusa (library/medusa/medusa.ts, valaquer/medusa repo). Always check both.

---

## Data Flow

### External Data Sources

| Source | Read By | Purpose |
|--------|---------|---------|
| ORG.md (`library/ORG.md`) | kitty-open-teammate.sh, close-tabs.py, failover scripts, reminder-agent.sh | Roster + Groups SSoT |
| janus-config.csv (canonical in this repo) | kitty-open-teammate.sh, close-tabs.py, failover scripts | Harness, model, machine routing |
| Facade API (localhost:51730 or LAN IP) | facade-relay.sh, inject-timestamp.sh, reminder-agent.sh, kitty-open-teammate.sh, close-tabs.py | Room resolution, tool activity, pulse, activate/deactivate |
| macOS Keychain | kitty-open-teammate.sh, mini-launch.sh, vault.py, safe.sh | Passwords and encryption keys |
| Kitty socket (/tmp/honeybloom-kitty-*.sock) | kitty-open-teammate.sh, close-tabs.py, failover scripts, statusline-huddles.sh | Tab discovery and management |
| livemirror-global flag (`library/facade/livemirror-global`) | facade-relay.sh | Live mirror on/off |
| honeybloom-succinct-language.md (`library/output-styles/`) | inject-timestamp.sh | Per-turn directive content |
| REMINDERS.md (per teammate dir) | reminder-agent.sh | Scheduled reminders |

### Symlinks

| Symlink | Target (canonical) |
|---------|--------------------|
| `rio/janus-config.csv` | `library/scripts/janus-config.csv` |
| `library/skills/gestalt-layer-3-janus/janus-config.csv` | `library/scripts/janus-config.csv` |

---

## Blast Radius Map

### Cross-Repo Dependencies

| This Repo's File | Depends On (External) | Depended On By (External) |
|-------------------|-----------------------|---------------------------|
| kitty-open-teammate.sh | Facade /api/rooms/activate, /api/huddle | Facade (teammate lifecycle), Hanover (SSH routing) |
| close-tabs.py | Facade /api/rooms/deactivate | Facade (deactivation), Hanover (Mini SSH close) |
| facade-relay.sh | Facade /api/tool-activity, /api/active-rooms | Facade (live mirror), Medusa (parallel impl) |
| inject-timestamp.sh | Facade /api/rooms/active-room | Facade (room context), Medusa (parallel impl) |
| mini-launch.sh | NFS mount, Keychain | Hanover (Mini teammate spawning) |
| failover-to-v4.sh / failover-to-46.sh | OpenCode binary, Medusa plugin | Janus (model migration) |
| janus-config.csv | — | Janus L3, kitty-open-teammate.sh, close-tabs.py, failover scripts |
| reminder-agent.sh | Facade /api/pulse, ORG.md | Facade (reminder system) |
| mcp-reddit/server.py | old.reddit.com | ~/.claude.json MCP registration |
| vault.py | SQLCipher binary, Keychain | Felix/Katja vaults |
| safe.sh | Keychain | Felix safe, close-tabs.py (auto-unmount) |
| watermark.py | PyTorch, videoseal | Dante/Sierra workflow |

---

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| 6 LEGACY scripts tracked but unused | Low | espanso-base.yml, bw-get.sh, calendar-wake.sh, clean-memory-file-cruft.sh, meeting-status.sh, skills-to-pdf.sh. Candidates for cleanup. |
| No automated tests | Medium | All verification is manual via B13 (Boss visual). |
| Credential filter regex is best-effort | Medium | CRED_REGEX in facade-relay.sh catches known patterns but novel credential formats may leak. FP-12 defense-in-depth. |
