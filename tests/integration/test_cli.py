import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from textwrap import dedent
from typing import List, Tuple, Union

import docker
import pytest
from docker import DockerClient
from docker.errors import DockerException

from aki import cli
from aki._colorize import colorize_in_green, colorize_in_red

project_folder = Path(__file__).resolve().parent.parent.parent
cli_file = project_folder / 'aki/cli.py'
docker_compose_folder = Path(__file__).resolve().parent.parent / 'resources/yaml'
aki_file = docker_compose_folder / 'aki.yaml'
env_file = docker_compose_folder / '.env'
mongo_folder = docker_compose_folder / 'mongo'

docker_client: DockerClient = docker.from_env()
postgres_volumes = ['test', 'dev', 'mongo_not_exist', 'share']
mongo_volumes = ['test', 'dev', 'share']
extra_to_remove = ['test_cp']

postgres_container_id = 'aki_test_postgres'
mongo_container_id = 'aki_test_mongo'

postgres_prefix = 'aki_test_postgres_'
mongo_prefix = docker_compose_folder / 'mongo'


@pytest.fixture(autouse=True)
def run_around_tests():
    # prepare a volumes and containers for test
    remove_docker_env()
    create_docker_env()

    yield
    # clean volumes and containers
    remove_docker_env()


def create_docker_env():
    [docker_client.volumes.create(f'aki_test_postgres_{volume}') for volume in postgres_volumes]
    [(mongo_folder / volume).mkdir() for volume in mongo_volumes]

    env_file.unlink(missing_ok=True)
    env_file.touch()
    with open(env_file, 'w') as env_writer:
        env_writer.write('AKI_TEST_MONGO_VOLUME_NAME=dev\n')
        env_writer.write('AKI_TEST_POSTGRES_VOLUME_NAME=dev\n')

    _check_process(_run_cmd('docker', 'compose', 'up', '--detach', cwd=docker_compose_folder))


def remove_docker_env():
    _check_process(_run_cmd('docker', 'compose', 'down', cwd=docker_compose_folder))

    if env_file.exists():
        env_file.unlink()
        env_file.touch()

    # Remove docker volume
    for volume in postgres_volumes + extra_to_remove:
        try:
            docker_client.volumes.get(f'aki_test_postgres_{volume}').remove()
        except DockerException:
            pass

    # Remove folder volume
    docker_client.containers.run(
        image='busybox',
        command=f'rm -rf /volumes/{" ".join(mongo_volumes + extra_to_remove)}',
        working_dir='/volumes',
        volumes=[
            f'{mongo_folder}:/volumes',
        ],
        remove=True
    )


def test_bad_args():
    exit_code, out = _run_cli('foo')
    _assert_process_code(exit_code, 2)

    assert out.startswith('usage: aki [-h]')
    assert "aki: error: argument action: invalid choice: 'foo' (choose from 'ls', 'use', 'cp', 'rm', 'version')" in out


def test_ls():
    exit_code, out = _run_cli('ls')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green('✔'), colorize_in_green('✔')],
        ['mongo_not_exist', 'x', '✔'],
        ['test', '✔', '✔'],
    ]
    assert expected == actual


def test_ls_one():
    exit_code, out = _run_cli('--volume', 'mongo', 'ls')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO'],
        [colorize_in_green('dev'), colorize_in_green('✔')],
        ['test', '✔'],
    ]
    assert expected == actual


def test_ls_long():
    exit_code, out = _run_cli('ls', '--long-name')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green(mongo_folder / 'dev'), colorize_in_green('aki_test_postgres_dev')],
        ['mongo_not_exist', '-', 'aki_test_postgres_mongo_not_exist'],
        ['test', str(mongo_folder / 'test'), 'aki_test_postgres_test'],
    ]
    assert expected == actual


def test_ls_pattern():
    exit_code, out = _run_cli('ls', 'dev')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green('✔'), colorize_in_green('✔')],
    ]
    assert expected == actual


def test_ls_pattern_2():
    exit_code, out = _run_cli('ls', 'e')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green('✔'), colorize_in_green('✔')],
        ['mongo_not_exist', 'x', '✔'],
        ['test', '✔', '✔'],
    ]
    assert expected == actual


