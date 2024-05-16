import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Callable

import docker
import yaml
from docker import DockerClient

from aki.action import CopyAction, UseAction, ErrorAction, ACTION_COPY, ACTION_USE, ACTION_ERROR, \
    ACTION_PY, PyCodeAction, ACTION_RM, RemoveAction, Action
from aki.config_key import ConfigKey
from aki.error import ScriptError
from aki.volume import AkiHostVolume, AkiDockerVolume, KEY_VOLUME_HOST, KEY_VOLUME_DOCKER, AkiVolume, Volume
import aki._dict_parse_utils as dict_parse_utils


@dataclass
class Config:
    docker_client: DockerClient
    base_path: Path
    aki_volumes: Dict[str, AkiVolume]
    docker_compose: List[Path]
    docker_env: Path
    docker_compose_cli_version: str
    use_not_found_action_fn: Callable[[str, Dict[str, List[Volume]], Dict[str, Volume]], List[Action]]

KEY_DOCKER_COMPOSE = ConfigKey('docker_compose')
KEY_DOCKER_COMPOSE_PATH = ConfigKey('path', KEY_DOCKER_COMPOSE.path)
KEY_DOCKER_COMPOSE_ENV = ConfigKey('env', KEY_DOCKER_COMPOSE.path)
KEY_DOCKER_COMPOSE_VERSION = ConfigKey('cli_version', KEY_DOCKER_COMPOSE.path)

KEY_AKI = ConfigKey('aki')

KEY_VOLUMES = ConfigKey('volumes', KEY_AKI.path)
KEY_VOLUME_TYPE = ConfigKey('type', KEY_VOLUMES.path)
KEY_VOLUME_ENV = ConfigKey('env', KEY_VOLUMES.path)
KEY_VOLUME_CONTAINER = ConfigKey('container_name', KEY_VOLUMES.path)
KEY_VOLUME_FOLDER = ConfigKey('folder', KEY_VOLUMES.path)
KEY_VOLUME_EXCLUDE = ConfigKey('exclude', KEY_VOLUMES.path)
KEY_VOLUME_PREFIX = ConfigKey('prefix', KEY_VOLUMES.path)

KEY_USE = ConfigKey('use', KEY_AKI.path)
KEY_USE_NOT_FOUND = ConfigKey('not_found', KEY_USE.path)
KEY_NOT_FOUND_VOLUME_REGEX = ConfigKey('volume_name', KEY_USE_NOT_FOUND.path)
KEY_NOT_FOUND_ACTIONS = ConfigKey('actions', KEY_USE_NOT_FOUND.path)
KEY_NOT_FOUND_ACTIONS_ACTION = ConfigKey('action', KEY_NOT_FOUND_ACTIONS.path)
KEY_NOT_FOUND_ACTIONS_COPY_SOURCE = ConfigKey('source', KEY_NOT_FOUND_ACTIONS.path)
KEY_NOT_FOUND_ACTIONS_USE_VOLUME = ConfigKey('volume', KEY_NOT_FOUND_ACTIONS.path)
KEY_NOT_FOUND_ACTIONS_RM_VOLUMES = ConfigKey('volumes', KEY_NOT_FOUND_ACTIONS.path)


def import_config(yaml_file: Path) -> Config:
    if yaml_file and not yaml_file.exists():
        raise ScriptError(f'No such file or directory: {yaml_file}')
    elif not yaml_file:
        yaml_file = _fetch_default_aki_path()

    with open(yaml_file.resolve(), 'r') as stream:
        config: Dict = yaml.load(stream, Loader=yaml.Loader)

    docker_client: DockerClient = docker.from_env()
    base_path = yaml_file.parent.resolve()
    aki_volumes = _get_volumes_from_config(base_path, config, docker_client)
    docker_composes, docker_env_path, docker_compose_cli_version = _get_docker_compose_from_config(base_path, config)
    use_not_found_action_fn = _create_use_not_found_action_fn_from_config(base_path, config)

    return Config(docker_client, base_path, aki_volumes, docker_composes, docker_env_path, docker_compose_cli_version,
                  use_not_found_action_fn)


def _get_volumes_from_config(base_path, config, docker_client):
    aki_volumes: Dict[str, AkiVolume] = {}

    volumes_config: Dict = dict_parse_utils.get_deep_dict(KEY_VOLUMES.path, config)
    for volume_name in volumes_config.keys():
        volume_key_config = ConfigKey(volume_name, KEY_VOLUMES.path)
        volume: Dict = dict_parse_utils.get_dict(volume_key_config, volumes_config)

        volume_type_key_config = ConfigKey(KEY_VOLUME_TYPE.key, volume_key_config.path)
        volume_type = dict_parse_utils.get_str(volume_type_key_config, volume)

        if volume_type == KEY_VOLUME_HOST:
            volume_spec = _create_host_volume_from_config(volume, docker_client, base_path)
        elif volume_type == KEY_VOLUME_DOCKER:
            volume_spec = _create_docker_volume_from_config(volume, docker_client)
        else:
            raise ScriptError(
                f'Key \'{volume_type_key_config.path}\' is \'{volume_type}\' but possible values are \'host\' or '
                f'\'docker\''
            )

        aki_volumes.setdefault(volume_name, volume_spec)

    return aki_volumes


