# shypip

**shypip** (Secure Hybrid Pip) is a pip wrapper that improves security in 
hybrid public-private repository configurations.

## Installation

### Linux/MacOS

    $ git clone git@github.com/mike10004/shypip.git
    # Activate the virtual environment for your project, or use `python3 -m venv venv` to create one
    $ source $PROJECT_DIR/venv/bin/activate
    (venv) $ pip install ./shypip
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
