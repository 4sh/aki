from pathlib import Path
from typing import Dict, List

from aki.config_key import ConfigKey
from aki.error import DictParseMandatoryScriptError, DictParseScriptError


def get_value(config_key: ConfigKey, dictionary: Dict, mandatory=True):
    value = dictionary.get(config_key.key)
    if mandatory and not value:
        raise DictParseMandatoryScriptError(config_key)

    return value


def get_str(key: ConfigKey, dictionary: Dict, mandatory=True):
    value_str = get_value(key, dictionary, mandatory)

    if not mandatory and value_str is None:
        return None

    if not isinstance(value_str, str):
        raise DictParseScriptError(f'key \'{key.path}\' is not a str')

    return value_str


def get_dict(key: ConfigKey, dictionary: Dict, mandatory=True) -> Dict:
    value_dict = get_value(key, dictionary, mandatory)

    if not mandatory and value_dict is None:
        return {}

    if not isinstance(value_dict, dict):
        raise DictParseScriptError(f'key \'{key.path}\' is not a dictionary')

    return value_dict


def get_list(key: ConfigKey, dictionary: Dict, mandatory=True) -> List:
    value_list = get_value(key, dictionary, mandatory)

    if not mandatory and value_list is None:
        return []

    if not isinstance(value_list, list):
        raise DictParseScriptError(f'key \'{key.path}\' is not an array')

    return value_list


def get_bool(key: ConfigKey, dictionary: Dict, mandatory: bool) -> bool:
    value = get_value(key, dictionary, mandatory=mandatory)

    if value and not isinstance(value, bool):
        raise DictParseScriptError(f'key \'{key.path}\' is not a boolean')

    return value


def get_bool_default(key: ConfigKey, dictionary: Dict, default_value: bool) -> bool:
    return get_bool(key, dictionary, mandatory=False) or default_value


def get_path(base_path: [Path], key: ConfigKey, config: Dict, mandatory=True):
    path_str = get_value(key, config, mandatory)
    return str_to_path(base_path, path_str) if path_str else None


def get_deep_value(compose_key: str, dictionary: Dict, prefix: str = '', mandatory=True):
    current_dictionary = dictionary
    current_key = ConfigKey('', prefix)
    keys = compose_key.split('.')

    for index, key_str in enumerate(keys):
        current_key = ConfigKey(key_str, current_key.path)
        if index + 1 != len(keys):
            value = get_dict(current_key, current_dictionary, mandatory)
            if mandatory and not value:
                raise DictParseMandatoryScriptError(current_key)

            current_dictionary = value
        else:
            return get_value(current_key, current_dictionary, mandatory)


def get_deep_list(compose_key: str, dictionary: Dict, prefix: str = '', mandatory=True):
    value_list = get_deep_value(compose_key, dictionary, prefix, mandatory)
    if not isinstance(value_list, list):
        key_path = f'{prefix}.{compose_key}' if prefix else compose_key
        raise DictParseScriptError(f'key \'{key_path}\' is not an array')
    return value_list


def get_deep_dict(compose_key: str, dictionary: Dict, prefix: str = '', mandatory=True) -> Dict:
    value_dict = get_deep_value(compose_key, dictionary, prefix, mandatory)

    if not mandatory and value_dict is None:
        return {}

    if not isinstance(value_dict, dict):
        key_path = f'{prefix}.{compose_key}' if prefix else compose_key
        raise DictParseScriptError(f'key \'{key_path}\' is not a dictionary')

    return value_dict


def get_path_list(base_path: [Path], key: ConfigKey, config: Dict, mandatory=True) -> List[Path]:
    paths = get_list(key, config, mandatory)
    return [str_to_path(base_path, path_str) for path_str in paths if path_str]


def str_to_path(base_path: [Path], path_str: str) -> Path:
    path = Path(path_str)
    if base_path and not path.is_absolute():
        path = (base_path / path).resolve()

    return path