def test_ls_pattern_3():
    exit_code, out = _run_cli('ls', '^(de|mongo)')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green('✔'), colorize_in_green('✔')],
        ['mongo_not_exist', 'x', '✔'],
    ]
    assert expected == actual


def test_ls_pattern_reverse():
    exit_code, out = _run_cli('ls', '-r', 'dev')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        ['mongo_not_exist', 'x', '✔'],
        ['test', '✔', '✔'],
    ]
    assert expected == actual


def test_ls_long_pattern():
    exit_code, out = _run_cli('ls', '-l', 'dev')
    _assert_process_code(exit_code)

    actual = _str_out_to_matrix(out)
    expected = [
        ['VOLUME', 'MONGO', 'POSTGRES'],
        [colorize_in_green('dev'), colorize_in_green(mongo_folder / 'dev'), colorize_in_green('aki_test_postgres_dev')],
    ]
    assert expected == actual


def test_use():
    exit_code, out = _run_cli('use', 'test')
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Use volume test
                                 Writing {project_folder}/tests/resources/yaml/.env
                                 Removing container aki_test_mongo
                                 Removing container aki_test_postgres
                                 Restarting containers
                                 {colorize_in_green("Containers started")}''')

    assert mongo_prefix / 'test' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}test' == _get_postgres_current_volume_name()


def test_use_one():
    exit_code, out = _run_cli('--volume', 'mongo', 'use', 'test')
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Use volume test
                                 Writing {project_folder}/tests/resources/yaml/.env
                                 Removing container aki_test_mongo
                                 Restarting containers
                                 \x1b[32mContainers started\x1b[0m''')

    assert mongo_prefix / 'test' == _get_mongo_current_volume_path()


