# Hanover -- Architecture

Mac Mini M4 Pro infrastructure. All 26 teammates run on the Mini. iMac is Boss's display terminal -- Raycast triggers, Safari for Aether UI. The Mini owns all processes and the Kitty terminal.

---

## 1. Directory Structure

Hanover is infrastructure, not an app. Components live across both machines and the OPS-scripts repo.

```
Mac Mini (deepak-macmini@192.168.0.186)
├── /Users/deepak-macmini/honeybloom/          # Local working tree (all teammates)
│   ├── library/scripts/                       # OPS-scripts repo (git: valaquer/OPS-scripts)
│   │   ├── open-team.sh                       # Canonical launcher -- solo + team modes
│   │   ├── close-team.sh                      # Team closer -- validates leader, delegates to close-tabs.py
│   │   ├── close-tabs.py                      # Tab/process closer -- closes all group members
│   │   ├── start-all.sh                       # Full org boot -- all teammates + auto-huddles
│   │   ├── mini-launch.sh                     # Per-teammate launcher (harness, wakeup, keychain)
│   │   ├── sync-screenshots.sh                # rsync iMac→Mini screenshots
│   │   ├── sync-postal-mail.sh                # rsync iMac→Mini postal mail
│   │   ├── unlock-keychain.sh                 # Keychain unlock for SSH sessions
│   │   ├── vault-auto-commit.sh               # Hourly vault auto-commit to GitHub
│   │   ├── aether-db-snapshot.sh              # DB snapshot for backups
│   │   ├── calendar-wake.sh                   # Calendar-based teammate auto-wake
│   │   ├── failover-to-46.sh                  # Failover: switch to Opus 4.6
│   │   ├── failover-to-v4.sh                  # Failover: switch to V4 Flash
│   │   ├── janus-config.csv                   # Teammate configuration (model, harness, machine)
│   │   └── hooks/                             # PreToolUse/PostToolUse hooks
│   ├── library/aether-app/                    # Aether SvelteKit app (port 51730)
│   └── {teammate}/                            # 26 teammate home directories
├── /Users/deepak-macmini/screenshots/         # Screenshot sync target (from iMac)
├── /Users/deepak-macmini/drop-zone/           # Drop zone (bidirectional sync with iMac)
├── /Users/deepak-macmini/.ssh/
│   ├── id_mini                                # SSH key for iMac→Mini AND Mini→iMac
│   └── config                                 # Aliases: imac → 192.168.0.153
├── /Users/deepak-macmini/Library/LaunchAgents/
│   ├── com.honeybloom.screenshot-sync.plist   # rsync iMac→Mini screenshots (5s interval)
│   ├── com.honeybloom.postal-mail-sync.plist  # rsync iMac→Mini postal mail (5s interval)
│   ├── com.honeybloom.unlock-keychain.plist   # Keychain unlock on boot
│   ├── com.honeybloom.vault-auto-commit.plist # Hourly vault auto-commit
│   ├── com.honeybloom.aether-db-snapshot.plist # DB snapshot
│   ├── com.honeybloom.cdp-tunnel.plist        # SSH tunnel to iMac Chrome CDP (KeepAlive)
│   └── com.honeybloom.markwhen-watch.plist    # Markwhen file watcher (retired)
└── /tmp/
    ├── honeybloom-kitty-*.sock                # Kitty socket (discovered at runtime)
    └── aether-active-teammates.json           # Active teammate roster

iMac (d.patnaik@192.168.0.153)
├── /Users/d.patnaik/
│   ├── screenshots/                           # Boss drops screenshots here → synced to Mini
│   ├── postal-mail/                           # Boss drops postal mail here → synced to Mini
│   ├── drop-zone/                             # Bidirectional sync with Mini
│   ├── raycast-scripts/                       # Raycast Script Commands (Boss's shortcuts)
│   │   ├── kitty-open-teammate.sh             # Thin wrapper → SSH to Mini's open-team.sh
│   │   ├── start-all.sh                       # Full org boot (delegates to Mini)
│   │   ├── leadership-team.sh                 # Leadership huddle launch
│   │   ├── rio-team.sh, guru-team.sh, ...     # Per-team launchers
│   │   ├── +close-team.sh                     # Team closer -- SSH to Mini's close-team.sh
│   │   ├── scr.sh                             # Latest screenshot path → paste
│   │   ├── pst.sh                             # Latest postal mail path → paste
│   │   ├── drp.sh                             # Drop zone message → paste
│   │   ├── open-aether.sh                     # Open Aether in Safari
│   │   ├── open-workbench.sh                  # Open workbench apps in Safari
│   │   └── chrome-cdp.sh                      # Chrome CDP for Playwright
│   └── .ssh/
│       └── id_hanover                         # SSH key for iMac→Mini (no passphrase)
├── /Users/d.patnaik/Library/LaunchAgents/
│   ├── com.honeybloom.drop-zone.plist         # rsync Mini→iMac drop-zone (5s interval)
│   ├── com.honeybloom.drop-zone-reverse.plist # rsync iMac→Mini drop-zone (5s interval)
│   ├── com.honeybloom.config-mirror.plist     # Config mirror
│   ├── com.honeybloom.fable-jsonl-sync.plist  # Fable JSONL sync
│   ├── com.honeybloom.print-shop.plist        # Print shop
│   ├── com.honeybloom.reminder-agent.plist    # Reminder agent
│   └── com.honeybloom.markwhen-watch.plist    # Markwhen watcher (retired)
```

