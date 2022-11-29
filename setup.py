"""A setuptools based setup module.

See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
import pathlib
import os

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="shypip",
    version="0.1.0",
    description="more secure pip for hybrid public-private repository configurations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mike10004/shypip",
    author="Mike Chaberski",  # Optional
    author_email="mac937@nyu.edu",  # Optional
    classifiers=[  # Optional
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
    keywords="development",
    # When your source code is in a subdirectory under the project root, e.g.
    # `src/`, it is necessary to specify the `package_dir` argument.
    #package_dir={"": "src"},  # Optional
    packages=find_packages(where=os.getcwd()),  # Required
    python_requires=">=3.8, <4",
    install_requires=["pip~=22.3.1"],
    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # `pip` to create the appropriate form of executable for the target
    # platform.
    #
    # For example, the following would provide a command called `sample` which
    # executes the function `main` from this package when invoked:
    entry_points={  # Optional
        "console_scripts": [
            "shypip=shypip.main:main",
        ],
    },
    project_urls={  # Optional
        "Bug Reports": "https://github.com/mike10004/shypip/issues",
        "Source": "https://github.com/mike10004/shypip/",
    },
)