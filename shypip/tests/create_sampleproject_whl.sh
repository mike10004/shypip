#!/usr/bin/env bash

set -e

VERSION="$1"
OUTDIR="$PWD"
if [ -n "$2" ] ; then
  OUTDIR="$2"
fi
echo "writing output to $OUTDIR" >&2

git clone https://github.com/pypa/sampleproject.git >/dev/null

pushd sampleproject

SPEC_FILE="pyproject.toml"

if [ ! -f "$SPEC_FILE" ] ; then
  echo "no ${SPEC_FILE} in $PWD" >&2
  find . -maxdepth 1 -type f
  popd
  rm -rf sampleproject
  exit 1
fi

if [ -n "$VERSION" ] ; then
  sed -i "s/version = \".\+\"/version = \"${VERSION}\"/" "$SPEC_FILE"
fi

grep -B1 -A1 "version = " "$SPEC_FILE"

# This makes our build's hash different from the public package's hash
sed -i "s/description = .\+/description = \"A custom built sample project for testing\"/" "$SPEC_FILE"

python3 -m venv venv
source venv/bin/activate
pip install --quiet build
python3 -m build --outdir "${OUTDIR}" >/dev/null

popd >/dev/null

rm -rf sampleproject