def test_cp():
    exit_code, out = _run_cli('cp', 'test', 'test_cp', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Stopping aki_test_mongo
                                 Copying {mongo_folder}/test to {mongo_folder}/test_cp
                                 \x1b[32mCopy done\x1b[0m
                                    
                                 Stopping aki_test_postgres
                                 Copying volume aki_test_postgres_test to aki_test_postgres_test_cp
                                 \x1b[32mCopy done\x1b[0m
                                    
                                 Switch to volume test_cp ? [Y/n]
                                 Use volume test_cp
                                 Writing {env_file}
                                 Removing container aki_test_mongo
                                 Removing container aki_test_postgres
                                 Restarting containers
                                 \x1b[32mContainers started\x1b[0m''')

    assert mongo_prefix / 'test_cp' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}test_cp' == _get_postgres_current_volume_name()


def test_cp_one():
    exit_code, out = _run_cli('--volume', 'mongo', 'cp', 'test', 'test_cp', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                     Stopping aki_test_mongo
                                     Copying {mongo_folder}/test to {mongo_folder}/test_cp
                                     \x1b[32mCopy done\x1b[0m
                                        
                                     Switch to volume test_cp ? [Y/n]
                                     Use volume test_cp
                                     Writing {env_file}
                                     Removing container aki_test_mongo
                                     Restarting containers
                                     \x1b[32mContainers started\x1b[0m''')

    assert mongo_prefix / 'test_cp' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}dev' == _get_postgres_current_volume_name()


def test_cp_no_switch():
    exit_code, out = _run_cli('cp', 'test', 'test_cp', stdin=StringIO('n'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Stopping aki_test_mongo
                                 Copying {mongo_folder}/test to {mongo_folder}/test_cp
                                 \x1b[32mCopy done\x1b[0m
                                    
                                 Stopping aki_test_postgres
                                 Copying volume aki_test_postgres_test to aki_test_postgres_test_cp
                                 \x1b[32mCopy done\x1b[0m
                                    
                                 Switch to volume test_cp ? [Y/n]
                                 Restarting containers''')

    assert mongo_prefix / 'dev' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}dev' == _get_postgres_current_volume_name()


def test_cp_override():
    stdin = StringIO('y\ny\ny\n')
    exit_code, out = _run_cli('cp', 'test', 'dev', stdin=stdin)
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Stopping aki_test_mongo
                                 Volume dev for mongo already exist, override it ? [Y/n]
                                 Remove volume dev
                                 Removing {mongo_folder}/dev
                                 Copying {mongo_folder}/test to {mongo_folder}/dev
                                 \x1b[32mCopy done\x1b[0m
                                 
                                 Stopping aki_test_postgres
                                 Volume dev for postgres already exist, override it ? [Y/n]
                                 Remove volume dev
                                 Removing aki_test_postgres_dev
                                 Copying volume aki_test_postgres_test to aki_test_postgres_dev
                                 \x1b[32mCopy done\x1b[0m
                                 
                                 Switch to volume dev ? [Y/n]
                                 Use volume dev
                                 Writing {env_file}
                                 Removing container aki_test_mongo
                                 Removing container aki_test_postgres
                                 Restarting containers
                                 \x1b[32mContainers started\x1b[0m''')

    assert mongo_prefix / 'dev' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}dev' == _get_postgres_current_volume_name()


def test_cp_no_override():
    stdin = StringIO('n\nn\ny\n')
    exit_code, out = _run_cli('cp', 'test', 'dev', stdin=stdin)
    _assert_process_code(exit_code)
    _assert_process_out(out, f'''
                                 Stopping aki_test_mongo
                                 Volume dev for mongo already exist, override it ? [Y/n]
                                 Stopping aki_test_postgres
                                 Volume dev for postgres already exist, override it ? [Y/n]
                                 Switch to volume dev ? [Y/n]
                                 Use volume dev
                                 Writing {env_file}
                                 Removing container aki_test_mongo
                                 Removing container aki_test_postgres
                                 Restarting containers
                                 \x1b[32mContainers started\x1b[0m''')

    assert mongo_prefix / 'dev' == _get_mongo_current_volume_path()
    assert f'{postgres_prefix}dev' == _get_postgres_current_volume_name()


def test_rm():
    exit_code, out = _run_cli('rm', 'test')
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Removing {mongo_folder}/test
                                 Removing {postgres_prefix}test''')

    assert not (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}test' != volume.name


def test_rm_used():
    exit_code, out = _run_cli('rm', 'dev')
    _assert_process_code(exit_code, code=1)

    _assert_process_out(out, colorize_in_red(
        'Volume dev is use by container mongo, please switch the volume before trying to remove it'))

    assert (mongo_folder / 'dev').exists()

    volumes_list = docker_client.volumes.list()
    found_volume = False
    for volume in volumes_list:
        if f'{postgres_prefix}test' == volume.name:
            found_volume = True

    assert found_volume


def test_rm_multiple():
    exit_code, out = _run_cli('rm', 'test', 'mongo_not_exist')
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                                 Removing {mongo_folder}/test
                                 Removing {postgres_prefix}mongo_not_exist
                                 Removing {postgres_prefix}test''')

    assert not (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}test' != volume.name
        assert f'{postgres_prefix}mongo_not_exist' != volume.name


def test_rm_one():
    exit_code, out = _run_cli('--volume', 'mongo', 'rm', 'test')
    _assert_process_code(exit_code)

    _assert_process_out(out, f'Removing {mongo_folder}/test')

    assert not (mongo_folder / 'test').exists()


def test_rm_pattern():
    exit_code, out = _run_cli('rm', '-e', '^(te|mongo)', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                             VOLUME           MONGO  POSTGRES  
                             mongo_not_exist  x      ✔         
                             test             ✔      ✔         
                            
                             Remove those volumes ? [y/N]
                             Removing {mongo_folder}/test
                             Removing aki_test_postgres_mongo_not_exist
                             Removing aki_test_postgres_test''')

    assert not (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}test' != volume.name
        assert f'{postgres_prefix}mongo_not_exist' != volume.name


def test_rm_pattern_multiple():
    exit_code, out = _run_cli('rm', '-e', '^te', '^mongo', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                             VOLUME           MONGO  POSTGRES  
                             mongo_not_exist  x      ✔         
                             test             ✔      ✔         
                            
                             Remove those volumes ? [y/N]
                             Removing {mongo_folder}/test
                             Removing aki_test_postgres_mongo_not_exist
                             Removing aki_test_postgres_test''')

    assert not (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}test' != volume.name
        assert f'{postgres_prefix}mongo_not_exist' != volume.name


def test_rm_pattern_reverse():
    exit_code, out = _run_cli('rm', '-er', '^dev$', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                             VOLUME           MONGO  POSTGRES  
                             mongo_not_exist  x      ✔         
                             test             ✔      ✔         
                            
                             Remove those volumes ? [y/N]
                             Removing {mongo_folder}/test
                             Removing aki_test_postgres_mongo_not_exist
                             Removing aki_test_postgres_test''')

    assert not (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}test' != volume.name
        assert f'{postgres_prefix}mongo_not_exist' != volume.name


def test_rm_pattern_reverse_multiple():
    exit_code, out = _run_cli('rm', '-er', '^dev$', '^test$', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                             VOLUME           MONGO  POSTGRES  
                             mongo_not_exist  x      ✔         
                            
                             Remove those volumes ? [y/N]
                             Removing aki_test_postgres_mongo_not_exist''')

    volumes_list = docker_client.volumes.list()
    for volume in volumes_list:
        assert f'{postgres_prefix}mongo_not_exist' != volume.name


def test_rm_pattern_no_match():
    exit_code, out = _run_cli('rm', '-e', '^no_match', stdin=StringIO('y'))
    _assert_process_code(exit_code)

    _assert_process_out(out, f'''
                             No volume found''')

    assert (mongo_folder / 'dev').exists()
    assert (mongo_folder / 'test').exists()

    volumes_list = docker_client.volumes.list()
    found_dev = False
    found_test = False
    found_mongo_not_exist = False
    for volume in volumes_list:
        found_dev = found_dev or f'{postgres_prefix}dev' != volume.name
        found_test = found_test or f'{postgres_prefix}test' != volume.name
        found_mongo_not_exist = found_mongo_not_exist or f'{postgres_prefix}mongo_not_exist' != volume.name

    assert found_dev
    assert found_test
    assert found_mongo_not_exist


def _run_cli(*args, stdin: StringIO = StringIO()) -> Tuple[Union[int, None], str]:
    """
    Execute cli main and return printed lines as str
    :param args: cli main args
    :return: str
    """
    # Copy argv and stdout
    argv = sys.argv
    sin = sys.stdin
    out = sys.stdout
    err = sys.stderr
    try:
        # Override argv and stdout
        sys.argv = ['aki', '--file', str(aki_file), *args]
        sys.stdout = StringIO()
        sys.stderr = sys.stdout
        sys.stdin = stdin

        # Execute
        out.write(' '.join(sys.argv) + '\n')
        exit_code = None
        try:
            exit_code = cli.main()
        except SystemExit as e:
            exit_code = e.code
        except Exception as e:
            out.write(f'test error: {e}')

        # Return printed lines
        printed = sys.stdout.getvalue()
        out.write(printed + '\n')
        return exit_code, printed
    finally:
        sys.stdout.close()
        sys.stderr.close()
        sys.stdin.close()

        # Restore argv and stdout
        sys.argv = argv
        sys.stdin = sin
        sys.stdout = out
        sys.stderr = err


def _run_cmd(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)


def _check_process(process: subprocess.CompletedProcess):
    if process.returncode != 0:
        raise ValueError(f'{process.args=} {process.returncode=} out={process.stdout.decode()}')


def _assert_process_code(exit_code: int or None, code: int = 0):
    assert exit_code == code


def _assert_process_out(out: str or None, expected: str):
    assert out.strip().replace('[Y/n] ', '[Y/n]\n').replace('[y/N] ', '[y/N]\n') == dedent(expected).strip()


def _str_out_to_matrix(out) -> List[List[str]]:
    matrix: List[List[str]] = []
    for line in out.split('\n'):
        line_split = list(filter(lambda s: s, line.split(' ')))
        if line_split:
            matrix.append(line_split)

    return matrix


def _get_postgres_current_volume_name():
    container = docker_client.containers.get(postgres_container_id)
    container_volumes = container.attrs.get('Mounts')

    for docker_volumes in container_volumes:
        volume_name = docker_volumes.get('Name')
        if postgres_prefix in volume_name:
            return volume_name


def _get_mongo_current_volume_path():
    container = docker_client.containers.get(mongo_container_id)
    volumes = container.attrs.get('Mounts')

    for volume in volumes:
        source = volume.get('Source')
        if str(mongo_prefix) in source:
            return Path(source)
