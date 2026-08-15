# OPS-scripts — Architecture

Last updated: 2026-08-15

---

## Directory Structure

```
library/scripts/                          # Repo root (valaquer/OPS-scripts)
├── hooks/                              # Shell/Python hooks for Claude Code + OpenCode
│   ├── aether-relay.sh                 # ACTIVE — PostToolUse live mirror relay
│   ├── inject-timestamp.sh            # ACTIVE — UserPromptSubmit per-turn timestamp
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
├── start-all.sh                        # ACTIVE — Raycast "Start" (26 tabs + 7 hard-coded huddles; deferred ORG gap)
├── mini-launch.sh                      # ACTIVE — Mini-side launcher (NFS-shared)
├── open-aether.sh                      # ACTIVE — Raycast "Aether"
├── open-workbench.sh                   # ACTIVE — Raycast "Workbench" (3 tabs)
├── provision-workbench-app.sh          # ACTIVE — Scaffold new Workbench-family app from template
├── open-markwhen.sh                    # ACTIVE — Raycast "Markwhen"
├── bavaria-csv009-monitor.py            # ACTIVE — Bavaria CSV009 watchdog (2-min launchd poll)
├── notes-create.sh                     # ACTIVE — Apple Notes creation via SSH to iMac
├── reminder-agent.sh                   # ACTIVE — Launchd reminder agent
├── com.honeybloom.reminder-agent.plist # ACTIVE — Launchd plist for reminder agent
├── vault.py                            # ACTIVE — Encrypted vault (SQLCipher)
├── safe.sh                             # ACTIVE — Encrypted disk image mount/unmount
├── watermark.py                        # ACTIVE — PixelSeal watermarking CLI
├── reel-smart-extract.py              # ACTIVE — Smart frame extraction from video
├── transcript-search.py               # ACTIVE — Aether/JSONL conversation search
├── failover-to-v4.sh                  # ACTIVE — Emergency failover to OpenCode
├── failover-to-46.sh                  # ACTIVE — Emergency failover to Claude Code
├── test-janus-lifecycle.sh             # ACTIVE — Launcher/failover lifecycle fixtures
├── test_close_tabs.py                  # ACTIVE — Group/close unit tests
├── test_codex_process_cleanup.py       # ACTIVE — Disposable Codex tree teardown test
├── espanso-base.yml                    # LEGACY — Text expansion config
├── bw-get.sh                           # LEGACY — Bitwarden retrieval
├── ig-reel-dl.sh                       # ACTIVE — Instagram reel download
├── calendar-wake.sh                    # LEGACY — Calendar-based teammate wake
├── clean-memory-file-cruft.sh         # LEGACY — Memory file cleanup
├── meeting-status.sh                   # LEGACY — Meeting status check
├── bear-watcher.py                     # ACTIVE — Bear note change watcher (iMac DB poll, session batching, Aether notification)
├── bear-watcher.sh                     # ACTIVE — Bear note watcher shell fallback (single-note)
├── mcp-bear/
│   └── server.py                       # ACTIVE — Bear MCP server (6 tools: read, list, write, create, edit, delete)
├── launchd/
│   └── com.honeybloom.bear-watcher.plist  # ACTIVE — Launchd plist for Bear watcher (KeepAlive)
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
  ├── reads: ORG.md (`## Groups` rows with `(host: name)`)
  ├── discovers: Kitty socket (/tmp/honeybloom-kitty-*.sock)
  ├── calls: mini-launch.sh (via SSH for machine=mini)
  ├── calls: Aether /api/rooms/activate
  ├── calls: Aether /api/huddle (auto-start for groups)
  ├── reads: macOS Keychain (hanover-keychain for Mini password)
  └── writes: NFS .tmp/ (wakeup prompt + password files for Mini)

mini-launch.sh (runs on Mac Mini via SSH)
  ├── reads: NFS .tmp/ (wakeup prompt + password files)
  ├── calls: security unlock-keychain (Mini Keychain)
  ├── NOTE: activate call removed (REQ-314) -- open-team.sh is sole caller of /api/rooms/activate
  └── exec: claude, opencode, or codex binary selected by Janus

