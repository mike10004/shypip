#!/usr/bin/env python3

"""Common testing utilities."""
import hashlib
import io
import os
import shutil
import socket
import platform
import threading
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer
# noinspection PyUnresolvedReferences,PyProtectedMember
from http.server import _get_best_family
from contextlib import AbstractContextManager
from functools import partial
from typing import Optional, List, Tuple, Any, NamedTuple
from shypip import Pathish
import logging


_log = logging.getLogger(__name__)


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):

    quiet_codes = {HTTPStatus.NOT_FOUND}

    def log_request(self, code='-', size='-'):
        if isinstance(code, HTTPStatus):
            code = code.value
        _log.debug('%s "%s" %s %s', self.address_string(), self.requestline, str(code), str(size))

    def _is_quiet(self, fmt, args: Tuple) -> bool:
        if fmt == "code %d, message %s":
            if len(args) == 2 and isinstance(args[0], HTTPStatus) and args[0] in self.quiet_codes:
                return True
        return False

    def log_error(self, fmt: str, *args: Any):
        if self._is_quiet(fmt, args):
            return
        super().log_error(fmt, *args)


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
        self.tempdir = None
        self.venv_dir = None
        self._venv_creator = SubprocessVenvCreator()

    def __enter__(self) -> 'VirtualEnv':
        return self.create()

    def create(self) -> 'VirtualEnv':
        self.tempdir = TemporaryDirectory(prefix="shypiptest_")
        self.venv_dir = Path(self.tempdir.name) / "venv"
        try:
            self._venv_creator.create(self.venv_dir)
            self.install("pip~=22.3.1")
        except:
            self.tempdir.cleanup()
            raise
        return self

    def cleanup(self):
        if self.tempdir is not None:
            self.tempdir.cleanup()

    def __exit__(self, et, ev, tb):
        self.cleanup()
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


def maybe_read_text(pathname: Pathish) -> str:
    """Read text from a file, if the file exists."""
    try:
        return Path(pathname).read_text("utf-8")
    except FileNotFoundError:
        return ""


class Package(NamedTuple):

    name: str
    version: str
    file: Path
    sha256sum: str

    def publish(self, repo_root: Path):
        directory = repo_root / self.name
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.file, directory / self.file.name)

    @staticmethod
    def create(name: str, version: str, file: Path) -> 'Package':
        h = hashlib.sha256()
        h.update(file.read_bytes())
        sha256sum = h.hexdigest()
        return Package(name, version, file, sha256sum)



def get_package(version: str, name: str = "sampleproject") -> Package:
    packages_dir = Path(__file__).absolute().parent.resolve() / "packages"
    filename = f"{name}-{version}-py3-none-any.whl"
    package_file = packages_dir / filename
    return Package.create(name, version, package_file)





class PipCache(NamedTuple):

    directory: Path

    def find_packages(self, name: str, allow_empty: bool = False) -> List[Package]:
        packages = []
        files = []
        for root, subdirs, filenames in os.walk(self.directory):
            for filename in filenames:
                file = Path(root) / filename
                files.append(file)
                name_prefix = f"{name}-"
                if filename.startswith(name_prefix):
                    version = filename[len(name_prefix):].split("-", maxsplit=1)[0]
                    packages.append(Package.create(name, version, file))
        if not allow_empty and not packages:
            raise ValueError(f"file with name {name} not found among {files}")
        return packages
