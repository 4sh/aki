import abc
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from sys import platform
from typing import List, Iterator

import docker.errors
from docker import DockerClient
from docker.errors import DockerException

from aki._print import print_info, print_verbose, print_debug_def

KEY_VOLUME_DOCKER = 'docker'
KEY_VOLUME_HOST = 'host'


@dataclass(frozen=True)
class Volume:
    """
    Rep of an existing volume
    """
    external_name: str  # name in docker or path in file system
    aki_name: str  # short name in aki


@dataclass(frozen=True)
class AkiVolume(metaclass=abc.ABCMeta):
    docker_client: DockerClient = field(repr=False)
    container_name: str
    env_variable: str

    @abc.abstractmethod
    def volume_name_to_volume(self, volume_name: str, is_aki_name: bool = False) -> Volume:
        """
        Create a aki volume instance from the name
        it can be the aki short name or the long name (in docker or path in the file system)
        """
        pass

    @abc.abstractmethod
    def fetch_volumes(self) -> Iterator[Volume]:
        """
        Return existing volumes
        """
        pass

    @abc.abstractmethod
    def fetch_current_volume(self) -> Volume or None:
        """
        Fetch volume name use by container name
        """
        pass

    @abc.abstractmethod
    def copy(self, source: Volume, destination: Volume):
        pass

    @abc.abstractmethod
    def remove(self, volume: Volume):
        pass

    def is_container_up(self) -> bool:
        """
        True if the container link to AkiVolume is running
        """
        try:
            return self.docker_client.containers.get(self.container_name).status == 'running'
        except docker.errors.NotFound:
            return False


@dataclass(frozen=True)
class AkiDockerVolume(AkiVolume):
    prefix_name: str
    exclude_names: List[str] = field(default_factory=list)

    def volume_name_to_volume(self, volume_name: str, is_aki_name: bool = False) -> Volume:
        if is_aki_name:
            aki_name = volume_name
            name = f'{self.prefix_name}{volume_name}'
        else:
            name = volume_name
            aki_name = volume_name[len(self.prefix_name):]

        return Volume(name, aki_name)

    def fetch_volumes(self) -> Iterator[Volume]:
        docker_filter = f'^{self.prefix_name}'
        print_verbose(f'{self.container_name} - fetch volume on docker with filter {docker_filter}')
        docker_volumes = self.docker_client.volumes.list(filters={'name': docker_filter})
        print_debug_def(lambda: f'{self.container_name} - receive {[v.name for v in docker_volumes]}')

        for docker_volume in docker_volumes:
            volume = self.volume_name_to_volume(docker_volume.name)
            if volume.aki_name not in self.exclude_names:
                yield volume

    def fetch_current_volume(self) -> Volume or None:
        try:
            print_verbose(f'{self.container_name} - fetch container')
            container = self.docker_client.containers.get(self.container_name)
            print_verbose(f'{self.container_name} - fetch container ok')

            container_volumes = container.attrs.get('Mounts')

            for docker_volumes in container_volumes:
                volume_name = docker_volumes.get('Name')
                if self.prefix_name in volume_name:
                    current_volume = self.volume_name_to_volume(volume_name)
                    print_verbose(f'{self.container_name} - {current_volume=}')
                    return current_volume

            return None
        except DockerException as e:
            print_verbose(f'{self.container_name} - fetch container error {e}')
            return None

    def copy(self, source: Volume, destination: Volume):
        print_verbose(f'{self.container_name} - docker copy {self.container_name}, {source=}, {destination=}')
        print_info(f'Copying volume {source.external_name} to {destination.external_name}')

        self.docker_client.containers.run('busybox',
                                          command='cp -R /source/ /destination',
                                          volumes=[
                                              f'{source.external_name}:/source',
                                              f'{destination.external_name}:/destination'
                                          ],
                                          remove=True)

    def remove(self, volume: Volume):
        try:
            print_info(f'Removing {volume.external_name}')
            self.docker_client.volumes.get(volume.external_name).remove()
        except DockerException:
            pass


@dataclass(frozen=True)
class AkiHostVolume(AkiVolume):
    parent_folder: Path
    exclude_names: List[str] = field(default_factory=list)

    def volume_name_to_volume(self, volume_name: str, is_aki_name: bool = False) -> Volume:
        if is_aki_name:
            aki_name = volume_name
            name = str(self.parent_folder / volume_name)
        else:
            name = volume_name
            aki_name = Path(volume_name).name

        return Volume(name, aki_name)

    def fetch_volumes(self) -> Iterator[Volume]:
        print_verbose(f'{self.container_name} - fetch volume on host - folder {self.parent_folder} - '
                      f'excludes {self.exclude_names}')

        for volume in self.parent_folder.iterdir():
            if volume.is_dir() and volume.name not in self.exclude_names:
                yield self.volume_name_to_volume(str(volume))

    def fetch_current_volume(self) -> Volume or None:
        parent_folder = str(self.parent_folder)
        exclude_str_path = [str(self.parent_folder / exclude_name) for exclude_name in self.exclude_names]

        try:
            print_verbose(f'{self.container_name} - fetch container')
            container = self.docker_client.containers.get(self.container_name)
            print_verbose(f'{self.container_name} - fetch container ok')
            volumes = container.attrs.get('Mounts')

            for volume in volumes:
                volume_path = volume.get('Source')

                if parent_folder in volume_path and volume_path not in exclude_str_path:
                    print_verbose(f'{self.container_name} - current_volume={volume_path}')
                    return self.volume_name_to_volume(volume_path)
        except DockerException as e:
            print_verbose(f'{self.container_name} - fetch container error {e}')
            return None

        return None

    def copy(self, source: Volume, destination: Volume):
        print_verbose(f'{self.container_name} - host copy {source=}, {destination=}')

        destination_path = Path(destination.external_name)
        if destination_path.exists():
            destination_path.rmdir()

        if platform == "linux" or platform == "linux2":
            print_verbose('copy on linux - start a container')
            self.docker_client.containers.run('busybox',
                                              command='cp -R /source/. /destination',
                                              volumes=[
                                                  f'{source.external_name}:/source',
                                                  f'{destination.external_name}:/destination'
                                              ],
                                              remove=True)
        else:
            print_verbose('copy with sh')
            shutil.copytree(source.external_name, destination.external_name)


    def remove(self, volume: Volume):
        try:
            print_info(f'Removing {volume.external_name}')
            shutil.rmtree(volume.external_name)
        except FileNotFoundError:
            pass