close-tabs.py
  ├── validates: ORG.md roster and `## Groups` (unknown members, duplicates; solo operators valid)
  ├── discovers: Kitty socket
  ├── kills: local Codex/Claude processes (birth-fingerprinted, cwd-validated)
  ├── calls: safe.sh unmount (if teammate has a safe)
  ├── calls: Aether /api/rooms/deactivate
  └── exports: is_solo_operator() (used by close-team.sh for gatekeeper check)

close-team.sh
  ├── validates: leader name against ORG.md (host check OR solo operator via is_solo_operator())
  ├── calls: close-tabs.py (closes team members or solo individual)
  └── calls: Aether /api/archive-huddle (archives team huddle session)

start-all.sh
  ├── calls: kitty-open-teammate.sh --solo (26 times, parallel)
  └── calls: Aether /api/huddle (7 hard-coded huddles, parallel)
```

The tracked `library/scripts/kitty-open-teammate.sh` is the source, but Raycast
and Aether execute `/Users/d.patnaik/raycast-scripts/kitty-open-teammate.sh` on
the iMac. A launcher change is not deployed until the active iMac file has been
snapshotted, a syntax-checked replacement has been installed atomically, and its
hash has been verified against the tracked source. The active copy must also be
checked against canonical `ORG.md` before lifecycle acceptance.

`start-all.sh` is not fully compatible with the current ORG group contract: canonical
`ORG.md` defines eight multi-member groups, but Start-All bypasses the group-aware
launcher with `--solo` and starts only seven hard-coded huddles, omitting the
Gunnar/Fable group. This is a known deferred consumer gap. Controlled org rollouts
must use `kitty-open-teammate.sh` without `--solo` so its validated `## Groups`
parser governs tab and huddle creation.

### 2. Hook Cluster

See **Hook Registration** section below for full mapping.

```
aether-relay.sh (PostToolUse)
  ├── reads: livemirror-global flag file
  ├── reads: Aether /api/active-rooms (room resolution)
  ├── applies: CRED_REGEX credential filter (FP-12)
  ├── generates: summary for read tools, full detail for write tools
  └── POSTs: Aether /api/tool-activity

inject-timestamp.sh (UserPromptSubmit)
  └── outputs: JSON hookSpecificOutput (timestamp only)

block-aether-db.py (PreToolUse)
  ├── blocks: Bash/Write/Edit targeting aether.db, aether.db-wal, aether.db-shm
  ├── exception: Burt redaction UPDATEs on messages table (cwd + UPDATE + messages check)
  └── exception: OPS team (rio, chica, natalie) sqlite3 -readonly diagnostic queries (cwd + -readonly flag check, SQLite engine enforces)

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
transcript-search.py → Aether SQLite (library/aether/aether.db) + JSONL files
reminder-agent.sh → ORG.md roster + REMINDERS.md files + Aether /api/pulse
```

### 4. Raycast Shortcuts Cluster

```
open-aether.sh → starts Aether dev server (port 51820) + opens Safari
open-workbench.sh → starts Workbench dev server (port 51740) + opens 3 Safari tabs
open-markwhen.sh → ensures Aether running + opens markwhen-fork.html
provision-workbench-app.sh → copies template, replaces placeholders, creates symlinks + GitHub repo, registers in workbench-apps.json
```

### 5. Emergency Failover Cluster

```
failover-to-v4.sh
  ├── validates: ORG roster/groups and exact nine-column Janus identity set before mutation
  ├── preserves: legacy Natalie row unchanged pending Boss's failover-policy decision
  ├── rewrites: canonical wiki Janus CSV (atomic via mktemp+mv)
  ├── backs up: canonical Janus CSV to .failover-backup/
  ├── strips: hooks from opencode.json files (prevents Medusa + shell duplication)
  ├── kills: all Kitty tabs
  └── relaunches: via kitty-open-teammate.sh (group-aware)

failover-to-46.sh (alternate emergency target)
  ├── restores: hooks from .failover-backup/hooks/
  ├── validates and rewrites: canonical nine-column Janus CSV; legacy Natalie row remains unchanged
  ├── kills: all Kitty tabs
  └── relaunches: via kitty-open-teammate.sh
```