---

## 2. Dependency Graph

### Teammate Launch Chain

```
Boss triggers Raycast on iMac
  → kitty-open-teammate.sh (iMac, 20-line wrapper)
  → SSH to Mini: open-team.sh --solo {name}
  → open-team.sh discovers Kitty socket (/tmp/honeybloom-kitty-*.sock)
  → If Kitty not running: starts Kitty with custom socket name
  → kitten @ launch --tab + set user var teammate={name}
  → mini-launch.sh {name} runs inside the new tab
    → Reads janus-config.csv for harness/model/provider
    → Unlocks Keychain via SSH to iMac (reads ~/.secrets/hanover-keychain)
    → Builds wakeup message
    → Launches claude (or codex/opencode depending on harness)
  → open-team.sh sends POST /api/rooms/activate to Aether
  → If team mode (not --solo): creates huddle via POST /api/huddle
```

### File Sync

```
Mini LaunchAgents:
  com.honeybloom.screenshot-sync (5s)
    → rsync -a --delete iMac:~/screenshots/ → Mini:/Users/deepak-macmini/screenshots/
    → One-way pull, destructive (--delete mirrors deletions)
    
  com.honeybloom.postal-mail-sync (5s)
    → rsync -a iMac:~/postal-mail/ → Mini:/Users/deepak-macmini/honeybloom/felix/postal-mail/
    → One-way pull, non-destructive (no --delete)

iMac LaunchAgents:
  com.honeybloom.drop-zone (5s)
    → rsync -avz Mini:/Users/deepak-macmini/drop-zone/ → iMac:/Users/d.patnaik/drop-zone/
    → Pull: Mini→iMac
    
  com.honeybloom.drop-zone-reverse (5s)
    → rsync -avz iMac:/Users/d.patnaik/drop-zone/ → Mini:/Users/deepak-macmini/drop-zone/
    → Push: iMac→Mini (bidirectional sync)
```

### SSH Connectivity

```
iMac → Mini:
  Key: /Users/d.patnaik/.ssh/id_hanover (no passphrase)
  User: deepak-macmini@192.168.0.186

Mini → iMac:
  Key: /Users/deepak-macmini/.ssh/id_mini
  User: d.patnaik@192.168.0.153
  Alias: ssh imac (configured in ~/.ssh/config)
  
Used by: teammate launching, file sync, keychain unlock, Raycast delegation

CDP Tunnel (Mini → iMac):
  ssh -L 9222:localhost:9222 imac -N
  Managed by: com.honeybloom.cdp-tunnel.plist (KeepAlive)
  ServerAliveInterval: 60s, ExitOnForwardFailure: yes
  Used by: playwright-cdp MCP server (all teammates)
  Error log: /tmp/cdp-tunnel.err
```

### External Dependencies

```
janus-config.csv
  Read by: open-team.sh (tab colors), mini-launch.sh (harness/model), 
           kitten.ts (alive check, harness routing), /api/rooms (model labels)

ORG.md
  Read by: open-team.sh (team groups for huddle creation),
           start-all.sh (team batching),
           close-team.sh (leader validation),
           close-tabs.py (group member resolution)

Kitty (/opt/homebrew/bin/kitten)
  Used by: open-team.sh (tab management), kitten.ts (message delivery),
           all teammate lifecycle operations

Aether (/api/rooms/activate, /api/rooms/deactivate, /api/huddle)
  Called by: open-team.sh (activation + huddle creation),
             end-session skill (deactivation)
```

---

## 3. Data Flow

