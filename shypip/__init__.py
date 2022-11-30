#!/usr/bin/env python3

import json
import os
import platform
import sys
import tempfile
import urllib.parse
from datetime import timedelta
from datetime import datetime
from datetime import timezone
from functools import cached_property
from pathlib import Path
from collections import defaultdict
from optparse import Values

# noinspection PyProtectedMember
from pip._internal.utils.hashes import Hashes
# noinspection PyProtectedMember
from pip._vendor.packaging import specifiers
# noinspection PyProtectedMember
from pip._internal.index.collector import LinkCollector
# noinspection PyProtectedMember
from pip._internal.models.selection_prefs import SelectionPreferences
# noinspection PyProtectedMember
from pip._internal.commands.install import InstallCommand
# noinspection PyProtectedMember
from pip._internal.commands.download import DownloadCommand
from typing import List, Any, Optional, Dict, Tuple, TextIO
from typing import NamedTuple
from typing import Union

# noinspection PyProtectedMember
from pip._internal.index.package_finder import PackageFinder, CandidateEvaluator, BestCandidateResult
# noinspection PyProtectedMember
from pip._internal.models.candidate import InstallationCandidate
# noinspection PyProtectedMember
from pip._internal.models.target_python import TargetPython
# noinspection PyProtectedMember
from pip._internal.network.session import PipSession


_PROG = "shypip"
_THIS_MODULE = "shypip"
_ENV_PREFIX = "SHYPIP_"
ENV_UNTRUSTED = f"{_ENV_PREFIX}UNTRUSTED"
ENV_POPULARITY = f"{_ENV_PREFIX}POPULARITY"
ENV_CACHE = f"{_ENV_PREFIX}CACHE"
ENV_LOG_FILE = f"{_ENV_PREFIX}LOG_FILE"
ENV_PYPISTATS_API_URL = f"{_ENV_PREFIX}PYPISTATS_API_URL"
ENV_MAX_CACHE_AGE = f"{_ENV_PREFIX}MAX_CACHE_AGE"
ENV_DUMP_CONFIG = f"{_ENV_PREFIX}DUMP_CONFIG"
Pathish = Union[str, Path]
DEFAULT_MAX_CACHE_AGE = timedelta(hours=24)


class ShypipOptions(NamedTuple):

    untrusted_sources_spec: str = "pypi.org"
    popularity_threshold: str = ""
    cache_dir: str = ""
    pypistats_api_url: str = "https://pypistats.org/api"
    max_cache_age_minutes: str = "1440"
    dump_config: str = ""
    log_file: str = ""

    def log(self, *messages):
        if self.log_file:
            try:
                with open(self.log_file, "a") as ofile:
                    print(*messages, file=ofile)
            except IOError as e:
                print("shypip: log error", type(e), e, file=sys.stderr)

    def untrusted_sources(self) -> Tuple[str]:
        return tuple(s for s in (self.untrusted_sources_spec or "").split(",") if s)

    def is_untrusted(self, candidate: InstallationCandidate):
        if candidate.link.comes_from:
            parsed_origin = urllib.parse.urlparse(candidate.link.comes_from)
            return parsed_origin.netloc in self.untrusted_sources()

    def cache_dir_path(self) -> Path:
        return Path(self.cache_dir or _default_cache_dir())

    def create_pypistats_cache(self) -> 'PypiStatsCache':
        return FilePypiStatsCache(self)

    def is_popularity_check_enabled(self) -> bool:
        try:
            return int(self.popularity_threshold) > 0
        except (TypeError, ValueError):
            return False

    # noinspection PyUnusedLocal
    def is_popularity_satisfied(self, package_name: str, popularity: 'Popularity') -> bool:
        if not self.is_popularity_check_enabled():
            return False
        return popularity.last_day >= int(self.popularity_threshold)

    def max_cache_age(self) -> timedelta:
        try:
            return timedelta(minutes=int(self.max_cache_age_minutes))
        except (TypeError, ValueError):
            return timedelta(hours=24)

    @staticmethod
    def create(getenv = os.getenv) -> 'ShypipOptions':
        return ShypipOptions(
            untrusted_sources_spec=getenv(ENV_UNTRUSTED, "pypi.org"),
            popularity_threshold=getenv(ENV_POPULARITY, ""),
            cache_dir=getenv(ENV_CACHE, _default_cache_dir()),
            pypistats_api_url=getenv(ENV_PYPISTATS_API_URL, "https://pypistats.org/api"),
            max_cache_age_minutes=getenv(ENV_MAX_CACHE_AGE, "1440"),
            dump_config=getenv(ENV_DUMP_CONFIG, ""),
            log_file=getenv(ENV_LOG_FILE, ""),
        )

    def print_config(self, ofile: TextIO = sys.stderr):
        for field in self._fields:
            docstring = ShypipOptions.__dict__[field].__doc__
            env_var_name = docstring.split()[-1]
            value = getattr(self, field)
            print(f"{env_var_name}={value}", file=ofile)


