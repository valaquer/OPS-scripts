import importlib.util
import os
import pathlib
import shutil
import subprocess
import time
import unittest
import uuid


MODULE_PATH = pathlib.Path(__file__).with_name("close-tabs.py")
SPEC = importlib.util.spec_from_file_location("close_tabs_integration", MODULE_PATH)
close_tabs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(close_tabs)


class CodexProcessCleanupIntegrationTest(unittest.TestCase):
    def test_disposable_launcher_native_and_host_tree_has_no_survivors(self):
        fixture_dir = pathlib.Path(
            "/Users/deepak-macmini/honeybloom", f"cleanup-fixture-{uuid.uuid4().hex}"
        )
        fixture_dir.mkdir()
        self.addCleanup(shutil.rmtree, fixture_dir, True)
        bin_dir = fixture_dir / "bin"
        bin_dir.mkdir()
        native = bin_dir / "codex"
        host = bin_dir / "codex-code-mode-host"
        host_source = fixture_dir / "host.c"
        native_source = fixture_dir / "native.c"
        host_source.write_text("#include <unistd.h>\nint main(void){for(;;) pause();}\n")
        native_source.write_text(
            '#include <unistd.h>\n#include <sys/wait.h>\n'
            f'int main(void){{pid_t p=fork();if(p==0)execl("{host}","{host}",(char*)0);'
            'if(p<0)return 2;return waitpid(p,0,0)<0?3:0;}\n'
        )
        subprocess.run(["cc", "-o", host, host_source], check=True, capture_output=True)
        subprocess.run(["cc", "-o", native, native_source], check=True, capture_output=True)

        launcher = subprocess.Popen(
            [
                "node /opt/homebrew/bin/codex fixture",
                "-c",
                f'"{native}" & wait',
            ],
            executable="/bin/bash",
            cwd=fixture_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(self._reap, launcher)

        native_pid = self._wait_for_child(launcher.pid, launcher)
        self.addCleanup(self._terminate_if_alive, native_pid)
        host_pid = self._wait_for_child(native_pid)
        self.addCleanup(self._terminate_if_alive, host_pid)
        command = close_tabs.build_close_command(fixture_dir.name)
        result = subprocess.run(
            ["/bin/bash", "-c", command], capture_output=True, text=True, timeout=10
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "killed")
        launcher.wait(timeout=2)
        for pid in (host_pid, native_pid, launcher.pid):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    @staticmethod
    def _wait_for_child(parent_pid, process=None):
        for _ in range(50):
            if process is not None and process.poll() is not None:
                detail = process.stderr.read().strip() if process.stderr else ""
                raise AssertionError(f"launcher exited {process.returncode}: {detail}")
            result = subprocess.run(
                ["pgrep", "-P", str(parent_pid)], capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.splitlines()[0])
            time.sleep(0.05)
        raise AssertionError(f"process {parent_pid} did not spawn a child")

    @staticmethod
    def _terminate_if_alive(pid):
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    @staticmethod
    def _reap(process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