def _get_volume_common_config(volume: Dict):
    env_variable = dict_parse_utils.get_str(KEY_VOLUME_ENV, volume)
    container_name = dict_parse_utils.get_str(KEY_VOLUME_CONTAINER, volume)

    return env_variable, container_name


def _create_host_volume_from_config(volume: Dict, docker_client, base_path: Path):
    env_variable, container_name = _get_volume_common_config(volume)
    folder = dict_parse_utils.get_path(base_path, KEY_VOLUME_FOLDER, volume)
    exclude = dict_parse_utils.get_list(KEY_VOLUME_EXCLUDE, volume, mandatory=False)

    return AkiHostVolume(docker_client, container_name, env_variable, folder, exclude)


def _create_docker_volume_from_config(volume: Dict, docker_client):
    env_variable, container_name = _get_volume_common_config(volume)
    prefix = dict_parse_utils.get_str(KEY_VOLUME_PREFIX, volume)
    exclude = dict_parse_utils.get_list(KEY_VOLUME_EXCLUDE, volume, mandatory=False)

    return AkiDockerVolume(docker_client, container_name, env_variable, prefix, exclude)


def _fetch_default_docker_compose(base_path: Path):
    docker_compose = dict_parse_utils.str_to_path(base_path, 'docker-compose.yaml')
    if docker_compose.exists():
        return docker_compose

    docker_compose = dict_parse_utils.str_to_path(base_path, 'docker-compose.yml')
    if docker_compose.exists():
        return docker_compose

    raise ScriptError(f'Cannot find file docker-compose.yaml or docker-compose.yml in {base_path}')


def _fetch_default_docker_env(base_path: Path):
    docker_compose_env = dict_parse_utils.str_to_path(base_path, '.env')
    if docker_compose_env.exists():
        return docker_compose_env
    raise ScriptError(f'Cannot find file .env in {base_path}')


def _get_docker_compose_from_config(base_path, config):
    compose_config = dict_parse_utils.get_dict(KEY_DOCKER_COMPOSE, config, mandatory=False)
    if not compose_config:
        docker_composes = [_fetch_default_docker_compose(base_path)]
        docker_env_path = _fetch_default_docker_env(base_path)
    else:
        docker_composes = \
            dict_parse_utils.get_path_list(base_path, KEY_DOCKER_COMPOSE_PATH, compose_config, mandatory=False) or \
            [_fetch_default_docker_compose(base_path)]

        docker_env_path = \
            dict_parse_utils.get_path(base_path, KEY_DOCKER_COMPOSE_ENV, compose_config, mandatory=False) or \
            _fetch_default_docker_env(base_path)

    docker_compose_cli_version = dict_parse_utils.get_str(KEY_DOCKER_COMPOSE_VERSION, compose_config, mandatory=False) or '2'
    if docker_compose_cli_version not in ['1', '2']:
        raise ScriptError(
            f'Key \'{KEY_DOCKER_COMPOSE_VERSION.path}\' is \'{docker_compose_cli_version}\' but possible values are '
            f'\'1\' or \'2\''
        )

    return docker_composes, docker_env_path, docker_compose_cli_version


def _fetch_default_aki_path():
    base_path = Path().resolve()
    for aki_file in [base_path / 'aki.yaml', base_path / 'aki.yml']:
        if aki_file.exists():
            return aki_file

    raise ScriptError(f'Cannot find aki.yaml or aki.yml file in folder {base_path}')


def _create_use_not_found_action_fn_from_config(base_path, config):
    actions_configs = dict_parse_utils.get_deep_list(KEY_USE_NOT_FOUND.path, config)

    def fetch_use_not_found_action(volume_name, volumes_by_type, current_volume_by_type):
        for actions_config in actions_configs:
            regex = dict_parse_utils.get_str(KEY_NOT_FOUND_VOLUME_REGEX, actions_config, mandatory=False)
            if regex and not re.search(regex, volume_name):
                continue

            actions = []
            for action_config in dict_parse_utils.get_list(KEY_NOT_FOUND_ACTIONS, actions_config):
                action_type = dict_parse_utils.get_str(KEY_NOT_FOUND_ACTIONS_ACTION, action_config)
                if action_type == ACTION_COPY:
                    action_config[CopyAction.KEY_DESTINATION] = volume_name
                    action_config.setdefault(CopyAction.KEY_SWITCH_TO_COPY, True)
                    action = CopyAction.from_dict(action_config, prefix=KEY_NOT_FOUND_ACTIONS.path)
                elif action_type == ACTION_USE:
                    action = UseAction.from_dict(action_config, prefix=KEY_NOT_FOUND_ACTIONS.path)
                elif action_type == ACTION_RM:
                    action = RemoveAction.from_dict(action_config, prefix=KEY_NOT_FOUND_ACTIONS.path)
                elif action_type == ACTION_ERROR:
                    action = ErrorAction.from_dict(action_config, prefix=KEY_NOT_FOUND_ACTIONS.path)
                elif action_type == ACTION_PY:
                    action_config.setdefault(PyCodeAction.KEY_FUNCTION, 'use_not_found')
                    action = PyCodeAction.from_dict(action_config, volume_name, volumes_by_type,
                                                    current_volume_by_type, prefix=KEY_NOT_FOUND_ACTIONS.path,
                                                    base_path=base_path)
                else:
                    raise ScriptError(f'Action \'{action_type}\' is unknown')
                actions.append(action)

            return actions

    return fetch_use_not_found_action
