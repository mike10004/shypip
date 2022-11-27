#!/usr/bin/env python3

import requests

from shypip.tests import LocalRepositoryServer
from unittest import TestCase



class LocalRepositoryServerTest(TestCase):

    def test_start(self):
        with LocalRepositoryServer() as server:
            server.start()
            readme_url = server.url("/README.txt")
            with requests.get(readme_url) as rsp:
                content = rsp.text
                self.assertEqual("Local repository for testing", content.strip())