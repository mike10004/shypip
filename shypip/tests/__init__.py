#!/usr/bin/env python3

"""Common testing utilities."""
import socket
import threading
from pathlib import Path
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer
# noinspection PyUnresolvedReferences,PyProtectedMember
from http.server import _get_best_family
from contextlib import AbstractContextManager
from functools import partial
from typing import Optional
from shypip import Pathish
import logging


_log = logging.getLogger(__name__)


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):

    def log_request(self, code='-', size='-'):
        if isinstance(code, HTTPStatus):
            code = code.value
        _log.debug('%s "%s" %s %s', self.address_string(), self.requestline, str(code), str(size))


# noinspection PyPep8Naming
def build_http_server(directory: Pathish,
         ServerClass=ThreadingHTTPServer,
         protocol="HTTP/1.0", port=8000, bind=None) -> ThreadingHTTPServer:
    """Test the HTTP request handler class.

    This runs an HTTP server on port 8000 (or the port argument).

    """
    handler_class = partial(QuietHTTPRequestHandler, directory=str(directory))
    ServerClass.address_family, addr = _get_best_family(bind, port)

    handler_class.protocol_version = protocol
    return ServerClass(addr, handler_class)


class LocalRepositoryStateException(Exception):
    pass


class LocalRepositoryServer(AbstractContextManager):

    def __init__(self, repo_root: Pathish = None, port: int = 0):
        self.repo_root = Path(repo_root or (Path(__file__).parent / "repo1"))
        self._requested_port = port
        self.http_server: Optional[ThreadingHTTPServer] = None
        self.serving_thread: Optional[threading.Thread] = None

    def __enter__(self) -> 'LocalRepositoryServer':
        if not self.repo_root.is_dir():
            raise ValueError("repository root path must be a directory")
        http_server = build_http_server(
            directory=self.repo_root,
            port = self._requested_port,
            bind = "127.0.0.1",
        )
        self.http_server = http_server
        return self

    def __exit__(self, __exc_type, __exc_value, __traceback):
        self.shutdown()

    def pretty_host(self) -> str:
        host = self.http_server.server_name
        url_host = f'[{host}]' if ':' in host else host
        return url_host

    def url(self, path: str = "/", *more_path_components, **kwargs) -> str:
        all_path_components = [path] + list(more_path_components)
        full_path = '/'.join(all_path_components)
        if not full_path.startswith("/"):
            full_path = "/" + full_path
        if 'host' in kwargs:
            host = kwargs['host']
        else:
            host = self.pretty_host()
        # noinspection HttpUrlsUsage
        scheme = kwargs.get('scheme', 'http')
        return f"{scheme}://{host}:{self.http_server.server_port}{full_path}"

    def start(self) -> 'LocalRepositoryServer':
        http_server = self.http_server
        if http_server is None:
            raise LocalRepositoryStateException("server not created")
        t = threading.Thread(target=http_server.serve_forever)
        self.serving_thread = t
        t.start()
        address = (http_server.server_name, http_server.server_port)
        with socket.create_connection(address):
            pass
        return self

    def shutdown(self, join_timeout: float = None):
        thread = self.serving_thread
        if thread is None:
            return
        http_server = self.http_server
        if http_server is not None:
            try:
                http_server.shutdown()
            finally:
                http_server.server_close()
        thread.join(timeout=join_timeout)
