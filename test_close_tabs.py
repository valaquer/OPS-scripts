import importlib.util
import pathlib
import tempfile
import unittest
import subprocess
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("close-tabs.py")
SPEC = importlib.util.spec_from_file_location("close_tabs", MODULE_PATH)
close_tabs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(close_tabs)


class CloseTabsTest(unittest.TestCase):
    def test_current_org_groups_resolve_full_team(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as org:
            org.write("Teammate: rio\nTeammate: chica\nTeammate: natalie\n## Groups\nrio, chica, natalie (host: rio)\n\n## Sidebar Order\n")
            org_path = org.name
        self.addCleanup(pathlib.Path(org_path).unlink)

        with patch.object(close_tabs, "ORG_PATH", org_path):
            groups = close_tabs.parse_groups()

        expected = {"host": "rio", "members": ["rio", "chica", "natalie"]}
        self.assertEqual(groups, [expected])
        self.assertEqual(close_tabs.find_group(groups, "chica"), expected)

    def test_groups_reject_unknown_missing_duplicate_and_invalid_host(self):
        cases = [
            "Teammate: rio\nTeammate: chica\n## Groups\nrio, unknown (host: rio)\n",
            "Teammate: rio\nTeammate: chica\n## Groups\nrio (host: rio)\n",
            "Teammate: rio\nTeammate: chica\n## Groups\nrio, chica (host: rio)\nchica (host: chica)\n",
            "Teammate: rio\nTeammate: chica\n## Groups\nrio, chica (host: natalie)\n",
        ]
        for contents in cases:
            with self.subTest(contents=contents), tempfile.NamedTemporaryFile("w", delete=False) as org:
                org.write(contents)
                org_path = org.name
            self.addCleanup(pathlib.Path(org_path).unlink)
            with self.assertRaises(ValueError):
                close_tabs.parse_groups(org_path)

    def test_live_org_has_current_full_roster_and_groups(self):
        groups = close_tabs.parse_groups()
        self.assertEqual(sum(len(group["members"]) for group in groups), 26)
        self.assertEqual(len(groups), 10)

    def test_cleanup_order_includes_codex_descendants_native_and_launcher(self):
        command = close_tabs.build_mini_close_command("rio")

        self.assertIn('record_descendants "$native"', command)
        self.assertLess(command.index('add_target "$native" native'), command.index('add_target "$launcher" launcher'))
        self.assertIn("node\\ /opt/homebrew/bin/codex\\ *", command)
        self.assertIn("fingerprint_of", command)
        self.assertIn('still_target "$pid" && kill -9', command)
        self.assertIn("surviving teammate processes", command)

    def test_cleanup_rejects_altered_teammate_input(self):
        with self.assertRaisesRegex(ValueError, "Invalid teammate name"):
            close_tabs.build_mini_close_command("rio; touch /tmp/bad")

    def test_force_kill_skips_same_command_with_different_start(self):
        definitions = close_tabs.build_mini_close_command("rio").split('targets=""')[0]
        script = definitions + r'''
command_of() { printf /tmp/bin/codex-code-mode-host; }
cwd_of() { printf '%s' "$expected_cwd"; }
is_live() { return 0; }
birth=first-start
birth_of() { printf '%s' "$birth"; }
fp_123=$(fingerprint_of 123)
role_123=descendant
birth=second-start
called=0
kill() { called=1; }
pid=123
still_target "$pid" && kill -9 "$pid" || true
[ "$called" -eq 0 ]
'''
        result = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_remote_survivors_propagate_and_abort_fallback(self):
        result = subprocess.CompletedProcess(
            args=["ssh"], returncode=1, stdout="", stderr="surviving teammate processes: 123"
        )
        with patch.object(close_tabs.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "surviving teammate processes: 123"):
                close_tabs.close_mini_tab("rio")

    def test_remote_none_is_explicit_fallback_status(self):
        result = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="none\n", stderr="")
        with patch.object(close_tabs.subprocess, "run", return_value=result):
            self.assertEqual(close_tabs.close_mini_tab("rio"), "none")

    def test_remote_survivor_failure_aborts_without_local_close_or_notify(self):
        with (
            patch.object(close_tabs.sys, "argv", ["close-tabs.py", "rio"]),
            patch.object(close_tabs, "parse_groups", return_value=[{"host": "rio", "members": ["rio"]}]),
            patch.object(close_tabs, "discover_socket", return_value="unix:/tmp/test.sock"),
            patch.object(close_tabs, "get_machine", return_value="mini"),
            patch.object(close_tabs, "close_mini_tab", side_effect=RuntimeError("surviving teammate processes: 123")),
            patch.object(close_tabs, "close_tab") as close_tab,
            patch.object(close_tabs, "notify_aether") as notify,
        ):
            with self.assertRaisesRegex(RuntimeError, "surviving teammate processes: 123"):
                close_tabs.main()
            close_tab.assert_not_called()
            notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
