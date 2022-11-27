#!/usr/bin/env python3
import contextlib
import io
import os
import platform
import subprocess
import venv
from tempfile import TemporaryDirectory
from contextlib import AbstractContextManager
from pathlib import Path
from unittest import TestCase

from shypip import Pathish
from shypip.main import MultipleRepositoryCandidatesException
from shypip.main import ERR_DEPENDENCY_SECURITY
from shypip.tests import LocalRepositoryServer


def main_file() -> str:
    this_file = Path(__file__).absolute()
    return str(this_file.parent.parent / "main.py")


class VirtualEnv(AbstractContextManager):

    def __init__(self):
        self._tempdir = None

    def __enter__(self) -> 'VirtualEnv':
        self._tempdir = TemporaryDirectory()
        self.venv_dir = Path(self._tempdir.name) / "venv"
        try:
            venv.create(
                env_dir=str(self.venv_dir),
                with_pip=True,
            )
        except:
            self._tempdir.cleanup()
            raise
        return self

    def __exit__(self, et, ev, tb):
        if self._tempdir is not None:
            self._tempdir.cleanup()
        super().__exit__(et, ev, tb)

    def python(self) -> str:
        bin_dir = "Scripts" if platform.system() == "Windows" else "bin"
        return str(self.venv_dir / bin_dir / "python")


def _maybe_read_text(pathname: Pathish) -> str:
    try:
        with open(pathname, "r") as ifile:
            return ifile.read()
    except FileNotFoundError:
        return ""


class MainTest(TestCase):

    def test_find_candidates(self):
        from pip._internal.cli.main_parser import parse_command
        from shypip.main import ShyDownloadCommand
        command = ShyDownloadCommand("download", "Download packages.", isolated=False)
        with TemporaryDirectory() as tempdir:
            with LocalRepositoryServer() as server:
                server.start()
                pip_args = [
                    "--disable-pip-version-check",
                    "--no-color",
                    "--quiet",
                    "--no-input",
                    "--no-cache-dir",
                    "download",
                    "--dest", tempdir,
                    "--progress-bar", "off",
                    "sampleproject",
                    "--extra-index-url", server.url(host="localhost"),
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ]
                cmd_name, cmd_args = parse_command(pip_args)
                stderr_buffer = io.StringIO()
                with contextlib.redirect_stderr(stderr_buffer):
                    exit_code = command.main(cmd_args)
                    self.assertEqual(2, exit_code)
                self.assertIn("MultipleRepositoryCandidatesException", stderr_buffer.getvalue())

    def test_rejects_ambiguous_dependency(self):
        with VirtualEnv() as virtual_env:
            #report_file = os.path.join(virtual_env._tempdir.name, "report.json")
            with LocalRepositoryServer() as server:
                server.start()
                repo_url = server.url(host="localhost")
                cmd = [
                    virtual_env.python(),
                    main_file(),
                    "--require-virtualenv",
                    "--disable-pip-version-check",
                    "--no-color",
                    "--no-input",
                    "--no-cache-dir",
                    "install",
                    "--progress-bar", "off",
             #       "--report", report_file,
                    "sampleproject",
                    "--extra-index-url", repo_url,
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(ERR_DEPENDENCY_SECURITY, proc.returncode, f"Output from shypip:\n\n{proc.stdout}\n\n{proc.stderr}")
            #self.assertEqual(1, proc.returncode, f"Output from shypip:\n\n{proc.stdout}\n\n{proc.stderr}")
            # report_text = _maybe_read_text(report_file)
            # print(report_text)