The 4.6 and v4 scripts are alternate emergency targets. Neither restores today's Codex/Sol baseline; automating that restoration is deferred to separately gated work.

### 6. MCP Server Cluster (Reddit)

See also cluster 7 for Bear MCP.

```
mcp-reddit/server.py
  ├── 4 tools: get_posts, search_posts, get_thread, get_user_activity
  ├── JSON-first with old.reddit.com HTML fallback
  └── registered in: ~/.claude.json (mcpServers.honeybloom-reddit)
```

### 7. Bear Collaboration Cluster

```
bear-watcher.py
  ├── reads: iMac Bear DB via SSH (ControlMaster at /tmp/bear-watcher-ssh)
  ├── reads: Mini local Bear DB (tag resolution -- interactive sessions only, TCC blocks launchd)
  ├── reads: iMac frontmost app via SSH (session batching trigger)
  ├── reads/consumes: write ledger (/var/tmp/bear-write-ledger.json) for attribution
  ├── reads: Aether /api/rooms (tag routing -- project > team > person)
  ├── POSTs: Aether /api/message (change notifications)
  └── managed by: launchd (com.honeybloom.bear-watcher, KeepAlive, /usr/bin/python3)

mcp-bear/server.py
  ├── 6 tools: bear_read, bear_list, bear_write, bear_create, bear_edit, bear_delete
  ├── reads: iMac Bear DB via SSH (bear_read, bear_list)
  ├── writes: iMac Bear via SSH x-callback-url (bear_write, bear_create, bear_edit, bear_delete)
  ├── writes: write ledger (/var/tmp/bear-write-ledger.json) for attribution
  ├── dedicated venv: mcp-bear/.venv (Python 3.14, MCP v1.x -- v2 dropped fastmcp)
  └── registered in: all 23 teammates' .mcp.json (mcpServers.honeybloom-bear)
```

---

## Hook Registration

### Claude Code (settings.json at ~/.claude/settings.json)

| Event | Script | Matcher | Timeout | Harness |
|-------|--------|---------|---------|---------|
| PreToolUse | block-aether-db.py | Bash | 5s | Claude Code only |
| PreToolUse | transcript-protection-hook.py | Bash | 5s | Claude Code only |
| PreToolUse | protect-outbox.py | Bash | 5s | Claude Code only |
| PreToolUse | block-subagents.py | Task | 5s | Both (dual-protocol) |
| UserPromptSubmit | inject-timestamp.sh | — | 5s | Claude Code + Codex |
| PostToolUse | aether-relay.sh | — | 5s | Claude Code only |
| SessionStart | session-start-time.sh | — | 5s | Claude Code only |
| ConfigChange | log-config-change.sh | * | 5s | Claude Code only |

Additionally, `statusline-huddles.sh` is called from the `statusLine` config block (not a hook — a status bar command).

### OpenCode (Medusa plugin at ~/.config/opencode/plugins/medusa.ts)

Medusa handles 3 functions natively via OpenCode's plugin system:
- `tool.execute.before` — Task tool block + transcript protection (replaces block-subagents.py + transcript-protection-hook.py)
- `tool.execute.after` — Aether relay with summaries (replaces aether-relay.sh)
- `experimental.chat.system.transform` — Timestamp injection + pending Aether message delivery (replaces inject-timestamp.sh)

**Pattern 4 warning:** Changes to aether-relay.sh, inject-timestamp.sh, or block-subagents.py may require parallel changes in Medusa (library/medusa/medusa.ts, valaquer/medusa repo). Always check both.

---

## Data Flow

### External Data Sources

