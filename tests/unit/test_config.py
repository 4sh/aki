from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aki import _config as config_loader
from aki.error import ScriptError
from aki.volume import AkiHostVolume, AkiDockerVolume

TEST_FOLDER = Path(__file__).resolve().parent.parent
DOCKER_CLIENT = MagicMock()


def test_get_volumes_specs_from_config():
    config = {
        'aki':
            {
                'volumes': {
                    'volume_spec_host': {
                        'type': 'host',
                        'env': 'ENV',
                        'container_name': 'name',
                        'folder': str(TEST_FOLDER / 'volume_spec_host'),
                        'exclude': ['exclude_name']
                    },
                    'volume_spec_docker': {
                        'type': 'docker',
                        'env': 'ENV2',
                        'container_name': 'name2',
                        'prefix': 'docker_',
                    }
                }
            }
    }
    volume_specs = config_loader._get_volumes_from_config(TEST_FOLDER, config, DOCKER_CLIENT)

    assert len(volume_specs) == 2

    volume_spec_host: AkiHostVolume = volume_specs['volume_spec_host']
    assert volume_spec_host is not None
    assert volume_spec_host.docker_client == DOCKER_CLIENT
    assert volume_spec_host.env_variable == 'ENV'
    assert volume_spec_host.container_name == 'name'
    assert volume_spec_host.parent_folder == TEST_FOLDER / 'volume_spec_host'
    assert volume_spec_host.exclude_names == ['exclude_name']

    volume_spec_docker: AkiDockerVolume = volume_specs['volume_spec_docker']
    assert volume_spec_docker is not None
    assert volume_spec_docker.docker_client == DOCKER_CLIENT
    assert volume_spec_docker.env_variable == 'ENV2'
    assert volume_spec_docker.container_name == 'name2'
    assert volume_spec_docker.prefix_name == 'docker_'


def test_get_volumes_specs_from_config_error_type():
    config = {
        'aki':
            {
                'volumes': {
                    'volume_spec_host': {
                        'type': 'error',
                        'env': 'ENV',
                        'container_name': 'name',
                        'folder': str(TEST_FOLDER / 'volume_spec_host'),
                        'exclude': ['exclude_name']
                    }
                }
            }
    }

    with pytest.raises(ScriptError) as e:
        config_loader._get_volumes_from_config(TEST_FOLDER, config, DOCKER_CLIENT)

    assert str(e.value) == 'Key \'aki.volumes.volume_spec_host.type\' is \'error\' but possible ' \
                           'values are \'host\' or \'docker\''


@patch('pathlib.Path.exists', MagicMock(return_value=False))
def test_fetch_default_docker_compose_not_exist():
    with pytest.raises(ScriptError) as e:
        config_loader._fetch_default_docker_compose(TEST_FOLDER)

    assert str(e.value) == f'Cannot find file docker-compose.yaml or docker-compose.yml in {TEST_FOLDER}'


def test_fetch_default_docker_compose_yaml():
    expected_path = TEST_FOLDER / 'docker-compose.yaml'

    def docker_compose_exist(self):
        return self.name == 'docker-compose.yaml'

    with patch.object(Path, 'exists', autospec=True, side_effect=docker_compose_exist) as exist_patch:
        docker_compose = config_loader._fetch_default_docker_compose(TEST_FOLDER)

    assert docker_compose == expected_path
    exist_patch.assert_called_once_with(expected_path)


def test_fetch_default_docker_compose_yml():
    expected_path = TEST_FOLDER / 'docker-compose.yml'

    def docker_compose_exist(self):
        return self.name == 'docker-compose.yml'

    with patch.object(Path, 'exists', autospec=True, side_effect=docker_compose_exist) as exist_patch:
        docker_compose = config_loader._fetch_default_docker_compose(TEST_FOLDER)

    assert docker_compose == expected_path
    assert exist_patch.call_count == 2
    exist_patch.assert_called_with(expected_path)
    exist_patch.assert_any_call(TEST_FOLDER / 'docker-compose.yaml')


@patch('pathlib.Path.exists', MagicMock(return_value=False))
def test_fetch_default_docker_env_not_exist():
    with pytest.raises(ScriptError) as e:
        config_loader._fetch_default_docker_env(TEST_FOLDER)

    assert str(e.value) == f'Cannot find file .env in {TEST_FOLDER}'


def test_fetch_default_docker_env():
    with patch.object(Path, 'exists', return_value=True) as exist_patch:
        docker_env = config_loader._fetch_default_docker_env(TEST_FOLDER)
    assert docker_env == TEST_FOLDER / '.env'
    assert exist_patch.call_count == 1


def test_get_docker_compose_from_config_key_docker_compose_not_exists():
    with patch.object(Path, 'exists', return_value=True):
        docker_compose, docker_env_path, docker_cli_version = config_loader._get_docker_compose_from_config(TEST_FOLDER,
                                                                                                            {})
    assert docker_compose == [TEST_FOLDER / 'docker-compose.yaml']
    assert docker_env_path == TEST_FOLDER / '.env'
    assert docker_cli_version == '2'


def test_get_docker_compose_from_config_key_docker_compose_empty():
    with patch.object(Path, 'exists', return_value=True):
        config = {'docker_compose': {}}
        docker_compose, docker_env_path, docker_cli_version = config_loader._get_docker_compose_from_config(TEST_FOLDER,
                                                                                                            config)
    assert docker_compose == [TEST_FOLDER / 'docker-compose.yaml']
    assert docker_env_path == TEST_FOLDER / '.env'
    assert docker_cli_version == '2'


