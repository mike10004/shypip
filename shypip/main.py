#!/usr/bin/env python3
import logging
import os
import sys
import urllib.parse
from pathlib import Path
from collections import defaultdict
from optparse import Values

import pip
# noinspection PyProtectedMember
from pip._internal.models.search_scope import SearchScope
# noinspection PyProtectedMember
from pip._internal.index.collector import LinkCollector
# noinspection PyProtectedMember
from pip._internal.models.selection_prefs import SelectionPreferences
# noinspection PyProtectedMember
from pip._internal.commands.install import InstallCommand
# noinspection PyProtectedMember
from pip._internal.commands.download import DownloadCommand
from typing import List, Any, Optional
from typing import NamedTuple

# noinspection PyProtectedMember
from pip._internal.index.package_finder import PackageFinder
# noinspection PyProtectedMember
from pip._internal.models.candidate import InstallationCandidate
# noinspection PyProtectedMember
from pip._internal.models.target_python import TargetPython
# noinspection PyProtectedMember
from pip._internal.network.session import PipSession


_PROG = "shypip"
ERR_DEPENDENCY_SECURITY = 2

class ShypipOptions(NamedTuple):

    log_file: str = None

    def log(self, *messages):
        if self.log_file:
            with open(self.log_file, "a") as ofile:
                print(*messages, file=ofile)


_THIS_MODULE = "shypip.main"


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


class ShyPackageFinder(PackageFinder):

    def find_all_candidates(self, project_name: str) -> List[InstallationCandidate]:
        candidates = super().find_all_candidates(project_name)
        if len(candidates) <= 1:
            return candidates
        num_candidates_by_package_repo_domain = defaultdict(int)
        candidates = list(filter(is_package_repo_candidate, candidates))
        for candidate in candidates:
            origin = urllib.parse.urlparse(candidate.link.comes_from)
            num_candidates_by_package_repo_domain[origin.netloc] += 1
        if len(num_candidates_by_package_repo_domain.keys()) > 1:
            counts = ", ".join(f"{count} candidate(s) from {domain}" for domain, count in num_candidates_by_package_repo_domain.items())
            raise MultipleRepositoryCandidatesException(f"multiple possible repository sources for {project_name}: {counts}")
        return candidates


class ShyMixin(object):

    def __init__(self):
        self.getenv = os.getenv
        self._shypip_options = None

    # noinspection PyMethodMayBeStatic
    def _read_shypip_options(self) -> ShypipOptions:
        return ShypipOptions(
            log_file=self.getenv("SHYPIP_LOG_FILE", None)
        )

    def _get_shypip_options(self) -> ShypipOptions:
        if self._shypip_options is None:
            self._shypip_options = self._read_shypip_options()
        return self._shypip_options

    def _log(self, *messages):
        self._get_shypip_options().log(*messages)

    @classmethod
    def create_search_scope(
        cls,
        find_links: List[str],
        index_urls: List[str],
        no_index: bool,
    ) -> SearchScope:
        """
        Create a SearchScope object after normalizing the `find_links`.
        """
        # noinspection PyProtectedMember
        from pip._internal.models.search_scope import normalize_path, has_tls
        import itertools
        logger = logging.getLogger(__name__)
        # Build find_links. If an argument starts with ~, it may be
        # a local file relative to a home directory. So try normalizing
        # it and if it exists, use the normalized version.
        # This is deliberately conservative - it might be fine just to
        # blindly normalize anything starting with a ~...
        built_find_links: List[str] = []
        for link in find_links:
            if link.startswith("~"):
                new_link = normalize_path(link)
                if os.path.exists(new_link):
                    link = new_link
            built_find_links.append(link)

        # If we don't have TLS enabled, then WARN if anyplace we're looking
        # relies on TLS.
        if not has_tls():
            for link in itertools.chain(index_urls, built_find_links):
                parsed = urllib.parse.urlparse(link)
                if parsed.scheme == "https":
                    logger.warning(
                        "pip is configured with locations that require "
                        "TLS/SSL, however the ssl module in Python is not "
                        "available."
                    )
                    break

        return SearchScope(
            find_links=built_find_links,
            index_urls=index_urls,
            no_index=no_index,
        )

    # noinspection PyUnresolvedReferences
    @classmethod
    def create_link_collector(
        cls,
        session: PipSession,
        options: Values,
        suppress_no_index: bool = False,
    ) -> "LinkCollector":
        """
        :param session: The Session to use to make requests.
        :param options: parsed options
        :param suppress_no_index: Whether to ignore the --no-index option
            when constructing the SearchScope object.
        """
        # noinspection PyProtectedMember
        from pip._internal.index.collector import redact_auth_from_url
        logger = logging.getLogger(__name__)
        index_urls = [options.index_url] + options.extra_index_urls
        if options.no_index and not suppress_no_index:
            logger.debug(
                "Ignoring indexes: %s",
                ",".join(redact_auth_from_url(url) for url in index_urls),
            )
            index_urls = []

        # Make sure find_links is a list before passing to create().
        find_links = options.find_links or []

        search_scope = cls.create_search_scope(
            find_links=find_links,
            index_urls=index_urls,
            no_index=options.no_index,
        )
        link_collector = LinkCollector(
            session=session,
            search_scope=search_scope,
        )
        return link_collector

    def _build_shy_package_finder(self,
                              options: Values,
                              session: PipSession,
                              target_python: Optional[TargetPython] = None,
                              ignore_requires_python: Optional[bool] = None) -> PackageFinder:
        # self._log("pip version", pip.__version__, "LinkCollector.__dict__.keys()", sorted(LinkCollector.__dict__.keys()))
        # if not hasattr(LinkCollector, "create"):
        #     import inspect
        #     collector_py_file = Path(inspect.getfile(LinkCollector))
        #     self._log(collector_py_file)
        #     self._log(collector_py_file.read_text())
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
def main(argv1: List[str] = None) -> int:
    import pip._internal.cli.main
    import pip._internal.commands
    from pip._internal.commands import CommandInfo
    pip._internal.commands.commands_dict["install"] = CommandInfo(
        _THIS_MODULE,
        "ShyInstallCommand",
        "Install packages.",
    )
    pip._internal.commands.commands_dict["download"] = CommandInfo(
        _THIS_MODULE,
        "ShyDownloadCommand",
        "Download packages.",
    )
    try:
        return pip._internal.cli.main.main(argv1)
    except DependencySecurityException as e:
        print(f"{_PROG}: {e}", file=sys.stderr)
        return ERR_DEPENDENCY_SECURITY


if __name__ == '__main__':
    exit(main())

