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
from shypip import ENV_PROMPT
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
    ]

    def setUp(self):
        self.virtual_env = VirtualEnv().create()
        tempdir = Path(self.virtual_env.tempdir.name)
        self.pip_cache_dir = tempdir / "pip-cache"
        self.pip_cache_dir.mkdir()
        self.log_file = tempdir / "shypip.log"
        self.stats_cache_dir = tempdir / "stats-cache"

    def tearDown(self):
        if hasattr(self, "virtual_env"):
            self.virtual_env.cleanup()

    def _default_env(self) -> Dict[str, str]:
        return {
            ENV_LOG_FILE: str(self.log_file),
            ENV_PROMPT: "no",
            ENV_CACHE: str(self.stats_cache_dir),
        }

    def _env(self, more_env: Dict[str, str] = None) -> Dict[str, str]:
        env = dict(os.environ)
        env.update(self._default_env())
        if more_env:
            env.update(more_env)
        return env

    def _shypip_cmd(self, args: List[str]) -> List[str]:
        cmd = [
            self.virtual_env.python(),
            main_file(),
        ]
        cmd += self._common_pip_options
        cmd += ["--cache-dir", self.pip_cache_dir]
        cmd += args
        return cmd

    def test_install_rejects_ambiguous_dependency(self):
        packages_installed = self.virtual_env.list_installed_packages()
        with LocalRepositoryServer() as server:
            server.start()
            repo_url = server.url(host="localhost")
            cmd =  self._shypip_cmd([
                "install",
                "--progress-bar", "off",
                "sampleproject",
                "--extra-index-url", repo_url,
            ])
            env = self._env({
                "SHYPIP_POPULARITY": "-1",  # disable popularity check
            })
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            passed = False
            try:
                self.assertEqual(1, proc.returncode, f"unexpected exit code from shypip:\n\n{proc.stdout}\n\n{proc.stderr}")
                stderr_lines = [line for line in io.StringIO(proc.stderr)]
                self.assertIn(MULTIPLE_SOURCES_MESSAGE_PREFIX, proc.stderr, f"output does not contain expected error message text ({repr(MULTIPLE_SOURCES_MESSAGE_PREFIX)}; installed: {packages_installed}:\n\n{proc.stderr}")
                self.assertLessEqual(len(stderr_lines), 5, f"expect <= 5 lines of output:\n\n{proc.stderr}")
                actual_packages_installed = self.virtual_env.list_installed_packages()
                self.assertSetEqual(set(packages_installed), set(actual_packages_installed))
                passed = True
            finally:
                self._print_log(not passed)


    def _print_log(self, always: bool = False):
        if always or self.VERBOSE_LOG:
            if self.log_file.is_file():
                print(self.log_file.read_text())
            else:
                print("no log to print")

    def _prepare_cache_dir(self, package_name: str, popularity: Popularity):
        cache = FilePypiStatsCache(ShypipOptions(
            cache_dir=str(self.stats_cache_dir),
        ))
        cache.write_popularity(package_name, popularity)
        self.assertIsNotNone(cache.read_cached_popularity(package_name))

    def test_query_popularity(self):
        self._prepare_cache_dir("sampleproject", Popularity(last_day=1, last_week=2, last_month=3))
        with LocalRepositoryServer() as server:
            server.start()
            repo_url = server.url(host="localhost")
            cmd = self._shypip_cmd([
                "install",
                "--progress-bar", "off",
                "sampleproject>=1.9.0",
                "--extra-index-url", repo_url,
            ])
            env = self._env({
                ENV_POPULARITY: str(100),
            })
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            passed = False
            try:
                self.assertEqual(0, proc.returncode, f"subprocess fail: {proc.stderr}")
                installed = self.virtual_env.list_installed_packages()
                self.assertIn(("sampleproject", "1.9.0"), installed)
                log_file_text = self.log_file.read_text()
                self.assertIn("cache hit: sampleproject", log_file_text)
                passed = True
            finally:
                self._print_log(not passed)
