#!/usr/bin/env python3
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "proc"
INTEGRATION_PROCFILE = ROOT / "tests" / "Procfile.integration"


class ProcmanBlackboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pm-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name) / "project"
        self.state_root = Path(self.tmp.name) / "state"
        self.workdir.mkdir()
        self.state_root.mkdir()
        self.procfile = self.workdir / "Procfile"
        self.env = os.environ.copy()
        self.env["PROCMAN_STATE_ROOT"] = str(self.state_root)

    def tearDown(self):
        if self.procfile.exists():
            self.run_proc("down", check=False, timeout=10)

    def write_procfile(self, text):
        self.procfile.write_text(text)

    def run_proc(self, *args, check=True, timeout=10):
        result = subprocess.run(
            [str(PROC), "-f", str(self.procfile), *args],
            cwd=self.workdir,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            self.fail(
                "proc command failed\n"
                f"args: {args!r}\n"
                f"returncode: {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}\n"
                f"daemon logs:\n{self.daemon_logs()}"
            )
        return result

    def daemon_logs(self):
        chunks = []
        for path in sorted(self.state_root.glob("*/daemon.log")):
            try:
                chunks.append(f"== {path} ==\n{path.read_text(errors='replace')}")
            except OSError as exc:
                chunks.append(f"== {path} ==\n<could not read: {exc}>")
        return "\n".join(chunks) if chunks else "<none>"

    def free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def ps_rows(self):
        result = self.run_proc("ps")
        rows = {}
        for line in result.stdout.splitlines():
            if not line or line.startswith("NAME") or line.startswith("-"):
                continue
            match = re.match(
                r"^(?P<name>\S+)\s+"
                r"(?P<status>\S+)\s+"
                r"(?P<pid>\S+)\s+"
                r"(?P<uptime>\S+)\s+"
                r"(?P<tty>yes|no)\s+"
                r"(?P<cmd>.*)$",
                line,
            )
            if match:
                rows[match.group("name")] = match.groupdict()
        return rows

    def wait_until(
        self,
        predicate,
        timeout=5,
        interval=0.1,
        description="condition",
        diagnostics=None,
    ):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except Exception as exc:
                last_error = exc
            time.sleep(interval)
        detail = diagnostics() if diagnostics else ""
        self.fail(
            f"timed out waiting for {description}; last error: {last_error!r}\n"
            f"{detail}"
        )

    def wait_for_status(self, name, expected_prefix, timeout=5):
        def check():
            row = self.ps_rows().get(name)
            if row and row["status"].startswith(expected_prefix):
                return row
            return None

        return self.wait_until(
            check,
            timeout=timeout,
            description=f"{name!r} status {expected_prefix!r}",
            diagnostics=self.process_diagnostics,
        )

    def wait_for_http(self, port):
        def check():
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.5) as resp:
                return resp.status == 200

        return self.wait_until(
            check,
            timeout=5,
            description=f"http server on {port}",
            diagnostics=self.process_diagnostics,
        )

    def wait_for_log_text(self, text, *processes):
        def check():
            result = self.run_proc("log", *processes)
            return result.stdout if text in result.stdout else None

        return self.wait_until(
            check,
            timeout=5,
            description=f"log text {text!r}",
            diagnostics=self.process_diagnostics,
        )

    def process_diagnostics(self):
        ps = self.run_proc("ps", check=False)
        logs = self.run_proc("log", check=False)
        return (
            f"ps stdout:\n{ps.stdout}\n"
            f"ps stderr:\n{ps.stderr}\n"
            f"log stdout:\n{logs.stdout}\n"
            f"log stderr:\n{logs.stderr}\n"
            f"daemon logs:\n{self.daemon_logs()}"
        )

    def test_up_no_tty_records_logs_and_ps_reports_no_tty(self):
        self.write_procfile(
            "once: "
            f"{sys.executable} -c \"print('hello from no tty')\"\n"
        )

        up = self.run_proc("up", "-d", "-T")
        self.assertIn("started  once", up.stdout)

        ps = self.run_proc("ps")
        self.assertIn("NAME", ps.stdout)
        self.assertIn("TTY", ps.stdout)
        self.assertIn("once", ps.stdout)
        self.assertIn("no", ps.stdout)
        self.assertNotIn("NameError", ps.stderr)

        logs = self.run_proc("log")
        self.assertIn("hello from no tty", logs.stdout)
        self.assertIn("[procman] exited with code 0", logs.stdout)

    def test_ps_reports_tty_yes_for_default_pty_process(self):
        self.write_procfile(
            "sleeper: "
            f"{sys.executable} -c \"import time; print('ready'); time.sleep(30)\"\n"
        )

        up = self.run_proc("up", "-d")
        self.assertIn("started  sleeper", up.stdout)

        deadline = time.time() + 5
        last_ps = None
        while time.time() < deadline:
            last_ps = self.run_proc("ps")
            if "running" in last_ps.stdout:
                break
            time.sleep(0.1)

        self.assertIsNotNone(last_ps)
        self.assertIn("sleeper", last_ps.stdout)
        self.assertIn("running", last_ps.stdout)
        self.assertIn("yes", last_ps.stdout)

    def test_start_no_tty_restarts_stopped_process_without_pty(self):
        self.write_procfile(
            "worker: "
            f"{sys.executable} -c \"print('started by proc start -T')\"\n"
        )

        self.run_proc("up", "-d", "-T")
        self.run_proc("stop", "worker", check=False)

        started = self.run_proc("start", "-T", "worker")
        self.assertIn("worker:", started.stdout)

        ps = self.run_proc("ps")
        self.assertIn("worker", ps.stdout)
        self.assertIn("no", ps.stdout)

        logs = self.run_proc("log", "worker")
        self.assertIn("started by proc start -T", logs.stdout)

    def test_real_procfile_processes_work_in_tty_and_no_tty_modes(self):
        for no_tty in (False, True):
            with self.subTest(no_tty=no_tty):
                self.run_proc("down", check=False)
                port = self.free_port()
                self.env["PORT"] = str(port)
                self.write_procfile(INTEGRATION_PROCFILE.read_text())

                up_args = ["up", "-d"]
                start_args = ["start"]
                expected_tty = "yes"
                if no_tty:
                    up_args.append("-T")
                    start_args.append("-T")
                    expected_tty = "no"

                self.run_proc(*up_args)

                web = self.wait_for_status("web", "running")
                ticker = self.wait_for_status("ticker", "running")
                self.assertEqual(expected_tty, web["tty"])
                self.assertEqual(expected_tty, ticker["tty"])
                self.wait_for_http(port)
                self.wait_for_log_text("tick-", "ticker")

                self.run_proc("stop", "ticker")
                ticker = self.wait_for_status("ticker", "exited(")
                self.assertNotEqual("running", ticker["status"])

                self.run_proc(*start_args, "ticker")
                ticker = self.wait_for_status("ticker", "running")
                self.assertEqual(expected_tty, ticker["tty"])

                web_pid = int(web["pid"])
                os.kill(web_pid, signal.SIGKILL)
                web = self.wait_for_status("web", "exited(")
                self.assertIn("exited(-9)", web["status"])

                self.run_proc("start", "web")
                web = self.wait_for_status("web", "running")
                self.assertEqual("yes", web["tty"])
                self.wait_for_http(port)


if __name__ == "__main__":
    unittest.main()