### Boss Opens a Teammate (Berlin -- iMac Raycast)

```
Boss types teammate name in Raycast on iMac
  → kitty-open-teammate.sh on iMac
  → ssh -i id_hanover deepak-macmini@192.168.0.186 "open-team.sh --solo {name}"
  → Mini: open-team.sh discovers /tmp/honeybloom-kitty-*.sock
  → Mini: kitten @ launch creates tab in Kitty
  → Mini: mini-launch.sh reads janus-config.csv, unlocks Keychain, launches claude
  → Mini: open-team.sh POSTs /api/rooms/activate to Aether
  → Aether: saves room, emits SSE → Boss sees teammate online in sidebar
```

### Boss Opens a Team (Berlin -- iMac Raycast)

```
Boss types team leader name in Raycast
  → rio-team.sh (iMac Raycast script)
  → ssh to Mini: open-team.sh {leader}
  → open-team.sh resolves team members from ORG.md
  → Launches each member via mini-launch.sh (parallel)
  → Creates huddle via POST /api/huddle { action: "start", host, participants }
  → Aether: saves huddle room, auto-wakes members, emits SSE
```

### Boss Opens Everybody (Berlin -- iMac Raycast)

```
Boss runs start-all.sh from iMac Raycast
  → SSH to Mini for each team batch (sequential with sleep 10 between batches)
  → open-team.sh {leader} per team
  → All 26 teammates launch + 8 auto-huddles + leadership huddle
```

### Gunnar Closes a Team (iMac Raycast)

```
Gunnar types leader name in +close-team Raycast command on iMac
  → +close-team.sh on iMac
  → ssh to Mini: close-team.sh {leader}
  → close-team.sh validates leader against ORG.md groups section
  → Delegates to close-tabs.py {leader}
  → close-tabs.py resolves group members from ORG.md
  → For each member: closes Kitty tab, kills claude process, POSTs /api/rooms/deactivate, unmounts safe
```

### Boss Opens a Teammate (India -- Mini Raycast)

```
Boss uses Mini's local Raycast
  → open-team.sh runs locally (no SSH needed)
  → Same flow as above but hostname check skips SSH
```

### File Drop (Screenshot)

```
Boss takes screenshot on iMac → saves to ~/screenshots/
  → com.honeybloom.screenshot-sync fires within 5s
  → rsync pulls new file to Mini:/Users/deepak-macmini/screenshots/
  → Boss runs scr Raycast script
  → Script SSHes to Mini: ls -t screenshots/ | head -1
  → Pastes "pick up the latest screenshot at {path}" into Aether input bar
  → Boss hits Enter → teammate reads file at the specified path
```

---

## 4. Blast Radius Map

### open-team.sh
Touches: ALL teammate launches. Changes affect every teammate on every start. Kitty socket discovery, tab creation, huddle creation, Aether activation. If this breaks, no teammates can be opened.

### mini-launch.sh
Touches: per-teammate harness launch. Reads janus-config.csv, unlocks Keychain, starts claude/codex. Changes affect how every individual teammate session initializes.

### start-all.sh
Touches: full org boot. References all team leaders, huddle batching, sleep timings. Exists on BOTH machines -- changes must be synced. Different LAUNCH paths (see constraint 7 in RUNBOOK).

### janus-config.csv
Touches: mini-launch.sh (harness, model, provider), open-team.sh (tab colors), kitten.ts (alive check, harness routing), /api/rooms (sidebar model labels). Changes affect teammate configuration org-wide.

### sync-screenshots.sh / sync-postal-mail.sh
Touches: file availability for Boss→teammate handoffs. Contains hardcoded iMac IP. If IP changes or SSH key changes, sync stops silently (errors redirected to /dev/null or err log).

### close-team.sh / close-tabs.py
Touches: team closing lifecycle. close-team.sh validates leader, delegates to close-tabs.py which closes ALL group members (tabs, processes, Aether rooms, safes). Changes to close-tabs.py affect ALL callers (close-team.sh, close-the-books skill). close-tabs.py reads ORG.md for group resolution -- path must stay in sync if ORG.md moves again.

### iMac Raycast scripts (raycast-scripts/)
Touches: Boss's and Gunnar's interface for launching and closing teammates/teams. The iMac kitty-open-teammate.sh and +close-team.sh are thin wrappers -- changes to open-team.sh and close-team.sh on Mini are the real blast radius. But the LAUNCH path in start-all.sh on iMac must match the iMac's script location.

