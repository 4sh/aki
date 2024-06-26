#!/usr/bin/env python
import os
import subprocess
import sys
import argparse
import traceback
from functools import reduce
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Set, Union

from docker.errors import DockerException
from dotenv import dotenv_values

import aki._config as config_importer
from aki.action import CopyAction, UseAction, ErrorAction, PyCodeAction, Action, RemoveAction
from aki._colorize import colorize_in_green
from aki.error import ScriptError
from aki._print import print_error, print_info, print_verbose, print_debug_def, print_success, \
    _set_print_verbose, PRINT_VERBOSE
from aki.version import __version__
from aki.volume import AkiVolume, Volume

config: config_importer.Config


def _print_matrix(matrix):
    matrix_array = []
    for column_template, columns_values in matrix:
        matrix_array.append(''.join(column_template).format(*columns_values))

    print_info('\n'.join(matrix_array))


def _fetch_volumes_of_aki_volumes(aki_volume_by_type: Dict[str, AkiVolume], regex_pattern: str = None,
                                  reverse_match: bool = False) -> Dict[str, List[Volume]]:
    """
    Return volumes by aki volume type
    """
    volumes_by_aki_volume_type = {}
    for volume_type, aki_volume in aki_volume_by_type.items():
        volumes_by_aki_volume_type[volume_type] = list(aki_volume.fetch_volumes(regex_pattern, reverse_match))

    return volumes_by_aki_volume_type


def _fetch_current_volume(aki_volume: AkiVolume) -> Union[Volume, None]:
    """
    Fetch volume from volume spec impl. If none try to determine current volume by reading docker compose env file
    """
    current_volume = aki_volume.fetch_current_volume()

    if current_volume:
        return current_volume

    print_verbose('cannot find current volume from spec, try to find it in docker compose env file')
    env_config = _fetch_docker_env()

    if aki_volume.env_variable in env_config:
        current_volume = aki_volume.volume_name_to_volume(env_config[aki_volume.env_variable], is_aki_name=True)
        print_verbose(f'found volume in docker compose env file : {current_volume}')
    else:
        print_verbose(f'volume not found in docker compose env file')

    return current_volume


def _fetch_docker_env() -> Dict[str, str or None]:
    print_verbose(f'loading docker compose env file {config.docker_env}')
    env_path = config.docker_env
    env_config = dotenv_values(env_path)
    print_verbose(f'docker compose env file content : {env_config}')
    return env_config


def _use_volume_not_exists(name: str, volumes_by_type: Dict[str, List[Volume]], aki_volume_by_type: Dict[str, AkiVolume]):
    print_verbose(f'fetching actions')
    current_volume_by_type = {
        volume_type: _fetch_current_volume(volume_spec)
        for volume_type, volume_spec in aki_volume_by_type.items()
    }

    actions = config.use_not_found_action_fn(name, volumes_by_type, current_volume_by_type)
    _execute_action(actions, aki_volume_by_type, f'Cannot find volume with name {name}')


def _execute_action(action_param: Action or List[Action], volumes_spec_by_type: Dict[str, AkiVolume],
                    error_default_message: str):
    print_verbose(f'actions receive {action_param}')
    actions = []
    if isinstance(action_param, Action) or action_param is None:
        actions.append(action_param)
    elif isinstance(action_param, list):
        actions = action_param
    else:
        raise ScriptError(f'object {actions} is not an action or a list of action')

    def filter_type_of_volume_spec_by_type(volume_types: List[str]):
        if volume_types is None or len(volume_types) == 0:
            return volumes_spec_by_type

        return {
            volume_type: volumes_spec
            for volume_type, volumes_spec in volumes_spec_by_type.items()
            if volume_type in volume_types
        }

    for action in actions:
        print_verbose(f'executing action {action}')
        if isinstance(action, CopyAction):
            print_verbose('start action copy')
            copy_volume(filter_type_of_volume_spec_by_type(action.types), action.source, action.destination,
                        action.override, action.switch_to_copy)
            print_verbose('action copy done')
        elif isinstance(action, UseAction):
            print_verbose('start action use')
            use_volume(filter_type_of_volume_spec_by_type(action.types), action.volume)
            print_verbose('action use done')
        elif isinstance(action, RemoveAction):
            print_verbose('start action remove')
            remove_volumes_by_name_or_pattern(filter_type_of_volume_spec_by_type(action.types), action.volumes,
                                              is_pattern=False, reverse_match=False, is_force=False)
            print_verbose('action remove done')
        elif isinstance(action, PyCodeAction):
            print_verbose('start action py')
            new_action = action.execute()
            print_verbose('action py done')
            _execute_action(new_action, volumes_spec_by_type, error_default_message)
        elif isinstance(action, ErrorAction):
            print_verbose('raise error')
            raise ScriptError(action.message or error_default_message)
        else:
            raise ScriptError(error_default_message)