| Source | Read By | Purpose |
|--------|---------|---------|
| ORG.md (`library/wiki/Organization/ORG.md`) | kitty-open-teammate.sh, close-tabs.py, failover scripts, reminder-agent.sh | Roster + Groups SSoT |
| `janus-config.csv` | kitty-open-teammate.sh, close-tabs.py, failover scripts, Aether | Harness, model, machine routing |
| Aether API (localhost:51820 or LAN IP) | aether-relay.sh, reminder-agent.sh, kitty-open-teammate.sh, close-tabs.py, bear-watcher.py | Room resolution, tool activity, pulse, activate/deactivate, change notifications |
| macOS Keychain | kitty-open-teammate.sh, mini-launch.sh, vault.py, safe.sh | Passwords and encryption keys |
| Kitty socket (/tmp/honeybloom-kitty-*.sock) | kitty-open-teammate.sh, close-tabs.py, failover scripts, statusline-huddles.sh | Tab discovery and management |
| livemirror-global flag (`library/aether/livemirror-global`) | aether-relay.sh | Live mirror on/off |
| REMINDERS.md (per teammate dir) | reminder-agent.sh | Scheduled reminders |
| iMac Bear DB (via SSH) | bear-watcher.py, mcp-bear/server.py | Note content, change detection, read queries |
| Write ledger (`/var/tmp/bear-write-ledger.json`) | bear-watcher.py (consume), mcp-bear/server.py (write) | Attribution of MCP writes vs Boss edits |
| iMac x-callback-url (via SSH) | mcp-bear/server.py | Bear write/create/edit/delete operations |

### Canonical configuration

Janus has one tracked source of truth: `library/scripts/janus-config.csv`. Lifecycle consumers read it directly; the deleted legacy `rio/` and gestalt CSV links are not part of the runtime path.

---

## Blast Radius Map

### Cross-Repo Dependencies

| This Repo's File | Depends On (External) | Depended On By (External) |
|-------------------|-----------------------|---------------------------|
| kitty-open-teammate.sh | Aether /api/rooms/activate, /api/huddle | Aether (teammate lifecycle), Hanover (SSH routing) |
| close-tabs.py | Aether /api/rooms/deactivate | Aether (deactivation), Hanover (Mini SSH close) |
| aether-relay.sh | Aether /api/tool-activity, /api/active-rooms | Aether (live mirror), Medusa (parallel impl) |
| inject-timestamp.sh | system clock, jq | Medusa (parallel timestamp implementation) |
| mini-launch.sh | NFS mount, Keychain | Hanover (Mini teammate spawning) |
| failover-to-v4.sh / failover-to-46.sh | OpenCode binary, Medusa plugin | Janus (model migration) |
| `janus-config.csv` | — | Janus L3, Aether, kitty-open-teammate.sh, close-tabs.py, failover scripts |
| reminder-agent.sh | Aether /api/pulse, ORG.md | Aether (reminder system) |
| mcp-reddit/server.py | old.reddit.com | ~/.claude.json MCP registration |
| vault.py | SQLCipher binary, Keychain | Felix/Katja vaults |
| safe.sh | Keychain | Felix safe, close-tabs.py (auto-unmount) |
| watermark.py | PyTorch, videoseal | Dante/Sierra workflow |
| bear-watcher.py | iMac SSH (ControlMaster), Aether /api/message, /api/rooms | launchd agent (com.honeybloom.bear-watcher) |
| mcp-bear/server.py | iMac SSH, x-callback-url, write ledger | All 23 teammates' .mcp.json (honeybloom-bear) |

---

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| 6 LEGACY scripts tracked but unused | Low | espanso-base.yml, bw-get.sh, calendar-wake.sh, clean-memory-file-cruft.sh, meeting-status.sh, skills-to-pdf.sh. Candidates for cleanup. |
| Live lifecycle acceptance still needs B13 | Medium | Automated launcher/failover, close, inbox-routing, and disposable Codex-tree tests run before the final Boss-designated live close/relaunch check. |
| Credential filter regex is best-effort | Medium | CRED_REGEX in aether-relay.sh catches known patterns but novel credential formats may leak. FP-12 defense-in-depth. |
| Bear watcher requires Python 3.9 compat | Low | Launchd uses /usr/bin/python3 (3.9.6). No PEP 604 union types (`str | None`), use string annotations instead. |
| Bear reads require iMac SSH (TCC constraint) | Medium | macOS TCC blocks launchd from reading Mini's local Bear DB (`~/Library/Group Containers/`). All reads go via SSH to iMac. |
| Shared SSH ControlMaster socket | Low | bear-watcher.py and mcp-bear/server.py share `/tmp/bear-watcher-ssh`. Connection pooling benefit but single point of failure for SSH. |
