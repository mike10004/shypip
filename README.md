# shypip

**shypip** (Secure Hybrid Pip) is a pip wrapper that improves security in 
hybrid public-private repository configurations.

## Installation

### Linux/MacOS

Create a virtual environment and activate it:

    $ python3 -m venv venv   # or python3 -m virtualenv venv
    $ source venv/bin/activate

Install the package from the github repository:

    (venv) $ pip install git+https://github.com/mike10004/shypip.git
    (venv) $ shypip --help  # prints pip help text

### Windows

TODO (not tested on Windows)

## Usage

Usage is exactly the same as `pip`. If the `download` or `install` command is 
executed and a package dependency has installation candidates from multiple
repositories, the installation will fail instead of pip selecting the candidate 
with highest version.

These environment variables are relevant to application behavior:

* SHYPIP_UNTRUSTED - comma delimited list of domains that are untrusted; default is `pypi.org`
* SHYPIP_POPULARITY - minimum number of downloads to be eligible for installation; default is one million
* SHYPIP_CACHE - pypistats cache directory; default is under system temp directory
* SHYPIP_PYPISTATS_API_URL - pypistats API URL; default is `https://pypistats.org/api`
* SHYPIP_MAX_CACHE_AGE - max age in minutes before pypistats cache files are considered stale; default is `1440`
* SHYPIP_DUMP_CONFIG - if 1, print config to standard error and exit
* SHYPIP_PROMPT - canned answer to shypip install permission prompt
* SHYPIP_LOG_FILE - pathname of log file to append to

A package popularity query returns three values: downloads in the last day, 
last week, and last month. If the popularity threshold (value of 
SHYPIP_POPULARITY environment variable) is an integer, then all three values 
must be exceed the threshold value for the threshold to be satisfied. More 
granular control may be exercised by defining the threshold in URL query 
string syntax, e.g. `SHYPIP_POPULARITY='last_day=100&last_week=200'`. To allow 
a threshold to be satisfied by any popularity value instead of all values, use 
the prefix `or:`, e.g. `SHYPIP_POPULARITY='or:last_day=100&last_month=300'`.

## Demonstration

To see how it works, you can set up a local repository that you consider "trusted" and
populate it with versions of packages that also exist in PyPI. (These instructions assume
you created a virtual environment that has **shypip** installed, as described in the 
**Installation** section above.) Here we create a local repository that contains a 
single package, `sampleproject` version 1.3.0. The public repository has many other 
versions, including version 1.3.1. We will demonstrate the use of shypip in the common
use case where a project declares a loose dependency `sampleproject~=1.3.0`, which may 
be satisfied by either version 1.3.0 or version 1.3.1.

    (venv) $ mkdir -p demo/sampleproject
    (venv) $ pip download --no-deps --dest demo/sampleproject sampleproject==1.3.0
    (venv) $ python -m http.server 8080

That starts an HTTP server to serve your mini repository. Now open another terminal window
to try out **shypip**:

    $ source $VENV_DIR/bin/activate
    $ export SHYPIP_LOG_FILE=/tmp/shypip.log
    $ export SHYPIP_POPULARITY=100
    (venv) $ shypip install 'sampleproject~=1.3.0' --extra-index-url http://localhost:8080/
    Looking in indexes: https://pypi.org/simple, http://localhost:8080/
    shypip: installation candidate sampleproject 1.3.1 from files.pythonhosted.org satisfies popularity threshold; allow (yes/no)? yes
    Collecting sampleproject~=1.3.0
      Downloading sampleproject-1.3.1-py3-none-any.whl (4.2 kB)
    Collecting peppercorn
      Downloading peppercorn-0.6-py3-none-any.whl (4.8 kB)
    Installing collected packages: peppercorn, sampleproject
    Successfully installed peppercorn-0.6 sampleproject-1.3.1

Installation pauses for user input because packages from both private (trusted) 
and public (untrusted) sources are available, and the package from the public 
repository satisfies the (low) popularity threshold of 100. If the user enters 
'yes', the public package is installed fails, and if the user enters 'no', the 
private package is installed.

If any of the following conditions is true, the private package is installed 
without any prompt:

* packages from private and public sources are available, and the private
  package version is higher
* packages from private and public sources are available, but the public 
  packages do not satisfy the popularity threshold

# Known Issues

* relies on internal API of pip~=22.3.1, so compatibility is limited
* does not protect against typosquatting or bad dependency declaration; will 
  allow installation of package from public (untrusted) repository if no 
  package that satisfies a requirement is available from the private 
  (trusted) repository

# Background

The code in this repository was produced as part of a project for a computer 
security course. Several people were involved in its design, implementation, 
and evaluation, and for their privacy their names are not included in the 
package metadata file, but their contributions are appreciated.
