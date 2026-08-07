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

        expected = {"host": "rio", "members": ["rio", "chica", "natalie"], "virtual": False}
        self.assertEqual(groups, [expected])
        self.assertEqual(close_tabs.find_group(groups, "chica"), expected)

    def test_groups_reject_unknown_and_duplicate(self):
        cases = [
            "Teammate: rio\nTeammate: chica\n## Groups\nrio, unknown (host: rio)\n",
            "Teammate: rio\nTeammate: chica\n## Groups\nrio, chica (host: rio)\nchica (host: chica)\n",
        ]
        for contents in cases:
            with self.subTest(contents=contents), tempfile.NamedTemporaryFile("w", delete=False) as org:
                org.write(contents)
                org_path = org.name
            self.addCleanup(pathlib.Path(org_path).unlink)
            with self.assertRaises(ValueError):
                close_tabs.parse_groups(org_path)

    def test_solo_operator_does_not_raise(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as org:
            org.write("Teammate: rio\nTeammate: burt\n## Groups\nrio (host: rio)\n\n## Sidebar Order\n")
            org_path = org.name
        self.addCleanup(pathlib.Path(org_path).unlink)

        with patch.object(close_tabs, "ORG_PATH", org_path):
            groups = close_tabs.parse_groups()
        self.assertEqual(len(groups), 1)
        self.assertIsNone(close_tabs.find_group(groups, "burt"))
        self.assertTrue(close_tabs.is_solo_operator("burt", org_path))
        self.assertFalse(close_tabs.is_solo_operator("rio", org_path))

    def test_virtual_group_member_is_solo(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as org:
            org.write("Teammate: rio\nTeammate: fable\n## Groups\nrio (host: rio)\nrio, fable (host: xl)\n\n## Sidebar Order\n")
            org_path = org.name
        self.addCleanup(pathlib.Path(org_path).unlink)

        with patch.object(close_tabs, "ORG_PATH", org_path):
            groups = close_tabs.parse_groups()
        self.assertEqual(len(groups), 2)
        group = close_tabs.find_group(groups, "fable")
        self.assertIsNotNone(group)
        self.assertTrue(group["virtual"])
        self.assertTrue(close_tabs.is_solo_operator("fable", org_path))

    def test_live_org_has_current_full_roster_and_groups(self):
        groups = close_tabs.parse_groups()
        self.assertEqual(sum(len(group["members"]) for group in groups), 27)
        self.assertEqual(len(groups), 8)

    def test_cleanup_order_includes_codex_descendants_native_and_launcher(self):
        command = close_tabs.build_close_command("rio")

        self.assertIn('record_descendants "$native"', command)
        self.assertLess(command.index('add_target "$native" native'), command.index('add_target "$launcher" launcher'))
        self.assertIn("node\\ /opt/homebrew/bin/codex\\ *", command)
        self.assertIn("fingerprint_of", command)
        self.assertIn('still_target "$pid" && kill -9', command)
        self.assertIn("surviving teammate processes", command)

    def test_cleanup_rejects_altered_teammate_input(self):
        with self.assertRaisesRegex(ValueError, "Invalid teammate name"):
            close_tabs.build_close_command("rio; touch /tmp/bad")

    def test_force_kill_skips_same_command_with_different_start(self):
        definitions = close_tabs.build_close_command("rio").split('targets=""')[0]
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

    def test_process_failure_propagates_from_main(self):
        with (
            patch.object(close_tabs.sys, "argv", ["close-tabs.py", "rio"]),
            patch.object(close_tabs, "parse_groups", return_value=[{"host": "rio", "members": ["rio"], "virtual": False}]),
            patch.object(close_tabs, "discover_socket", return_value="unix:/tmp/test.sock"),
            patch.object(close_tabs, "kill_processes", side_effect=RuntimeError("Process cleanup failed for rio: exit 1")),
            patch.object(close_tabs, "close_tab") as mock_close_tab,
            patch.object(close_tabs, "notify_aether") as mock_notify,
        ):
            with self.assertRaisesRegex(RuntimeError, "Process cleanup failed"):
                close_tabs.main()
            mock_close_tab.assert_not_called()
            mock_notify.assert_not_called()

    def test_solo_operator_closes_only_individual(self):
        killed = []
        def track_kill(name):
            killed.append(name)
            return "none"
        with (
            patch.object(close_tabs.sys, "argv", ["close-tabs.py", "andrea"]),
            patch.object(close_tabs, "parse_groups", return_value=[
                {"host": "rio", "members": ["rio", "chica"], "virtual": False},
            ]),
            patch.object(close_tabs, "discover_socket", return_value=None),
            patch.object(close_tabs, "kill_processes", side_effect=track_kill),
        ):
            close_tabs.main()
        self.assertEqual(killed, ["andrea"])


if __name__ == "__main__":
    unittest.main()