### SSH keys
Touches: ALL cross-machine operations. id_hanover (iMac→Mini) used by Raycast scripts, sync agents, CDP tunnel. id_mini (Mini→iMac) used by mini-launch.sh (Keychain unlock), sync agents, screenshot/postal-mail scripts.

### Kitty socket (/tmp/honeybloom-kitty-*.sock)
Touches: ALL message delivery (sendToKitty), teammate alive checks (getAliveTeammates), tab lifecycle. Socket is discovered at runtime. If Kitty restarts, the socket path changes and must be re-discovered.

### Hardcoded IPs (192.168.0.153, 192.168.0.186)
Touches: 12+ files across both machines (full list in RUNBOOK Known Issues). DHCP reassignment breaks everything. No DHCP reservation set on router yet.

### CDP tunnel (com.honeybloom.cdp-tunnel.plist)
Touches: Playwright CDP access for all 23 teammates. Forwards localhost:9222 to iMac's Chrome debug port via SSH. Uses id_mini key and `imac` SSH alias. If this breaks, `mcp__playwright-cdp__*` tools fail for everyone (standalone `mcp__playwright__*` tools unaffected). KeepAlive ensures automatic restart.

### Per-teammate .mcp.json (playwright-cdp entry)
Touches: every teammate's MCP server list. The `playwright-cdp` entry in each teammate's `.mcp.json` connects to localhost:9222 (the tunnel endpoint). 1s timeout (`--cdp-timeout=1000`) -- fast fail when Chrome isn't running. If Chrome is off, the MCP server exits silently; tools just don't appear.

### LaunchAgents (both machines)
Touches: file sync (screenshots, postal-mail, drop-zone), vault auto-commit, Keychain unlock, DB snapshots, CDP tunnel. Each agent runs independently. Failure is silent -- most redirect stderr to /dev/null or /tmp/*.err.

---

## 5. Known Issues

### Hardcoded IPs -- no DHCP reservation
All cross-machine operations use hardcoded IPs (iMac: 192.168.0.153, Mini: 192.168.0.186) across 12+ files. A DHCP reassignment after router reboot or Ethernet replug breaks all SSH, sync, and Aether LAN access. Fix: set DHCP reservations on the router. Documented in RUNBOOK Known Issues with full file list.

### start-all.sh two-copy divergence
The script exists on both machines with identical batching logic but different LAUNCH paths. Mini canonical: `LAUNCH="open-team.sh"`. iMac Raycast: `LAUNCH="kitty-open-teammate.sh"`. Never SCP one over the other without updating LAUNCH. Preferred update: `sed` over SSH.

### Silent sync failures
All rsync sync agents redirect stderr to /dev/null or /tmp/*.err. If SSH key auth breaks, IP changes, or the remote machine is unreachable, sync stops silently. No alerting mechanism for failed syncs.

### Postal-mail sync target mismatch
`sync-postal-mail.sh` syncs to `/Users/deepak-macmini/honeybloom/felix/postal-mail/` (Felix's directory), not to `/Users/deepak-macmini/postal-mail/`. This is because postal mail is a Felix-team feature (finance/corporate). The `pst` Raycast script points to the correct path.

### NFS removed but artifacts may remain
NFS was removed Jun 22 after causing zombie processes. The Mini's `honeybloom/` is now fully local. Do not re-add NFS mounts (constraint 2 in RUNBOOK). The `drop-zone` having identical content on both machines is maintained by bidirectional rsync, not NFS.

### Mini password leaked in session (FP-12)
Mini password was exposed via `kitten @ ls` command output (shows command-line args). Password needs to be changed. Use temp file + read + delete pattern for future password handling.

### No Hanover ARCHITECTURE.md existed before Aug 2
Cross-machine infrastructure -- sync mechanisms, SSH architecture, launchd agents, file paths -- was undocumented. This is the first ARCHITECTURE.md for the project.

---

## Conventions

- All teammate launches go through open-team.sh (canonical launcher)
- SSH keys: id_hanover (iMac→Mini), id_mini (Mini→iMac, also GitHub)
- Kitty socket naming: /tmp/honeybloom-kitty-{random}.sock
- Tab identification: user variable `teammate={name}` set on every tab
- Aether URL: localhost:51730 on Mini, 192.168.0.186:51730 from iMac
- File sync: rsync via launchd, 5-second intervals, SSH key auth
- Credential access: through Burt, never direct security commands
- iMac Raycast scripts are thin wrappers -- real logic lives on Mini
- Update this file after every shipped REQ (R14)