def test_get_docker_compose_from_config_key_docker_compose():
    with patch.object(Path, 'exists', return_value=True):
        config = {'docker_compose': {'path': ['./docker_compose/dc.yaml'], 'env': './docker_compose/dev.env'}}
        docker_compose, docker_env_path, docker_cli_version = config_loader._get_docker_compose_from_config(TEST_FOLDER,
                                                                                                            config)
    assert docker_compose == [TEST_FOLDER / 'docker_compose/dc.yaml']
    assert docker_env_path == TEST_FOLDER / 'docker_compose/dev.env'
    assert docker_cli_version == '2'


def test_get_docker_compose_from_config_key_docker_compose_absolute_path():
    with patch.object(Path, 'exists', return_value=True):
        config = {'docker_compose': {'path': ['/docker_compose/dc.yaml'], 'env': '/docker_compose/dev.env'}}
        docker_compose, docker_env_path, docker_cli_version = config_loader._get_docker_compose_from_config(TEST_FOLDER,
                                                                                                            config)
    assert docker_compose == [Path('/docker_compose/dc.yaml')]
    assert docker_env_path == Path('/docker_compose/dev.env')
    assert docker_cli_version == '2'


def test_get_cli_version_from_config_key_docker_compose():
    with patch.object(Path, 'exists', return_value=True):
        config = {'docker_compose': {'path': ['./docker_compose/dc.yaml'], 'env': './docker_compose/dev.env',
                                     'cli_version': '1'}}
        docker_compose, docker_env_path, docker_cli_version = config_loader._get_docker_compose_from_config(TEST_FOLDER,
                                                                                                            config)
    assert docker_compose == [TEST_FOLDER / 'docker_compose/dc.yaml']
    assert docker_env_path == TEST_FOLDER / 'docker_compose/dev.env'
    assert docker_cli_version == '1'


def test_get_incorrect_cli_version_from_config_key_docker_compose():
    with pytest.raises(ScriptError) as e:
        config = {'docker_compose': {'path': ['./docker_compose/dc.yaml'], 'env': './docker_compose/dev.env',
                                     'cli_version': 'foo'}}
        config_loader._get_docker_compose_from_config(TEST_FOLDER, config)

    assert str(e.value) == f"Key 'docker_compose.cli_version' is 'foo' but possible values are '1' or '2'"


def test_create_use_not_found_action_fn_from_config_copy():
    actions = {'aki': {'use': {'not_found': [{'volume': '.*', 'actions': [{'action': 'copy', 'source': 'dev'}]}]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('volume', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    copy = actions[0]

    assert copy.source == 'dev'
    assert copy.destination == 'volume'
    assert copy.override is False
    assert copy.switch_to_copy is True


def test_create_use_not_found_action_fn_from_config_use():
    actions = {'aki': {'use': {'not_found': [{'volume': '.*', 'actions': [{'action': 'use', 'volume_name': 'dev'}]}]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('volume', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    use = actions[0]

    assert use.volume == 'dev'


def test_create_use_not_found_action_fn_from_config_rm():
    actions = {'aki': {'use': {'not_found': [{'actions': [{'action': 'remove', 'volume_names': ['dev', 'dev-x']}]}]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('volume', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    remove = actions[0]

    assert remove.volumes == ['dev', 'dev-x']


def test_create_use_not_found_action_fn_from_config_error():
    actions = {
        'aki': {'use': {'not_found': [{'volume_name': '.*', 'actions': [{'action': 'error', 'message': 'why ?'}]}]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('volume', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    error = actions[0]

    assert error.message == 'why ?'


def test_create_use_not_found_action_fn_from_config_py():
    actions = {'aki': {'use': {'not_found': [{'volume_name': '.*', 'actions': [
        {'action': 'py', 'file': str(TEST_FOLDER / 'resources/py/test_py_code.py')}
    ]}]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('volume', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    py_code = actions[0]

    assert py_code.file == TEST_FOLDER / 'resources/py/test_py_code.py'
    assert py_code.function == 'use_not_found'
    assert py_code._function_args == ('volume', {}, {})


def test_create_use_not_found_action_fn_from_config_multi():
    actions = {'aki': {'use': {'not_found': [
        {'volume_name': 'dev-.*',
         'actions': [{'action': 'py', 'file': str(TEST_FOLDER / 'resources/py/test_py_code.py')}]},
        {'volume_name': 'test+', 'actions': [{'action': 'error', 'message': 'why ?'}]},
        {'volume_name': '.*', 'actions': [{'action': 'error', 'message': 'no'}]}
    ]}}}
    actions = config_loader._create_use_not_found_action_fn_from_config(TEST_FOLDER, actions)('testtest', {}, {})

    assert type(actions) == list
    assert len(actions) == 1
    error = actions[0]

    assert error.message == 'why ?'


def test_import_config():
    base_path = TEST_FOLDER / 'resources/yaml'
    config = config_loader.import_config(base_path / 'aki.yaml')

    assert config.docker_compose == [base_path / 'docker-compose.yaml']

    volume_specs = config.aki_volumes
    assert len(volume_specs) == 2

    volume_spec_host: AkiHostVolume = volume_specs['mongo']
    assert volume_spec_host is not None
    assert volume_spec_host.docker_client == config.docker_client
    assert volume_spec_host.env_variable == 'AKI_TEST_MONGO_VOLUME_NAME'
    assert volume_spec_host.container_name == 'aki_test_mongo'
    assert volume_spec_host.parent_folder == base_path / 'mongo'
    assert volume_spec_host.exclude_names == ['share']

    volume_spec_docker: AkiDockerVolume = volume_specs['postgres']
    assert volume_spec_docker is not None
    assert volume_spec_host.docker_client == config.docker_client
    assert volume_spec_docker.env_variable == 'AKI_TEST_POSTGRES_VOLUME_NAME'
    assert volume_spec_docker.container_name == 'aki_test_postgres'
    assert volume_spec_docker.prefix_name == 'aki_test_postgres_'
