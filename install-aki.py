"""
This script will install aki.

It will perform the following steps:
    * Create a new virtual environment using the built-in venv module in home args or $HOME/.aki
    * Install aki inside this virtual environment using pip.
    * Install a `aki` script into `~/.local/bin`
    * Attempt to inform the user if they need to add this bin directory to their `$PATH`, as well as how to do so.
"""

import argparse
import subprocess
import sys
import os
import venv
from pathlib import Path

AKI_HOME = Path(os.environ.get('HOME')) / '.aki'
AKI_VERSION = '0.10.1'
GITHUB_URL = f'https://github.com/4sh/aki/releases/download/{AKI_VERSION}/aki-{AKI_VERSION}.tar.gz'
AKI_PYTHON_MIN_REQUIREMENT = (3, 8, 0)
POST_INSTALL_MESSAGE = """You can test that everything is set up by executing:
`aki --help`

You may need to add the bin directory `{symlink_bin}` in your shell configuration file:
`export PATH="{symlink_bin}:$PATH"`
    
Or you can call aki with `{script}` 
"""


def colorize(color, message):
    return f'\033[{color}m{message}\033[0m'


def print_success(text, **kwargs):
    print(colorize(32, text), **kwargs)


def check_python_version():
    if sys.version_info < AKI_PYTHON_MIN_REQUIREMENT:
        raise ValueError(f'aki required at least python {".".join([str(v) for v in AKI_PYTHON_MIN_REQUIREMENT])}')


class AkiEnvBuilder(venv.EnvBuilder):
    """
    Class for create a venv and install aki
    """

    def __init__(self):
        super().__init__(clear=True, symlinks=False, with_pip=True, upgrade=True)


class AkiInstaller:
    AKI_VENV_SCRIPT_PATH = Path('/usr/local/bin/aki')
    AKI_DEFAULT_SYMLINK_BIN_PATH = Path(os.environ.get('HOME')) / '.local/bin'

    def __init__(self, home: Path):
        self.home = home
        self.venv = self.home / 'venv'
        self.venv_python = self.venv / 'bin/python'
        self.script = self.venv / 'bin/aki'
        self.symlink_bin = self.home / 'bin' if self.home != AKI_HOME else AkiInstaller.AKI_DEFAULT_SYMLINK_BIN_PATH
        self.symlink = self.symlink_bin / 'aki'

    def install(self):
        """
        Create venv
        Install aki
        Create a symlink
        """
        print(f'Creating aki virtual env at {self.home}')
        self._build_env()

        print('Installing aki package')
        self._install_aki()

        print(f'Creating aki symlink to {self.symlink}')
        self._create_symlink()

        print_success(f'aki is installed')
        print()
        print(POST_INSTALL_MESSAGE.format(symlink_bin=self.symlink_bin, script=self.script))

    @staticmethod
    def _run(*args, **kwargs):
        process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)

        if process.returncode != 0:
            raise ValueError(f'command: `{" ".join(args)}` - code: {process.returncode}\n{process.stdout.decode()}')

    def _run_pip(self, *args, **kwargs):
        self._run(str(self.venv_python), '-m', 'pip', *args, **kwargs)

    def _build_env(self):
        AkiEnvBuilder().create(self.venv)
        self._run_pip('install', '--disable-pip-version-check', '--upgrade', 'pip')

    def _install_aki(self):
        self._run_pip('install', GITHUB_URL)

    def _create_symlink(self):
        if not self.symlink_bin.exists():
            self.symlink_bin.mkdir(parents=True, exist_ok=True)

        self.symlink.unlink(missing_ok=True)
        self.symlink.symlink_to(self.script)


def main():
    try:
        check_python_version()

        parser = argparse.ArgumentParser()
        parser.add_argument('--home', type=Path, default=AKI_HOME, help='aki installation folder')
        args = parser.parse_args()

        AkiInstaller(args.home.resolve()).install()
    except ValueError as e:
        print(colorize(31, 'aki installation fail'), file=sys.stderr)
        print(colorize(31, e), file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    sys.exit(main())