ShypipOptions.untrusted_sources_spec.__doc__ = f"untrusted sources (comma-delimited domains); set by {ENV_UNTRUSTED}"
ShypipOptions.popularity_threshold.__doc__ = f"popularity threshold; set by {ENV_POPULARITY}"
ShypipOptions.cache_dir.__doc__ = f"pypistats cache directory; set by {ENV_CACHE}"
ShypipOptions.pypistats_api_url.__doc__ = f"pypistats API URL; set by {ENV_PYPISTATS_API_URL}"
ShypipOptions.max_cache_age_minutes.__doc__ = f"max age in minutes for trusting pypistats cache data {ENV_MAX_CACHE_AGE}"
ShypipOptions.dump_config.__doc__ = f"flag that specifies program should print config and exit; set by {ENV_DUMP_CONFIG}"
ShypipOptions.log_file.__doc__ = f"pathname of log file to append to; set by {ENV_LOG_FILE}"


class Popularity(NamedTuple):

    last_day: int
    last_week: int
    last_month: int


class PypiStatsResponse(NamedTuple):

    data: Dict[str, Any]
    package: str
    type: str

    def popularity(self) -> Popularity:
        return Popularity(**self.data)


def _default_cache_dir(now: datetime = None) -> Path:
    if platform.system() != "Windows":
        home_cache_dir = Path("~").expanduser() / ".cache" / "shypip"
        if home_cache_dir.is_dir():
            return home_cache_dir
    now = now or datetime.now()
    timestamp = now.strftime("%Y%m%d")
    return Path(tempfile.gettempdir()) / f"shypip-cache-{timestamp}"


class PypiStatsCache(object):

    def query_popularity(self, package_name: str) -> Popularity:
        raise NotImplementedError("abstract")

    @staticmethod
    def is_query_supported(candidate_link_comes_from: str) -> bool:
        # noinspection PyBroadException
        try:
            if candidate_link_comes_from:
                parsed_url = urllib.parse.urlparse(candidate_link_comes_from)
                return parsed_url.netloc == "pypi.org"
        except:
            pass
        return False


