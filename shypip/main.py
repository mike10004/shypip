#!/usr/bin/env python3

import os
import sys
import urllib.parse
from collections import defaultdict
from optparse import Values

from pip._internal.index.collector import LinkCollector
from pip._internal.models.selection_prefs import SelectionPreferences
# noinspection PyProtectedMember
from pip._internal.commands.install import InstallCommand
from pip._internal.commands.download import DownloadCommand
from typing import List, Any, Optional, Tuple
from typing import NamedTuple

from pip._internal.index.package_finder import PackageFinder
from pip._internal.models.candidate import InstallationCandidate
from pip._internal.models.target_python import TargetPython
from pip._internal.network.session import PipSession


_PROG = "shypip"
ERR_DEPENDENCY_SECURITY = 2

class ShypipOptions(NamedTuple):

    pass


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
        if len(candidates) < 2:
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
        return ShypipOptions()

    def _get_shypip_options(self) -> ShypipOptions:
        if self._shypip_options is None:
            self._shypip_options = self._read_shypip_options()
        return self._shypip_options

    def _build_shy_package_finder(self,
                              options: Values,
                              session: PipSession,
                              target_python: Optional[TargetPython] = None,
                              ignore_requires_python: Optional[bool] = None) -> PackageFinder:
        link_collector = LinkCollector.create(session, options=options)
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

