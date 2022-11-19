#!/usr/bin/env bash
script_directory="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

pushd "$script_directory/.." > /dev/null
poetry run aki --file "$script_directory/aki.yaml" "$@"
popd > /dev/null || true