def _ask_user_with_default(message: str, default_yes=True) -> bool:
    """
    Ask user a question, response choice can be yes or no (y or n).
    If response is an empty string then use default choice
    """
    choice = 'Y/n' if default_yes else 'y/N'
    default_choice = 'y' if default_yes else 'n'

    while True:
        print_info(f'{message} [{choice}]', end=' ')
        user_choice = input() or default_choice
        if user_choice.lower() == 'y':
            return True
        elif user_choice.lower() == 'n':
            return False


def _docker_compose_up():
    """
    docker sdk does not support docker compose. Use subprocess module instead
    """
    print_info('Restarting containers')
    docker_command = ['docker-compose'] if config.docker_compose_cli_version == '1' else ['docker', 'compose']

    cmd = [
        *docker_command,
        '--env-file', str(config.docker_env),
        *reduce(lambda f, f2: f+f2, [('--file', str(compose)) for compose in config.docker_compose]),
        'up', '--detach'
    ]

    # Remove any exported docker vars that take priority over .env file
    cmd_env = os.environ.copy()
    for env in _fetch_docker_env():
        print_verbose(f'removing env {env} of docker compose subprocess')
        cmd_env.pop(env, None)

    print_verbose(f'executing command {" ".join(cmd)}')
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=cmd_env)
    print_verbose(f'command done - code {process.returncode} - out : {process.stdout.decode()}')

    if process.returncode != 0:
        raise ScriptError(process.stdout.decode("utf-8"))


def _print_volumes_matrix(aki_volume_by_type: Dict[str, AkiVolume], volumes_to_print: Dict[str, List[Volume]],
                          external_name: bool = False, volumes_to_decorate_by_type: Dict[str, str] = None):
    if volumes_to_decorate_by_type is None:
        volumes_to_decorate_by_type = {
            volume_type: None
            for volume_type, _ in aki_volume_by_type.items()
        }

    matrix_to_print = []

    # Compute volumes in a easier collection for print
    volumes_by_type_by_aki_name: Dict[str, Dict[str, Volume]] = {}
    for volume_type, volumes in volumes_to_print.items():
        for volume in volumes:
            volumes_by_types = volumes_by_type_by_aki_name.setdefault(volume.aki_name, {})
            volumes_by_types.setdefault(volume_type, volume)

    # Calculate column size
    aki_name_column_size = 8
    for aki_name, _ in volumes_by_type_by_aki_name.items():
        aki_name_column_size = max([aki_name_column_size, len(aki_name) + 2])

    if external_name:
        column_size_by_type = {}
        for volume_type in aki_volume_by_type:
            column_size = len(volume_type)
            for _, volume_by_type in volumes_by_type_by_aki_name.items():
                if volume_type in volume_by_type:
                    column_size = max(column_size, len(volume_by_type[volume_type].external_name) + 2)
            column_size_by_type[volume_type] = column_size
    else:
        column_size_by_type: Dict[str, int] = {
            volume_type: len(volume_type) + 2
            for volume_type in aki_volume_by_type
        }

    # Format default line template
    default_aki_column = f'{{:<{aki_name_column_size}}}'
    column_template = default_aki_column + ''.join([f'{{:<{column_size}}}' for column_size in column_size_by_type.values()])
    matrix_to_print.append((column_template, (['VOLUME'] + [key.upper() for key in aki_volume_by_type.keys()])))

    # Compute volumes by aki name and print a line by aki name
    for aki_name in sorted(volumes_by_type_by_aki_name.keys(), key=str.casefold):
        volume_by_type = volumes_by_type_by_aki_name[aki_name]

        # For each type set a tuple that indicate if the volume exist and need to be print in green
        volume_state_by_type = {}

        for volumes_type, volume_spec in aki_volume_by_type.items():
            volume_to_decorate = volumes_to_decorate_by_type[volumes_type]
            decorate = False
            volume = None

            # Check if volume exists and check decorate
            if volumes_type in volume_by_type:
                volume = volume_by_type[volumes_type]
                decorate = volume == volume_to_decorate

            volume_state_by_type.setdefault(volumes_type, (volume, decorate))

        # Template that define column minimum size
        column_template = []
        columns_values = []
        is_line_contains_decorate_volume = False   # If true then the aki name will be colorized too

        # Compute line template for aki name and print
        for volume_type, (volume, decorate) in volume_state_by_type.items():
            if external_name:
                volume_to_print = volume.external_name if volume else "-"
            else:
                volume_to_print = "\U00002714" if volume else "x"

            # Increase template size because we write unicode characters for print the volume name in another color
            column_size = column_size_by_type[volume_type]
            if decorate:
                volume_to_print = colorize_in_green(volume_to_print)
                column_size = column_size + 9
                is_line_contains_decorate_volume = True

            column_template.append(f'{{:<{column_size}}}')
            columns_values.append(volume_to_print)

        # Compute if aki name is colorized
        if is_line_contains_decorate_volume:
            columns_values.insert(0, colorize_in_green(aki_name))
            column_template.insert(0, f'{{:<{aki_name_column_size + 9}}}')
        else:
            columns_values.insert(0, aki_name)
            column_template.insert(0, default_aki_column)

        matrix_to_print.append((column_template, columns_values))
    _print_matrix(matrix_to_print)


