# shypip

**shypip** (Secure Hybrid Pip) is a pip wrapper that improves security in 
hybrid public-private repository configurations.

## Installation

### Linux/MacOS

Create a virtual environment and activate it:

    $ python3 -m venv venv   # or python3 -m virtualenv venv; whatever you have available
    $ source venv/bin/activate

Install the package from the github repository:

    (venv) $ pip install wheel git+https://github.com/mike10004/shypip.git
    (venv) $ shypip --help  # prints pip help text

### Windows

TODO

## Usage

Usage is exactly the same as `pip`. If the `download` or `install` command is 
executed and a package dependency has installation candidates from multiple
repositories, the installation will fail instead of pip selecting the candidate 
with highest version.

These environment variables are relevant to application behavior:

* SHYPIP_UNTRUSTED - comma delimited list of domains that are untrusted; default `pypi.org`
* SHYPIP_POPULARITY - minimum number of downloads in last day to be eligible for installation; default is empty, which means popularity is not queried
* SHYPIP_CACHE - pypistats cache directory; default is under system temp directory
* SHYPIP_PYPISTATS_API_URL - pypistats API URL; default is `https://pypistats.org/api`
* SHYPIP_MAX_CACHE_AGE - max age in minutes before pypistats cache files are considered stale; default is `1440`
* SHYPIP_DUMP_CONFIG - if 1, print config to standard error and exit
* SHYPIP_LOG_FILE - pathname of log file to append to


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
    (venv) $ shypip install 'sampleproject~=1.3.0' --extra-index-url http://localhost:8080/
    Looking in indexes: https://pypi.org/simple, http://localhost:8080/
    ERROR: Exception:
    Traceback (most recent call last):
      File "$VENV_DIR/lib/python3.8/site-packages/pip/_internal/cli/base_command.py", line 160, in exc_logging_wrapper
        status = run_func(*args)
    [...]
    shypip.MultipleRepositoryCandidatesException: multiple possible repository sources for sampleproject: 5 candidate(s) from pypi.org, 1 candidate(s) from localhost:8080

Installation fails because there are multiple sources and shypip won't 
allow pip to choose automatically from an untrusted source. 

(TODO: Decide whether we should automatically install from a trusted source.)

We can set a popularity threshold, though, that allows shypip to make a 
decision about what may be installed. In this case, shypip will decide to 
install from the local (trusted) repository because the packages from the 
public repository do not satisfy the popularity threshold

    $ export SHYPIP_POPULARITY=10000000
    $ shypip install sampleproject~=1.3.0 --extra-index-url http://localhost:8080/
    Looking in indexes: https://pypi.org/simple, http://localhost:8080/
    Collecting sampleproject~=1.3.0
      Downloading http://localhost:8080/sampleproject/sampleproject-1.3.0-py2.py3-none-any.whl (4.0 kB)
    Collecting peppercorn
      Using cached peppercorn-0.6-py3-none-any.whl (4.8 kB)
    Installing collected packages: peppercorn, sampleproject
    Successfully installed peppercorn-0.6 sampleproject-1.3.0
    
    $ cat /tmp/shypip.log
    sampleproject best candidate is version 1.3.1
    sampleproject is provided by multiple sources; candidates by origin: {'localhost:8080': [ResolvedPackage(name='sampleproject', version='1.3.0', comes_from='http://localhost:8080/sampleproject/', url='http://localhost:8080/sampleproject/sampleproject-1.3.0-py2.py3-none-any.whl')], 'pypi.org': [ResolvedPackage(name='sampleproject', version='1.3.0', comes_from='https://pypi.org/simple/sampleproject/', ...), ...]}
    cache hit: sampleproject Popularity(last_day=1128, last_week=7099, last_month=28830)
    6  candidates popularity-filtered by threshold 10000000 to 1
    best candidate after filtering: 'sampleproject' candidate (version 1.3.0 at http://localhost:8080/sampleproject/sampleproject-1.3.0-py2.py3-none-any.whl (from http://localhost:8080/sampleproject/))

If we set the popularity threshold low enough, a package from the public 
(untrusted) repository may be selected, as shown below.

    export SHYPIP_POPULARITY=1000
    (venv) $ rm /tmp/shypip.log 
    (venv) $ ./shypip/__init__.py install sampleproject~=1.3.0 --extra-index-url http://localhost:8080/
    Looking in indexes: https://pypi.org/simple, http://localhost:8080/
    Collecting sampleproject~=1.3.0
      Using cached sampleproject-1.3.1-py3-none-any.whl (4.2 kB)
    Collecting peppercorn
      Using cached peppercorn-0.6-py3-none-any.whl (4.8 kB)
    Installing collected packages: peppercorn, sampleproject
    Successfully installed peppercorn-0.6 sampleproject-1.3.1

Above, version 1.3.1 of the package, from the public repository, is resolved 
and installed, because it meets the popularity threshold of 1000 downloads 
in the last day.

    

