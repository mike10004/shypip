#!/usr/bin/env python3

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
                self.assertEqual("Local repository for testing", content.strip())