def use_volume(aki_volume_by_type: Dict[str, AkiVolume], aki_name_to_use: str):
    print_info(f'Use volume {aki_name_to_use}')
    volumes_by_type = _fetch_volumes_of_aki_volumes(aki_volume_by_type)

    print_verbose(f'volumes : {volumes_by_type}')

    volumes_type_without_target_volume = []
    for volume_type, volumes in volumes_by_type.items():
        has_volume = False
        for volume in volumes:
            if volume.aki_name == aki_name_to_use:
                has_volume = True
                break
        if not has_volume:
            volumes_type_without_target_volume.append(volume_type)

    if len(volumes_type_without_target_volume) == len(aki_volume_by_type.keys()):
        print_verbose(f'volume {aki_name_to_use} does not exists')
        _use_volume_not_exists(aki_name_to_use, volumes_by_type, aki_volume_by_type)
        return
    elif len(volumes_type_without_target_volume) > 0:
        raise ScriptError(f'Cannot use volume {aki_name_to_use} because it does not exist for'
                          f' {", ".join(volumes_type_without_target_volume)}')

    # Check all current volume are not aki volume and all containers are up
    is_already_on_the_volume_and_container_is_up = True
    for volume_type, volumes in volumes_by_type.items():
        aki_volume = aki_volume_by_type[volume_type]
        is_already_on_the_volume_and_container_is_up = is_already_on_the_volume_and_container_is_up and \
            aki_volume.is_container_up() and \
            _fetch_current_volume(aki_volume).aki_name == aki_name_to_use

    if is_already_on_the_volume_and_container_is_up:
        print_success(f'All containers already use the volume {aki_name_to_use}')
        return

    # Load .env file
    env_config = _fetch_docker_env()

    # Replace .env file key
    for volume_type, aki_volume in aki_volume_by_type.items():
        env_config[aki_volume.env_variable] = aki_name_to_use

    print_info(f'Writing {str(config.docker_env)}')
    with open(str(config.docker_env), 'w') as file:
        for key, value in env_config.items():
            file.write(f'{key}={value}\n')

    for _, aki_volume in aki_volume_by_type.items():
        print_info(f'Removing container {aki_volume.container_name}')
        try:
            container = config.docker_client.containers.get(aki_volume.container_name)
            container.stop()
            container.remove()
        except DockerException:
            pass

    _docker_compose_up()
    print_success(f'Containers started')


def print_volumes(aki_volume_by_type: Dict[str, AkiVolume], regex_pattern: str or None, reverse_match: bool = False,
                  external_name: bool = False):
    volumes_by_type = _fetch_volumes_of_aki_volumes(aki_volume_by_type, regex_pattern, reverse_match)

    current_volume_by_type = {
        volume_type: _fetch_current_volume(volume_spec)
        for volume_type, volume_spec in aki_volume_by_type.items()
    }

    print_verbose(f'current volume : {current_volume_by_type}')

    _print_volumes_matrix(aki_volume_by_type, volumes_by_type, external_name, current_volume_by_type)


