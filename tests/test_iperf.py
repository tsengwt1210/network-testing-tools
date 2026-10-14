"""Offline checks: no Tk window, iPerf executable, device, or network is started."""

import datetime
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "iperf" / "iperf_gui.py"
TEST_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("iperf_gui_under_test", SOURCE)
iperf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(iperf)


class CommandTests(unittest.TestCase):
    def test_server_bind_and_client_only_fields(self):
        self.assertEqual(
            iperf.build_iperf_command("Server", " 127.0.0.1 ", "27008", duration="bad"),
            ["iperf3", "-p", "27008", "-i", "1", "--forceflush", "-s", "-B", "127.0.0.1"],
        )

    def test_tcp_defaults_and_udp_options(self):
        self.assertEqual(
            iperf.build_iperf_command("Client", "localhost", "5201"),
            ["iperf3", "-p", "5201", "-i", "1", "--forceflush", "-c", "localhost", "-t", "10"],
        )
        self.assertEqual(
            iperf.build_iperf_command(
                "Client", "127.0.0.1", "5201", "UDP", "30", "4", "100M", "64K", True,
            )[-10:],
            ["-u", "-t", "30", "-P", "4", "-b", "100M", "-w", "64K", "-R"],
        )

    def test_rejects_invalid_ports_and_client_numbers(self):
        for port in ("0", "65536", "-1", "1.5", "５２０１", "abc", ""):
            with self.subTest(port=port), self.assertRaises(ValueError):
                iperf.build_iperf_command("Server", "", port)
        for name in ("duration", "parallel"):
            for value in ("0", "-1", "1.5", "abc", "３"):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    iperf.build_iperf_command("Client", "localhost", "5201", **{name: value})

    def test_client_requires_target_and_allows_empty_optional_numbers(self):
        with self.assertRaises(ValueError):
            iperf.build_iperf_command("Client", "  ", "5201")
        command = iperf.build_iperf_command("Client", "localhost", "5201", duration="", parallel="")
        self.assertNotIn("-t", command)
        self.assertNotIn("-P", command)


class ExecutableAndLogTests(unittest.TestCase):
    def test_local_executable_precedes_path_without_executing_it(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as folder:
            filename = "iperf3.exe" if iperf.os.name == "nt" else "iperf3"
            executable = Path(folder) / filename
            executable.touch()
            with patch.object(iperf.shutil, "which") as find:
                self.assertEqual(iperf.find_iperf_executable(folder), str(executable.resolve()))
                find.assert_not_called()

    def test_path_fallback_and_missing_executable(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as folder:
            with patch.object(iperf.shutil, "which", return_value="path-to-iperf3"):
                self.assertEqual(iperf.find_iperf_executable(folder), "path-to-iperf3")
            with patch.object(iperf.shutil, "which", return_value=None), self.assertRaises(FileNotFoundError):
                iperf.find_iperf_executable(folder)

    def test_identical_timestamps_do_not_overwrite_logs(self):
        now = datetime.datetime(2026, 1, 1, 12, 0, 0)
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as folder:
            first, first_header = iperf.create_log_file("Client", "5201", ["iperf3", "-c", "localhost"], folder, now)
            with open(first, "a", encoding="utf-8") as log:
                log.write("existing output\n")
            second, second_header = iperf.create_log_file("Client", "5201", ["iperf3", "-c", "localhost"], folder, now)
            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).read_text(encoding="utf-8"), first_header + "existing output\n")
            self.assertEqual(Path(second).read_text(encoding="utf-8"), second_header)

    def test_header_exists_before_task_construction(self):
        values = {
            "mode": "Server", "ip": "", "port": "27008", "proto": "TCP",
            "time": "10", "parallel": "1", "bw": "", "win": "", "reverse": False,
        }
        app = SimpleNamespace(notebook=Mock(), instances=[])
        for name, value in values.items():
            setattr(app, f"var_{name}", SimpleNamespace(get=lambda value=value: value))

        def check_header(parent, command, port, log_path, header_text):
            self.assertEqual(Path(log_path).read_text(encoding="utf-8"), header_text)
            self.assertIn("MODE : Server", header_text)
            return Mock()

        with tempfile.TemporaryDirectory(dir=TEST_DIR) as folder, \
                patch.object(iperf, "LOG_DIR", Path(folder)), \
                patch.object(iperf, "find_iperf_executable", return_value="mock-iperf3"), \
                patch.object(iperf, "IperfInstance", side_effect=check_header) as task, \
                patch.object(iperf.messagebox, "showerror", side_effect=AssertionError("Unexpected error dialog")), \
                patch.object(iperf.subprocess, "Popen") as process:
            iperf.App.start_new_task(app)
            task.assert_called_once()
            process.assert_not_called()
            self.assertEqual(len(app.instances), 1)


class ProcessStatusTests(unittest.TestCase):
    def test_launch_oserror_is_reported_and_stop_disabled(self):
        task = SimpleNamespace(
            cmd=["mock-iperf3"], is_running=False, _append_event=Mock(),
            lbl_status=Mock(), btn_stop=Mock(),
        )
        with patch.object(iperf.subprocess, "Popen", side_effect=PermissionError("test launch denied")):
            iperf.IperfInstance.start_process(task)
        self.assertFalse(task.is_running)
        self.assertIn("test launch denied", task._append_event.call_args.args[0])
        task.lbl_status.config.assert_called_with(text="Status: ERROR", fg=iperf.RED)
        task.btn_stop.config.assert_called_with(state="disabled")

    def test_completion_error_and_manual_stop_are_distinct(self):
        for returncode, stopped, read_error, expected in (
            (0, False, None, "COMPLETED"),
            (1, False, None, "ERROR"),
            (1, True, None, "STOPPED"),
            (0, False, "disk full", "ERROR"),
        ):
            with self.subTest(returncode=returncode, stopped=stopped, read_error=read_error):
                task = SimpleNamespace(
                    stop_requested=stopped, lbl_status=Mock(), btn_stop=Mock(), _append_event=Mock(),
                )
                iperf.IperfInstance._finish_process(task, returncode, read_error)
                self.assertEqual(task.lbl_status.config.call_args.kwargs["text"], f"Status: {expected} (exit {returncode})")

    def test_output_is_appended_and_nonzero_exit_is_forwarded(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as folder:
            log_path = Path(folder) / "output.txt"
            log_path.write_text("header\n", encoding="utf-8")
            process = Mock(stdout=io.StringIO("sample output\n"))
            process.wait.return_value = 7
            task = SimpleNamespace(
                log_file=str(log_path), process=process, is_running=True,
                _schedule_ui=Mock(), append_log=Mock(), _finish_process=Mock(),
            )
            iperf.IperfInstance._read_output(task)
            self.assertTrue(log_path.read_text(encoding="utf-8").startswith("header\n"))
            self.assertIn("sample output", log_path.read_text(encoding="utf-8"))
            task._schedule_ui.assert_any_call(task._finish_process, 7, None)
            self.assertFalse(task.is_running)


if __name__ == "__main__":
    unittest.main()
