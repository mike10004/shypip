#!/usr/bin/env python3

import io
import os
import subprocess
from pathlib import Path
from typing import List, Dict
from unittest import TestCase

from shypip import ENV_CACHE
from shypip import ENV_LOG_FILE
from shypip import ENV_POPULARITY
from shypip import FilePypiStatsCache
from shypip import MULTIPLE_SOURCES_MESSAGE_PREFIX
from shypip import Popularity
from shypip import ShypipOptions
from shypip.tests import LocalRepositoryServer
from shypip.tests import VirtualEnv
from shypip.tests import main_file


class MainTest(TestCase):

    VERBOSE_LOG = False
    _common_pip_options = [
        "--require-virtualenv",
        "--disable-pip-version-check",
        "--no-color",
        "--no-input",
        "--no-cache-dir",
    ]

    # noinspection PyMethodMayBeStatic
    def _env(self, more_env: Dict[str, str] = None) -> Dict[str, str]:
        env = dict(os.environ)
        if more_env:
            env.update(more_env)
        return env

    def _shypip_cmd(self, virtual_env: VirtualEnv, args: List[str]) -> List[str]:
        cmd = [
            virtual_env.python(),
            main_file(),
        ]
        cmd += self._common_pip_options
        cmd += args
        return cmd


    def test_install_rejects_ambiguous_dependency(self):
        with VirtualEnv() as virtual_env:
            packages_installed = virtual_env.list_installed_packages()
            shypip_log_file = Path(virtual_env._tempdir.name) / "shypip.log"
            with LocalRepositoryServer() as server:
                server.start()
                repo_url = server.url(host="localhost")
                cmd =  self._shypip_cmd(virtual_env, [
                    "install",
                    "--progress-bar", "off",
                    "sampleproject",
                    "--extra-index-url", repo_url,
                ])
                env = self._env({
                    "SHYPIP_POPULARITY": "-1",  # disable popularity check
                    "SHYPIP_LOG_FILE": str(shypip_log_file)
                })
                proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
                if shypip_log_file.is_file():
                    if self.VERBOSE_LOG:
                        print(Path(shypip_log_file).read_text())
                else:
                    print("no log file created")
                self.assertEqual(1, proc.returncode, f"unexpected exit code from shypip:\n\n{proc.stdout}\n\n{proc.stderr}")
                stderr_lines = [line for line in io.StringIO(proc.stderr)]
                self.assertIn(MULTIPLE_SOURCES_MESSAGE_PREFIX, proc.stderr, f"output does not contain expected error message text ({repr(MULTIPLE_SOURCES_MESSAGE_PREFIX)}; installed: {packages_installed}:\n\n{proc.stderr}")
                self.assertLessEqual(len(stderr_lines), 5, f"expect <= 5 lines of output:\n\n{proc.stderr}")


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
                cmd = self._shypip_cmd(virtual_env, [
                    "install",
                    "--progress-bar", "off",
                    "sampleproject>=1.9.0",
                    "--extra-index-url", repo_url,
                    "--trusted-host", f"localhost:{server.http_server.server_port}",
                ])
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
