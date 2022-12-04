#!/usr/bin/env python3

import io
import os
import glob
import datetime
import hashlib
import tempfile
import contextlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import shypip.tests
from shypip import FilePypiStatsCache
from shypip import ENV_POPULARITY
from shypip import Popularity
from shypip import ShyDownloadCommand
from shypip import ShypipOptions
from shypip import _default_cache_dir
from shypip.tests import LocalRepositoryServer
from shypip.tests import environment_context


class DownloadCommandTest(TestCase):

    VERBOSE_LOG = False
    _common_pip_options = [
        "--require-virtualenv",
        "--disable-pip-version-check",
        "--no-color",
        "--no-input",
        "--no-cache-dir",
    ]

    def test_download_find_candidates(self):
        from pip._internal.cli.main_parser import parse_command
        command = ShyDownloadCommand("download", "Download packages.", isolated=False)
        with TemporaryDirectory(prefix="shypiptest_") as tempdir:
            download_dir = Path(tempdir) / "download"
            download_dir.mkdir()
            repo_dir = Path(tempdir) / "repo"
            repo_dir.mkdir()
            package_130 = shypip.tests.get_package(name="sampleproject", version="1.3.0")
            package_130.publish(repo_dir)
            with LocalRepositoryServer(repo_root=repo_dir) as server:
                server.start()
                pip_args = [
                    "--disable-pip-version-check",
                    "--no-color",
                    "--no-input",
                    "--no-cache-dir",
                    "download",
                    "--dest", str(download_dir),
                    "--progress-bar", "off",
                    "--no-deps",
                    "sampleproject~=1.3.0",
                    "--extra-index-url", server.url(host="localhost"),
                ]
                cmd_name, cmd_args = parse_command(pip_args)
                stdout_buffer = io.StringIO()
                stderr_buffer = io.StringIO()
                with environment_context({ENV_POPULARITY: ""}):
                    with contextlib.redirect_stdout(stdout_buffer):
                        with contextlib.redirect_stderr(stderr_buffer):
                            exit_code = command.main(cmd_args)
                self.assertEqual(0, exit_code, f"expected exit code:\n\n{stdout_buffer.getvalue()}\n\n{stderr_buffer.getvalue()}")
                downloaded_files = glob.glob(os.path.join(download_dir, "*.*"))
                self.assertEqual(1, len(downloaded_files), f"expected one file in download dir:\n\n{stdout_buffer.getvalue()}\n\n{stderr_buffer.getvalue()}")
                downloaded_file = downloaded_files.pop()
                with open(downloaded_file, "rb") as ifile:
                    h = hashlib.sha256()
                    h.update(ifile.read())
                    downloaded_hash = h.hexdigest()
                self.assertEqual(package_130.sha256sum, downloaded_hash, "expect hash match of downloaded to private package")




class FilePypiStatsCacheTest(TestCase):

    def test__is_fresh(self):
        cache = FilePypiStatsCache(ShypipOptions(max_cache_age_minutes="1440"))
        with tempfile.TemporaryDirectory() as tempdir:
            pathname = Path(tempdir) / "foo.txt"
            with open(pathname, "wb") as ofile:
                ofile.write(b'')
            actual = cache._is_fresh(pathname.stat().st_mtime)
        self.assertTrue(actual)
        two_days_ago = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=26)
        self.assertFalse(cache._is_fresh(two_days_ago.timestamp()), f"expect not fresh: {two_days_ago}")


class ShypipOptionsTest(TestCase):

    def test_create(self):
        s = ShypipOptions.create({}.get)
        self.assertEqual(ShypipOptions(), s)

    def test__default_cache_dir(self):
        cache_dir_path = _default_cache_dir(no_try_home=True)
        self.assertRegex(cache_dir_path.name, r'^shypip-cache-\d{8}$')

    def test_get_related_environment_variable_name(self):
        from shypip import _ENV_PREFIX
        s = ShypipOptions()
        for field in s._fields:
            actual = ShypipOptions.get_related_env_var_name(field)
            self.assertRegex(actual, f'^{_ENV_PREFIX}[_A-Z]+$')
        with self.assertRaises(KeyError):
            ShypipOptions.get_related_env_var_name("not_a_field")


class PopularityThresholdTest(TestCase):
    def test_evaluate(self):
        from shypip import PopularityThreshold
        last_day_many = PopularityThreshold(Popularity(last_day=1_000_000), all)
        self.assertTrue(last_day_many.evaluate(Popularity(last_day=1_000_001)))
        conjunctive = PopularityThreshold(Popularity(100, 200, 300), all)
        self.assertTrue(conjunctive.evaluate(Popularity(101, 201, 301)))
        self.assertFalse(conjunctive.evaluate(Popularity(101, 201, 299)))
        disjunctive = PopularityThreshold(Popularity(100, 200, 300), any)
        self.assertTrue(disjunctive.evaluate(Popularity(last_week=201)))
        self.assertFalse(disjunctive.evaluate(Popularity(1, 2, 3)))


