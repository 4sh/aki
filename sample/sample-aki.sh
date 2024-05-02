#!/usr/bin/env bash

script_directory="$(cd "$(dirname "$(readlink -f ${BASH_SOURCE[0]})")" &> /dev/null && pwd)"
aki_config_filename="aki.yaml"

# Use aki in PATH or fallback on docker aki
if command -v aki &> /dev/null
then
  aki --file "$script_directory/$aki_config_filename" "$@"
else
  docker run --rm --interactive \
        --volume /var/run/docker.sock:/var/run/docker.sock \
        --volume "$script_directory":"$script_directory" \
        ghcr.io/4sh/aki --file "$script_directory/$aki_config_filename" "$@"
fi
