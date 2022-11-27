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