class FilePypiStatsCache(PypiStatsCache):

    def __init__(self, shypip_options: ShypipOptions):
        self.shypip_options = shypip_options

    def query_popularity(self, package_name: str) -> Popularity:
        popularity = self.read_cached_popularity(package_name)
        if not popularity:
            popularity = self.fetch_popularity(package_name)
            if popularity:
                self.write_popularity(package_name, popularity)
            else:
                popularity = Popularity(
                    last_week=0,
                    last_day=0,
                    last_month=0,
                )
        return popularity

    def fetch_popularity(self, package_name) -> Optional[Popularity]:
        import urllib.request
        from http.client import HTTPResponse
        url = f"{self.shypip_options.pypistats_api_url}/packages/{package_name}/recent"
        with urllib.request.urlopen(url) as response:
            response: HTTPResponse
            if response.getcode() // 100 == 2:
                rsp_dict = json.loads(response.read().decode('utf8'))
                return PypiStatsResponse(**rsp_dict).popularity()
        return None

    def write_popularity(self, package_name: str, popularity: Popularity):
        popularity_file = self._popularity_file(package_name)
        os.makedirs(popularity_file.parent, exist_ok=True)
        with open(popularity_file, "w") as ofile:
            json.dump(popularity._asdict(), ofile)

    def _popularity_file(self, package_name: str) -> Path:
        # TODO check whether a package_name is always a safe filename stem
        return self.shypip_options.cache_dir_path() / "popularity" / f"{package_name}.json"

    # noinspection PyMethodMayBeStatic
    def _now(self) -> datetime:
        return datetime.now(tz=timezone.utc)

    def _is_fresh(self, stat_mtime: float, max_age: timedelta = None) -> bool:
        max_age = max_age if max_age is not None else self.shypip_options.max_cache_age()
        last_modified = datetime.fromtimestamp(stat_mtime, tz=timezone.utc)
        now = self._now()
        return (now - last_modified) <= max_age

    def read_cached_popularity(self, package_name: str, max_age: timedelta = None) -> Optional[Popularity]:
        popularity_file = self._popularity_file(package_name)
        miss_reason = ""
        try:
            if popularity_file.exists():
                if not self._is_fresh(popularity_file.stat().st_mtime, max_age):
                    return None
                with open(popularity_file, "r") as ifile:
                    popularity_dict = json.load(ifile)
                popularity = Popularity(**popularity_dict)
                self.shypip_options.log("cache hit:", package_name, popularity)
                return popularity
        except (FileNotFoundError, json.JSONDecodeError, TypeError) as e:
            miss_reason = f" ({str(type(e))})"
        self.shypip_options.log(f"cache miss{miss_reason}:", package_name)
        return None


class DependencySecurityException(Exception):
    pass


class MultipleRepositoryCandidatesException(DependencySecurityException):
    pass


def is_package_repo_candidate(candidate: InstallationCandidate):
    if candidate.link.is_file or candidate.link.is_vcs:
        return False
    if not candidate.link.comes_from:
        return False
    origin = urllib.parse.urlparse(candidate.link.comes_from)
    return origin.scheme in {'http', 'https'}


def count_candidate_origins(candidates: List[InstallationCandidate]) -> Dict[str, int]:
    num_candidates_by_package_repo_domain = defaultdict(int)
    candidates = list(filter(is_package_repo_candidate, candidates))
    for candidate in candidates:
        origin = urllib.parse.urlparse(candidate.link.comes_from)
        num_candidates_by_package_repo_domain[origin.netloc] += 1
    return num_candidates_by_package_repo_domain


class ShyMixin(object):

    @cached_property
    def _shypip_options(self) -> ShypipOptions:
        getenv = os.getenv
        if hasattr(self, "_getenv"):
            getenv = self._getenv
        return ShypipOptions.create(getenv)

    def _log(self, *messages):
        self._shypip_options.log(*messages)

    # noinspection PyMethodMayBeStatic
    def _build_shy_package_finder(self,
                              options: Values,
                              session: PipSession,
                              target_python: Optional[TargetPython] = None,
                              ignore_requires_python: Optional[bool] = None) -> PackageFinder:
        link_collector = LinkCollector.create(session, options=options)
        # noinspection PyUnresolvedReferences
        selection_prefs = SelectionPreferences(
            allow_yanked=True,
            format_control=options.format_control,
            allow_all_prereleases=options.pre,
            prefer_binary=options.prefer_binary,
            ignore_requires_python=ignore_requires_python,
        )
        return ShyPackageFinder.create(
            link_collector=link_collector,
            selection_prefs=selection_prefs,
            target_python=target_python,
        )


