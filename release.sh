#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "$(readlink -f ${BASH_SOURCE[0]})")" &> /dev/null && pwd)"
version="$1"

echo "change version in files"
echo "__version__ = '$version'" > "$script_directory/aki/version.py"
sed -i'.bak' -e "s@^pipx install .*@pipx install https://github.com/4sh/aki/releases/download/v$version/aki-$version-py3-none-any.whl@" "README.md"
sed -i'.bak' -e "s@^version = .*@version = \"$version\"@" "pyproject.toml"
rm README.md.bak pyproject.toml.bak

echo "poetry build"
poetry blixbuild

echo "commit and tag"
git commit --all --message "release $version"
git tag "v$version"

echo "upload $script_directory/dist/aki-$version-py3-none-any.whl to a new release $version on https://github.com/4sh/aki/releases"
echo "push for publish version and docker package : git push && git push --tags"