def copy_volume(aki_volume_by_type: Dict[str, AkiVolume], source: str, destination: str, override_volume: bool,
                use_copied_volume: bool, up_container: bool = True):
    print_verbose(f'copy {source=}, {destination=}, {override_volume=}, {use_copied_volume=}, {up_container=}')

    volumes_by_types = _fetch_volumes_of_aki_volumes(aki_volume_by_type)

    # $current can be use for copy current volume if all container share the same volume name
    if source == '_current':
        source = None
        for _, aki_volume in aki_volume_by_type.items():
            current_volume = _fetch_current_volume(aki_volume).aki_name

            if source and current_volume != source:
                raise ScriptError('Cannot use _current has all containers does not share the same current volume name')
            elif current_volume is None:
                raise ScriptError('Cannot use _current has all containers does not share the same current volume name')
            else:
                source = current_volume
        print_verbose(f'use _current: {source=}')

    for volume_type, aki_volume in aki_volume_by_type.items():
        # Check source exist
        source_volume: Volume = next(filter(lambda v: v.aki_name == source, volumes_by_types[volume_type]), None)
        if not source_volume:
            print_info(f'Volume {source} does not exist for {volume_type}, skip copy')
            continue

        # Stop and remove container because it can mess up copy
        print_info(f'Stopping {aki_volume.container_name}')
        try:
            config.docker_client.containers.get(aki_volume.container_name).stop()
            config.docker_client.containers.get(aki_volume.container_name).remove()
        except DockerException:
            pass

        # Check destination exist
        destination_volume: Volume = next(filter(lambda v: v.aki_name == destination, volumes_by_types[volume_type]), None)
        if destination_volume:
            if override_volume \
                    or _ask_user_with_default(f'Volume {destination} for {volume_type} already exist, override it ?'):
                print_info(f'Remove volume {destination}')
                aki_volume.remove(destination_volume)
            else:
                continue

        # Copy volume
        aki_volume.copy(source_volume, aki_volume.volume_name_to_volume(destination, is_aki_name=True))
        print_success(f'Copy done')
        print_info()

    if use_copied_volume is True:
        use_volume(aki_volume_by_type, destination)
    elif use_copied_volume is None and _ask_user_with_default(f'Switch to volume {destination} ?'):
        use_volume(aki_volume_by_type, destination)
    elif up_container:
        _docker_compose_up()


def remove_volumes_by_name_or_pattern(aki_volume_by_type: Dict[str, AkiVolume], names_or_regex_patterns: List[str],
                                      is_pattern: bool, reverse_match: bool, is_force: bool):
    volumes_to_remove_by_type: Dict[str, List[Volume]] = {
        volume_type: [] for volume_type, _ in aki_volume_by_type.items()
    }

    # Compute volumes to remove
    if is_pattern:
        volumes_set_aki_name_by_type: Dict[str, Set[Volume]] = {
            volume_type: set() for volume_type in aki_volume_by_type
        }

        # Find volume that match pattern, merge in set for unicity
        for regex_pattern in names_or_regex_patterns:
            for volume_type, volumes in _fetch_volumes_of_aki_volumes(aki_volume_by_type, regex_pattern, reverse_match).items():
                if reverse_match:
                    if len(volumes_set_aki_name_by_type[volume_type]) == 0:
                        volumes_set_aki_name_by_type[volume_type] = set(volumes)
                    else:
                        volumes_set_aki_name_by_type[volume_type] = volumes_set_aki_name_by_type[volume_type] & set(volumes)
                else:
                    volumes_set_aki_name_by_type[volume_type] = volumes_set_aki_name_by_type[volume_type] | set(volumes)

        volumes_to_remove_by_type = {
            volume_type: list(volumes) for volume_type, volumes in volumes_set_aki_name_by_type.items()
        }

        if all(map(lambda volume_type: len(volumes_to_remove_by_type[volume_type]) == 0, volumes_to_remove_by_type.keys())):
            print('No volume found')
            return

        # Show volumes and ask user
        _print_volumes_matrix(aki_volume_by_type, volumes_to_remove_by_type)
        print()
        if not (is_force or _ask_user_with_default('Remove those volumes ?', default_yes=False)):
            print("abort")
            return
    else:
        for name in names_or_regex_patterns:
            for volume_type, volumes in _fetch_volumes_of_aki_volumes(aki_volume_by_type, f"^{name}$").items():
                volumes_to_remove_by_type[volume_type] = volumes_to_remove_by_type[volume_type] + volumes

    remove_volumes(aki_volume_by_type, volumes_to_remove_by_type)


def remove_volumes(aki_volume_by_type: Dict[str, AkiVolume], volumes_to_remove_by_type: Dict[str, List[Volume]]):
    for volume_type, aki_volume in aki_volume_by_type.items():
        current_volume = _fetch_current_volume(aki_volume)

        if not current_volume:
            continue

        for volume_to_remove in volumes_to_remove_by_type[volume_type]:
            if volume_to_remove.aki_name == current_volume.aki_name:
                raise ScriptError(f'Volume {volume_to_remove.aki_name} is use by container {volume_type}, '
                                  f'please switch the volume before trying to remove it')

    for volume_type, aki_volume in aki_volume_by_type.items():
        for volume in sorted(volumes_to_remove_by_type[volume_type], key=lambda v: v.aki_name.casefold()):
            aki_volume.remove(volume)


