#!/usr/bin/env python3

"""Tests of shypip.tests.__init__.py"""

import urllib.request
from shypip.tests import LocalRepositoryServer
from unittest import TestCase


class LocalRepositoryServerTest(TestCase):

    def test_start(self):
        with LocalRepositoryServer() as server:
            server.start()
            readme_url = server.url("/README.txt")
            with urllib.request.urlopen(readme_url) as rsp:
                content = rsp.read().decode('utf-8')
                self.assertIn("Local repository for testing", content.strip())
