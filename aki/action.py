import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from aki.config_key import ConfigKey
from aki.error import ScriptError
import aki._dict_parse_utils as dict_parse_utils

ACTION_COPY = 'copy'
ACTION_USE = 'use'
ACTION_RM = 'remove'
ACTION_ERROR = 'error'
ACTION_PY = 'py'


class Action(metaclass=abc.ABCMeta):
    KEY_ACTION = 'action'


@dataclass(frozen=True)
class CopyAction(Action):
    """
    Perform a script copy
    """
    KEY_SOURCE = 'source'
    KEY_DESTINATION = 'destination'
    KEY_OVERRIDE = 'override'
    KEY_SWITCH_TO_COPY = 'switch_to_copy'

    source: str
    destination: str
    override: bool = False
    switch_to_copy: bool = None

    @staticmethod
    def from_dict(dictionary: Dict, prefix: str = ''):
        source = dict_parse_utils.get_str(ConfigKey(CopyAction.KEY_SOURCE, prefix), dictionary)
        destination = dict_parse_utils.get_str(ConfigKey(CopyAction.KEY_DESTINATION, prefix), dictionary)
        override = dict_parse_utils.get_bool_default(ConfigKey(CopyAction.KEY_OVERRIDE, prefix), dictionary, False)
        switch_to_copy = dict_parse_utils.get_bool(ConfigKey(CopyAction.KEY_SWITCH_TO_COPY, prefix), dictionary, False)

        return CopyAction(source, destination, override, switch_to_copy)


@dataclass(frozen=True)
class UseAction(Action):
    """
    Perform a script use
    """
    KEY_VOLUME = 'volume_name'

    volume: str

    @staticmethod
    def from_dict(dictionary: Dict, prefix: str = ''):
        volume = dict_parse_utils.get_str(ConfigKey(UseAction.KEY_VOLUME, prefix), dictionary)
        return UseAction(volume)


@dataclass(frozen=True)
class RemoveAction(Action):
    """
    Remove one or a list of volumes
    """
    KEY_VOLUMES = 'volume_names'

    volumes: List[str]

    @staticmethod
    def from_dict(dictionary: Dict, prefix: str = ''):
        volume_names = dict_parse_utils.get_list(ConfigKey(RemoveAction.KEY_VOLUMES, prefix), dictionary)
        return RemoveAction(volume_names)


@dataclass(frozen=True)
class ErrorAction(Action):
    """
    Raise an error
    """
    KEY_MESSAGE = 'message'

    message: str = None

    @staticmethod
    def from_dict(dictionary: Dict, prefix: str = ''):
        message = dict_parse_utils.get_str(ConfigKey(ErrorAction.KEY_MESSAGE, prefix), dictionary, mandatory=False)
        return ErrorAction(message=message)


@dataclass(frozen=True)
class PyCodeAction(Action):
    """
    Call a function that return an action or a list of actions
    """
    KEY_FILE = 'file'
    KEY_FUNCTION = 'function'

    file: Path
    function: str
    _function_args: Tuple

    def execute(self) -> [List[Action], None]:
        # Import the file as a module
        import importlib.util
        import sys
        action_py_spec = importlib.util.spec_from_file_location("docker_volume_py_code_action", self.file)
        action_py_module = importlib.util.module_from_spec(action_py_spec)
        sys.modules["module.name"] = action_py_module
        action_py_spec.loader.exec_module(action_py_module)

        # Get function
        try:
            fn = getattr(action_py_module, self.function)
        except AttributeError:
            raise ScriptError(f'function \'{self.function}\' does not exist in \'{self.file}\'')

        # Execute the function
        try:
            actions_dict = fn(*self._function_args)
        except Exception as e:
            raise ScriptError(f'function {self.function} raise an error : {e.__repr__()}')

        actions = []
        if isinstance(actions_dict, dict):
            actions_dict = [actions_dict]
        elif isinstance(actions_dict, list):
            pass
        elif actions_dict is None:
            return None
        else:
            raise ScriptError(f'function {self.function} return \'{actions_dict}\' but this is not an action or a '
                              f'list of action')

        for action_dict in actions_dict:
            action_type = dict_parse_utils.get_str(ConfigKey(Action.KEY_ACTION), action_dict)
            if action_type == ACTION_COPY:
                actions.append(CopyAction.from_dict(action_dict))
            elif action_type == ACTION_USE:
                actions.append(UseAction.from_dict(action_dict))
            elif action_type == ACTION_RM:
                actions.append(RemoveAction.from_dict(action_dict))
            elif action_type == ACTION_ERROR:
                actions.append(ErrorAction.from_dict(action_dict))
            elif action_type == ACTION_PY:
                raise ScriptError(f'Action \'py\' is not authorize from a py action')
            else:
                raise ScriptError(f'Action \'{action_type}\' is unknown')

        return actions

    @staticmethod
    def from_dict(dictionary: Dict, *args, prefix: str = ''):
        file = dict_parse_utils.get_path(None, ConfigKey(PyCodeAction.KEY_FILE, prefix), dictionary)
        if not file.exists():
            raise ScriptError(f'Action py : Path {file} does not exist')

        function = dict_parse_utils.get_str(ConfigKey(PyCodeAction.KEY_FUNCTION, prefix), dictionary)
        return PyCodeAction(file, function, args)