def _parse_and_set_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--volume',
        '-v',
        action='append',
        help=f'filter volumes')

    parser.add_argument(
        '--file',
        '-f',
        type=Path,
        help='configuration file'
    )

    parser.add_argument(
        '--verbose',
        default=False,
        action='store_true'
    )

    # Actions (sub parser)
    action_parser = parser.add_subparsers(dest='action', required=True, help='actions')

    ls_parser = action_parser.add_parser('ls', help='list existing volumes. Volume used are print in red.')
    ls_parser.add_argument('regexp', help='filter volume short name with regex pattern', nargs='?')
    ls_parser.add_argument('--long-name', '-l', action='store_true', help='print volume name in docker or path')
    ls_parser.add_argument('--reverse-match', '-r', action='store_true', help='reverse pattern')

    use_parser = action_parser.add_parser('use', help='restart containers with the volume pass in parameter')
    use_parser.add_argument('name', help='volume short name')

    copy_parser = action_parser.add_parser('cp', help='copy volume source to dest')
    copy_parser.add_argument('source', help='source volume short name')
    copy_parser.add_argument('destination', help='destination volume short name')
    copy_parser.add_argument('--override-existing', action='store_true',
                             help='if destination volume exist, remove it and launch copy')
    copy_parser.add_argument('--switch-to-copy', action='store_true', help='restart containers with the copied volume')
    copy_parser.add_argument('--no-switch-to-copy', action='store_true',
                             help='do not ask if you want to switch to the volume and keep the actual one')

    remove_parser = action_parser.add_parser('rm', help='remove volume')
    remove_parser.add_argument('names', nargs='+', help='volume short names')
    remove_parser.add_argument('--regexp', '-e', action='store_true', help='names are considered as regex pattern. Ask before remove unless --force is pass')
    remove_parser.add_argument('--reverse-match', '-r', action='store_true', help='reverse regex pattern')
    remove_parser.add_argument('--force', '-f', action='store_true', help='force remove without ask')

    version_parser = action_parser.add_parser('version', help='print aki version')

    return parser.parse_args()


def main():
    exit_code = 0
    try:
        arguments = _parse_and_set_arguments()

        if arguments.action == 'version':
            print_info(f'aki {__version__}')
            return 0

        global config
        config = config_importer.import_config(arguments.file)

        if arguments.verbose:
            _set_print_verbose(arguments.verbose)

        print_debug_def(lambda: dedent(f'''
            version: {__version__}
            base_path: {config.base_path}
            volumes: {config.aki_volumes}
            docker_compose_paths: {', '.join([str(path) for path in config.docker_compose])}
            docker_env_path: {config.docker_env}
        ''').strip())

        # Filter volumes
        if arguments.volume:
            aki_volume_by_type: Dict[str, AkiVolume] = {}
            for volume_type in arguments.volume:
                volume_spec = config.aki_volumes.get(volume_type)
                if not volume_spec:
                    raise ScriptError(f'Volume {volume_type} does not exist')

                aki_volume_by_type.setdefault(volume_type, volume_spec)
        else:
            aki_volume_by_type = config.aki_volumes

        print_debug_def(lambda: f'filter on volumes {", ".join(aki_volume_by_type.keys())}')

        if arguments.action == 'ls':
            print_volumes(aki_volume_by_type, arguments.regexp, arguments.reverse_match, arguments.long_name)
        elif arguments.action == 'use':
            use_volume(aki_volume_by_type, arguments.name)
        elif arguments.action == 'cp':
            use_copied_volume = None
            if arguments.switch_to_copy:
                use_copied_volume = True
            elif arguments.no_switch_to_copy:
                use_copied_volume = False

            copy_volume(aki_volume_by_type, arguments.source, arguments.destination, arguments.override_existing,
                        use_copied_volume)
        elif arguments.action == 'rm':
            remove_volumes_by_name_or_pattern(aki_volume_by_type, arguments.names, arguments.regexp,
                                              arguments.reverse_match, arguments.force)
    except KeyboardInterrupt:
        print_error('Killed')
        exit_code = 130
    except ScriptError as e:
        if PRINT_VERBOSE:
            traceback.print_exc()
        else:
            print_error(e)
        exit_code = 1
    except Exception as e:
        raise e

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
