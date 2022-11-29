#!/usr/bin/env python3

import contextlib
import io
import os
import platform
import subprocess
from tempfile import TemporaryDirectory
from contextlib import AbstractContextManager
from pathlib import Path
from typing import List, Dict, Tuple
from unittest import TestCase

from shypip import Pathish
from shypip import ENV_CACHE
from shypip import ENV_LOG_FILE
from shypip import ENV_POPULARITY
from shypip import Popularity
from shypip.tests import LocalRepositoryServer
from shypip import ShypipOptions
from shypip import FilePypiStatsCache
from shypip import ShyDownloadCommand


def main_file() -> str:
    this_file = Path(__file__).absolute()
    return str(this_file.parent.parent / "__init__.py")


class VirtualEnvException(Exception):
    pass


class VenvCreator(object):

    def create(self, venv_dir: Pathish):
        raise NotImplementedError("abstract")


def _system_python() -> str:
    import shutil
    python_exe_path = shutil.which("python")
    return str(Path(python_exe_path).resolve())


class SubprocessVenvCreator(VenvCreator):

    def create(self, venv_dir: Pathish):
        proc = subprocess.run([
            _system_python(),
            "-m", "venv",
            str(venv_dir)
        ], capture_output=True, text=True)
        if proc.returncode != 0:
            raise VirtualEnvException(f"failed to create virtual environment in {venv_dir}: {proc.stderr}")


class ModuleVenvCreator(VenvCreator):

    def create(self, venv_dir: Pathish):
        import venv
        venv.main([
            str(venv_dir),
        ])


class VirtualEnv(AbstractContextManager):

    def __init__(self):
        self._tempdir = None
        self._venv_creator = SubprocessVenvCreator()

    def __enter__(self) -> 'VirtualEnv':
        self._tempdir = TemporaryDirectory(prefix="shypiptest_")
        self.venv_dir = Path(self._tempdir.name) / "venv"
        try:
            self._venv_creator.create(self.venv_dir)
            self.install("pip~=22.3.1")
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

    def install(self, requirement: str):
        cmd = [
            self.python(), "-m", "pip", "--quiet", "--no-input", "install", requirement
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise VirtualEnvException(f"pip install exit {proc.returncode}: {proc.stderr}")

    def list_installed_packages(self) -> List[Tuple[str, str]]:
        cmd = [
            self.python(),
            "-m", "pip", "list"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise VirtualEnvException(f"pip list terminated with exit code {proc.returncode}: {proc.stderr}")
        def to_package_spec(line: str):
            package_name, version = line.rstrip().split()
            return package_name, version
        return [to_package_spec(line) for line in io.StringIO(proc.stdout)][2:]


def _maybe_read_text(pathname: Pathish) -> str:
    try:
        with open(pathname, "r") as ifile:
            return ifile.read()
    except FileNotFoundError:
        return ""


class MainTest(TestCase):

    def test_download_find_candidates(self):
        from pip._internal.cli.main_parser import parse_command
        command = ShyDownloadCommand("download", "Download packages.", isolated=False)
        with TemporaryDirectory(prefix="shypiptest_") as tempdir:
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
                    "sampleproject>=1.9.0",
                    "--extra-index-url", server.url(host="localhost"),
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ]
                cmd_name, cmd_args = parse_command(pip_args)
                stderr_buffer = io.StringIO()
                with contextlib.redirect_stderr(stderr_buffer):
                    exit_code = command.main(cmd_args)
                    self.assertEqual(2, exit_code)
                self.assertIn("MultipleRepositoryCandidatesException", stderr_buffer.getvalue())

    # noinspection PyMethodMayBeStatic
    def _env(self, more_env: Dict[str, str] = None) -> Dict[str, str]:
        env = dict(os.environ)
        if more_env:
            env.update(more_env)
        return env

    def test_install_rejects_ambiguous_dependency(self):
        with VirtualEnv() as virtual_env:
            packages_installed = virtual_env.list_installed_packages()
            shypip_log_file = Path(virtual_env._tempdir.name) / "shypip.log"
            with LocalRepositoryServer() as server:
                server.start()
                repo_url = server.url(host="localhost")
                cmd = [
                    virtual_env.python(),
                    main_file(),
                ] + self._common_pip_options() + [
                    "install",
                    "--progress-bar", "off",
                    "sampleproject",
                    "--extra-index-url", repo_url,
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ]
                env = self._env({"SHYPIP_LOG_FILE": str(shypip_log_file)})
                proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
                if shypip_log_file.is_file():
                    print(Path(shypip_log_file).read_text())
                else:
                    print("no log file created")
                self.assertEqual(2, proc.returncode, f"Output from shypip:\n\n{proc.stdout}\n\n{proc.stderr}")
                self.assertIn("MultipleRepositoryCandidatesException", proc.stderr, f"output does not indicate MultipleRepositoryCandidatesException was raised; installed: {packages_installed}")

    @staticmethod
    def _common_pip_options() -> List[str]:
        return [
            "--require-virtualenv",
            "--disable-pip-version-check",
            "--no-color",
            "--no-input",
            "--no-cache-dir",
        ]

    def _prepare_cache_dir(self, cache_dir: Path, package_name: str, popularity: Popularity):
        cache = FilePypiStatsCache(ShypipOptions(
            cache_dir=str(cache_dir),
        ))
        cache.write_popularity(package_name, popularity)
        self.assertIsNotNone(cache.read_cached_popularity(package_name))

    def test_query_popularity(self):
        with VirtualEnv() as virtual_env:
            cache_dir = Path(virtual_env._tempdir.name) / "cache"
            self._prepare_cache_dir(cache_dir, "sampleproject", Popularity(last_day=1, last_week=2, last_month=3))
            log_file = Path(virtual_env._tempdir.name) / "shypip.log"
            with LocalRepositoryServer() as server:
                server.start()
                repo_url = server.url(host="localhost")
                cmd = [
                    virtual_env.python(),
                    main_file(),
                ] + self._common_pip_options() + [
                    "install",
                    "--progress-bar", "off",
                    "sampleproject>=1.9.0",
                    "--extra-index-url", repo_url,
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ]
                env = self._env({
                    ENV_CACHE: str(cache_dir),
                    ENV_LOG_FILE: str(log_file),
                    ENV_POPULARITY: str(100),
                })
                proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
                self.assertEqual(0, proc.returncode, f"subprocess fail: {proc.stderr}")
                installed = virtual_env.list_installed_packages()
                self.assertIn(("sampleproject", "1.9.0"), installed)
                log_file_text = log_file.read_text()
                self.assertIn("cache hit: sampleproject", log_file_text)
