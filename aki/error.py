# Basic error for print message before exist the script
from aki.config_key import ConfigKey


class ScriptError(Exception):
    pass


class DictParseScriptError(ScriptError):
    pass


class DictParseMandatoryScriptError(ScriptError):
    def __init__(self, key: ConfigKey):
        super(DictParseMandatoryScriptError, self).__init__(f'Key \'{key.path}\' is mandatory')
