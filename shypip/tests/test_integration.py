#!/usr/bin/env python3

import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import List, Dict, NamedTuple, Tuple
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
from shypip.tests import Package
from shypip.tests import get_package
from shypip.tests import InstallReport
from shypip.tests import maybe_read_text

_KNOWN_PUBLIC_131_SHA256SUM = "75bb5bb4e74a1b77dc0cff25ebbacb54fe1318aaf99a86a036cefc86ed885ced"


class PackagePopularity(NamedTuple):

    name: str
    popularity: Popularity

class TestSetup(NamedTuple):

    private_repo_packages: Tuple[Package, ...]
    public_package_popularities: Tuple[PackagePopularity, ...]
    dependency_declaration: str
    popularity_threshold: str
    prompt_answer: str

    def only_private_package(self) -> Package:
        if len(self.private_repo_packages) != 1:
            raise ValueError(f"{len(self.private_repo_packages)} private packages; exactly one required")
        return self.private_repo_packages[0]


class TestResult(NamedTuple):

    proc: subprocess.CompletedProcess
    packages_installed_before: Tuple[Tuple[str, str], ...]
    packages_installed_after: Tuple[Tuple[str, str], ...]
    install_report: InstallReport

    def assert_exit_code(self, test_case: TestCase, expected: int):
        test_case.assertEqual(expected, self.proc.returncode, f"unexpected exit code from shypip:\n\n{self.proc.stdout}\n\n{self.proc.stderr}")

    def assert_nothing_installed(self, test_case: TestCase):
        test_case.assertSetEqual(set(self.packages_installed_before), set(self.packages_installed_after))


class MainTest(TestCase):

    VERBOSE_LOG = False
    _common_pip_options = [
        "--require-virtualenv",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--no-color",
    ]

    def setUp(self):
        self.virtual_env = VirtualEnv().create()
        tempdir = Path(self.virtual_env.tempdir.name)
        self.log_file = tempdir / "shypip.log"
        self.report_file = tempdir / "report.json"
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

    def _shypip_cmd(self, setup: TestSetup, server: LocalRepositoryServer, more_install_args: List[str] = None) -> List[str]:
        cmd = [
            self.virtual_env.python(),
            str(main_file()),
        ]
        cmd += self._common_pip_options
        cmd += [
            "install",
            "--progress-bar", "off",
            "--extra-index-url", server.url(host="localhost"),
            "--report", str(self.report_file),
            setup.dependency_declaration,
        ]
        if more_install_args:
            cmd += more_install_args
        return cmd

    def test_install_publichigher_popular_promptaccept(self):
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.0"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="50",
            prompt_answer="yes",
        )
        passed = False
        result = self._run_shypip(setup)
        try:
            result.assert_exit_code(self, 0)
            self.assertIn(("sampleproject", "1.3.1"), result.packages_installed_after)
            download_info = result.install_report.get_download_info("sampleproject")
            self.assertEqual("files.pythonhosted.org", urllib.parse.urlparse(download_info.get('url')).netloc)
            self.assertEqual(f"sha256={_KNOWN_PUBLIC_131_SHA256SUM}", download_info['archive_info']['hash'], "sha256sum of downloaded package")
            passed = True
        finally:
            self._print_log(not passed)

    def test_install_publichigher_popular_no_input(self):
        """User specifies --no-input."""
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.0"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="50",
            prompt_answer="yes",
        )
        passed = False
        result = self._run_shypip(setup, ["--no-input"])
        try:
            result.assert_exit_code(self, 1)
            result.assert_nothing_installed(self)
            self.assertIn(MULTIPLE_SOURCES_MESSAGE_PREFIX, result.proc.stderr)
            passed = True
        finally:
            self._print_log(not passed)

    def test_install_publichigher_popularitydisabled(self):
        """User specifies --no-input."""
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.0"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="",
            prompt_answer="yes",
        )
        result = self._run_shypip(setup)
        self._assert_private_package_installed(setup, result)
        with open(self.log_file, "r") as ifile:
            log_lines = [line.rstrip() for line in ifile]
            self.assertIn("resolution ambiguous and popularity check disabled", log_lines)

    def test_install_publichigher_popular_promptreject(self):
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.0"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="50",
            prompt_answer="no",
        )
        result = self._run_shypip(setup)
        self._assert_private_package_installed(setup, result)

    def _assert_private_package_installed(self, setup: TestSetup, result: TestResult):
        private_package = setup.only_private_package()
        passed = False
        try:
            result.assert_exit_code(self, 0)
            self.assertIn((private_package.name, private_package.version), result.packages_installed_after)
            download_info = result.install_report.get_download_info("sampleproject")
            self.assertEqual("localhost", urllib.parse.urlparse(download_info.get('url')).netloc.split(':', maxsplit=1)[0])
            self.assertEqual(f"sha256={private_package.sha256sum}", download_info['archive_info']['hash'], "sha256sum of downloaded package")
            passed = True
        finally:
            self._print_log(not passed)

    def test_install_publichigher_unpopular(self):
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.0"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="9999999",
            prompt_answer="no",
        )
        result = self._run_shypip(setup)
        self._assert_private_package_installed(setup, result)

    def test_install_privatehigher(self):
        setup = TestSetup(
            private_repo_packages=(get_package("1.3.2"),),
            public_package_popularities=(PackagePopularity("sampleproject", Popularity(100, 200, 300)),),
            dependency_declaration="sampleproject~=1.3.0",
            popularity_threshold="100",
            prompt_answer="no",
        )
        result = self._run_shypip(setup)
        self._assert_private_package_installed(setup, result)

    def _run_shypip(self, setup: TestSetup, more_install_args: List[str] = None) -> TestResult:
        packages_installed = self.virtual_env.list_installed_packages()
        repo_dir = Path(self.virtual_env.tempdir.name) / "repo"
        repo_dir.mkdir()
        for package in setup.private_repo_packages:
            package.publish(repo_dir)
        for package_name, popularity in setup.public_package_popularities:
            self._prepare_cache_dir(package_name, popularity)
        with LocalRepositoryServer(repo_root=repo_dir) as server:
            server.start()
            cmd =  self._shypip_cmd(setup, server, more_install_args)
            env = self._env({
                ENV_POPULARITY: setup.popularity_threshold,  # disable popularity check
                ENV_PROMPT: setup.prompt_answer,
            })
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            actual_packages_installed = self.virtual_env.list_installed_packages()
            report_text = maybe_read_text(self.report_file)
            return TestResult(
                proc=proc,
                packages_installed_before=tuple(packages_installed),
                packages_installed_after=tuple(actual_packages_installed),
                install_report=InstallReport(report_text),
            )

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

