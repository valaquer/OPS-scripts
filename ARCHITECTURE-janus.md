# Janus -- ARCHITECTURE

## File Structure

```
library/scripts/
├── janus-config.csv          # Source of truth -- 9-column teammate-model matrix
├── mini-launch.sh            # Reads CSV at launch, selects harness/model per teammate
├── failover-to-46.sh         # Bulk-rewrites CSV to Opus 4.6 / Claude Code
├── failover-to-v4.sh         # Bulk-rewrites CSV to V4 Flash / OpenCode Go

library/aether-app/src/
├── lib/server/kitten.ts      # Reads CSV for inbox routing (OpenCode vs Claude path)
├── routes/api/rooms/+server.ts  # Reads CSV for sidebar model label

library/medusa/
├── medusa.ts                 # Medusa plugin source (GitHub: valaquer/medusa)
                              # Symlinked to ~/.config/opencode/plugins/medusa.ts
                              # 3 hooks: tool.execute.before (block Task + transcript protection),
                              #          tool.execute.after (facade relay),
                              #          experimental.chat.system.transform (timestamp + inbox delivery)

System-level:
├── /Library/Application Support/ClaudeCode/managed-settings.json  # availableModels allowlist (root-owned)
├── ~/.claude/settings.json   # Per-machine model + harness settings
```

## Dependency Graph

```
janus-config.csv (source of truth)
├── mini-launch.sh
│   ├── reads: harness (col 4), provider (col 5), model_api_id (col 8)
│   ├── selects launch path: Claude Code, OpenCode, or Codex
│   └── passes --model flag when model_api_id is non-empty
├── aether-app kitten.ts
│   └── reads: harness column to determine inbox routing (file-based for OpenCode, PTY for Claude/Codex)
├── aether-app rooms/+server.ts
│   └── reads: model column (col 3) for sidebar label
├── failover-to-46.sh
│   └── writes: rewrites all rows to Claude Code / Opus 4.6
└── failover-to-v4.sh
    └── writes: rewrites all rows to OpenCode / V4 Flash

medusa.ts (OpenCode customization layer -- dormant, no teammates on OpenCode)
├── tool.execute.before -- blocks Task tool, transcript protection
├── tool.execute.after -- facade relay (summaries for reads, full for writes)
└── experimental.chat.system.transform -- timestamp injection + Aether inbox delivery
    └── reads /tmp/opencode-inbox-{teammate}.jsonl (written by kitten.ts when harness=OpenCode)

managed-settings.json (allowlist gate)
└── availableModels array must include any model slug before it can be selected
    └── requires sudo to edit (root-owned)

Environment variables (set in shell profile, not in CSV):
├── ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-6[1m]  # Overrides 2.1.222 default of Opus 5
├── DISABLE_AUTOUPDATER=1                              # Prevents CLI auto-update
└── CLAUDE_CODE_OAUTH_TOKEN                            # Bypasses Keychain OAuth refresh
```

## Data Flow

A config change propagates through this path:

1. **CSV edit** -- Rio updates janus-config.csv (teammate row)
2. **Tab close** -- existing session is terminated (close-team.sh or manual)
3. **Tab relaunch** -- open-team.sh → mini-launch.sh reads CSV
4. **Harness selection** -- mini-launch.sh picks Claude Code, OpenCode, or Codex based on harness column
5. **Model override** -- if model_api_id is non-empty, --model flag is passed to the harness binary
6. **Session active** -- teammate runs on the new model/harness until next restart

Aether reads the CSV on each relevant API call (not cached in memory). A CSV change is reflected in the sidebar label and inbox routing on the next page load or message send.

The managed-settings.json allowlist is checked by Claude Code at startup. A new model slug must be added there BEFORE any teammate can select it.

## Blast Radius Map

| Change | Blast radius | Rollback |
|--------|-------------|----------|
| Edit one CSV row | One teammate's next session | Edit the row back, restart tab |
| Edit multiple CSV rows | All affected teammates' next sessions | failover-to-46.sh restores baseline |
| Change ANTHROPIC_DEFAULT_OPUS_MODEL env var | All 26 teammates' model selection on next restart | Restore env var in shell profile |
| Edit managed-settings.json allowlist | Gates which models any teammate can select | sudo-edit to restore previous array |
| npm install -g new CLI version | All 26 teammates pick up new version on next restart | npm install -g previous version |
| Edit mini-launch.sh | All 26 teammates' launch behavior on next restart | git revert the change |
| Edit failover script | Only affects next failover execution | git revert |
| Edit kitten.ts inbox routing | All teammates' message delivery path | Restart Aether dev server after revert |
| Edit rooms/+server.ts sidebar label | All teammates' sidebar model display | Restart Aether dev server after revert |
| Edit medusa.ts | All OpenCode teammates' org-specific behavior (currently none) | git revert + verify symlink intact |

## Known Issues

See RUNBOOK (runbook-janus-coding) KNOWN ISSUES and FAILED ATTEMPTS tables for the canonical list.
