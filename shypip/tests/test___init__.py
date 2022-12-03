#!/usr/bin/env python3

import contextlib
import datetime
import io
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from shypip import FilePypiStatsCache
from shypip import MULTIPLE_SOURCES_MESSAGE_PREFIX
from shypip import Popularity
from shypip import ShyDownloadCommand
from shypip import ShypipOptions
from shypip import _default_cache_dir
from shypip.tests import LocalRepositoryServer


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
        import unittest.mock
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
                ]
                cmd_name, cmd_args = parse_command(pip_args)
                stderr_buffer = io.StringIO()
                with unittest.mock.patch.dict("os.environ", {ShypipOptions.get_related_env_var_name("popularity_threshold"): ""}, clear=True):
                    with contextlib.redirect_stderr(stderr_buffer):
                        exit_code = command.main(cmd_args)
                self.assertEqual(1, exit_code, f"expected exit code:\n\n{stderr_buffer.getvalue()}")
                self.assertIn(MULTIPLE_SOURCES_MESSAGE_PREFIX, stderr_buffer.getvalue())


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