class ShyCandidateEvaluator(CandidateEvaluator, ShyMixin):

    # noinspection PyMethodMayBeStatic
    def _is_ambiguous(self, candidates: List[InstallationCandidate]):
        candidate_origin_counts = count_candidate_origins(candidates)
        return len(candidate_origin_counts.keys()) > 1

    # noinspection PyMethodMayBeStatic
    def _require_unambiguous(self, candidates: List[InstallationCandidate]):
        if not candidates:
            return
        candidate_origin_counts = count_candidate_origins(candidates)
        project_name = set(candidate.name for candidate in candidates).pop()
        if len(candidate_origin_counts.keys()) > 1:
            counts = ", ".join(f"{count} candidate(s) from {domain}" for domain, count in candidate_origin_counts.items())
            raise MultipleRepositoryCandidatesException(f"multiple possible repository sources for {project_name}: {counts}")

    @cached_property
    def pypistats_cache(self) -> PypiStatsCache:
        return self._shypip_options.create_pypistats_cache()

    def _refilter_candidates(self, candidates: List[InstallationCandidate]) -> List[InstallationCandidate]:
        if not candidates:
            return []
        filtered = []
        package_names = set(candidate.name for candidate in candidates)
        assert len(package_names) == 1, f"expect exactly one package name among {len(candidates)} candidates"
        package_name = package_names.pop()
        popularity = None
        def get_popularity():
            nonlocal popularity
            if popularity is None:
                popularity = self.pypistats_cache.query_popularity(package_name)
            return popularity

        for candidate in candidates:
            if is_package_repo_candidate(candidate):
                if self._shypip_options.is_untrusted(candidate):
                    # ignore if it's from an untrusted source whose popularity can't be queried
                    if self.pypistats_cache.is_query_supported(candidate.link.comes_from):
                        if self._shypip_options.is_popularity_satisfied(package_name, get_popularity()):
                            filtered.append(candidate)
                else:
                    filtered.append(candidate)
            else:
                filtered.append(candidate)
        return filtered

    def compute_best_candidate(
            self,
            candidates: List[InstallationCandidate],
        ) -> BestCandidateResult:
        result = super().compute_best_candidate(candidates)
        if result.best_candidate and self._shypip_options.is_untrusted(result.best_candidate):
            # noinspection PyProtectedMember
            applicable_candidates = result._applicable_candidates
            if self._is_ambiguous(applicable_candidates):
                if self._shypip_options.is_popularity_check_enabled():
                    # refilter applicable candidates using popularity criteria
                    applicable_candidates = self._refilter_candidates(applicable_candidates)
                    best_candidate = self.sort_best_candidate(applicable_candidates)
                else:
                    self._require_unambiguous(applicable_candidates)
                    raise NotImplementedError("BUG: unreachable")
                return BestCandidateResult(
                    candidates,
                    applicable_candidates=applicable_candidates,
                    best_candidate=best_candidate,
                )
        return result


class ShyPackageFinder(PackageFinder):

    def make_candidate_evaluator(
            self,
            project_name: str,
            specifier: Optional[specifiers.BaseSpecifier] = None,
            hashes: Optional[Hashes] = None,
    ) -> CandidateEvaluator:
        """Create a CandidateEvaluator object to use."""
        candidate_prefs = self._candidate_prefs
        return ShyCandidateEvaluator.create(
            project_name=project_name,
            target_python=self._target_python,
            prefer_binary=candidate_prefs.prefer_binary,
            allow_all_prereleases=candidate_prefs.allow_all_prereleases,
            specifier=specifier,
            hashes=hashes,
        )


class ShyInstallCommand(InstallCommand, ShyMixin):

    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)

    def _build_package_finder(self,
                              options: Values,
                              session: PipSession,
                              target_python: Optional[TargetPython] = None,
                              ignore_requires_python: Optional[bool] = None) -> PackageFinder:
        return self._build_shy_package_finder(options, session, target_python, ignore_requires_python)


class ShyDownloadCommand(DownloadCommand, ShyMixin):

    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)

    def _build_package_finder(self,
                              options: Values,
                              session: PipSession,
                              target_python: Optional[TargetPython] = None,
                              ignore_requires_python: Optional[bool] = None) -> PackageFinder:
        return self._build_shy_package_finder(options, session, target_python, ignore_requires_python)



# noinspection PyProtectedMember
def main(argv1: List[str] = None, getenv = os.getenv) -> int:
    shypip_options = ShypipOptions.create(getenv)
    if str(shypip_options.dump_config).lower() in {"1", "true", "yes"}:
        shypip_options.print_config(sys.stderr)
        return 0
    import pip._internal.cli.main
    import pip._internal.commands
    from pip._internal.commands import CommandInfo, commands_dict
    commands_dict["install"] = CommandInfo(
        _THIS_MODULE,
        "ShyInstallCommand",
        "Install packages.",
    )
    commands_dict["download"] = CommandInfo(
        _THIS_MODULE,
        "ShyDownloadCommand",
        "Download packages.",
    )
    return pip._internal.cli.main.main(argv1)


if __name__ == '__main__':
    exit(main())

