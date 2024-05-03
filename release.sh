#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "$(readlink -f ${BASH_SOURCE[0]})")" &> /dev/null && pwd)"
version="$1"

echo "change version in files"
echo "__version__ = '$version'" > "$script_directory/aki/version.py"
sed -i'.bak' -e "s@^pipx install .*@pipx install https://github.com/4sh/aki/releases/download/$version/aki-$version.tar.gz@" "README.md"
sed -i'.bak' -e "s@^version = .*@version = \"$version\"@" "pyproject.toml"
rm README.md.bak pyproject.toml.bak

echo "poetry build"
poetry build

echo "commit and tag"
git commit --all --message "release $version"
git tag "v$version"

echo "upload $script_directory/dist/aki-$version.tar.gz to a new release $version on https://github.com/4sh/aki/releases"
echo "push for publish docker package"
