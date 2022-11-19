from pathlib import Path

import pytest

from aki.action import CopyAction, UseAction, RemoveAction, ErrorAction, PyCodeAction
from aki.error import ScriptError

TEST_FOLDER = Path(__file__).resolve().parent.parent


def test_copy_default():
    copy = CopyAction.from_dict({
        'source': 'aSource',
        'destination': 'aDestination',
    })

    assert copy.source == 'aSource'
    assert copy.destination == 'aDestination'
    assert copy.override is False
    assert copy.switch_to_copy is None


def test_copy_all():
    copy = CopyAction.from_dict({
        'source': 'aSource',
        'destination': 'aDestination',
        'override': True,
        'switch_to_copy': True,
    })

    assert copy.source == 'aSource'
    assert copy.destination == 'aDestination'
    assert copy.override is True
    assert copy.switch_to_copy is True


def test_copy_source_mandatory():
    with pytest.raises(ScriptError) as e:
        CopyAction.from_dict({
            'destination': 'aDestination'
        })

    assert str(e.value) == 'Key \'source\' is mandatory'


def test_copy_destination_mandatory():
    with pytest.raises(ScriptError) as e:
        CopyAction.from_dict({
            'source': 'aSource'
        })

    assert str(e.value) == 'Key \'destination\' is mandatory'


def test_use_default():
    use = UseAction.from_dict({
        'volume_name': 'aVolume'
    })

    assert use.volume == 'aVolume'


def test_use_volume_mandatory():
    with pytest.raises(ScriptError) as e:
        UseAction.from_dict({})

    assert str(e.value) == 'Key \'volume_name\' is mandatory'


def test_rm_default():
    use = RemoveAction.from_dict({
        'volume_names': ['aVolume', 'aVolume2']
    })

    assert use.volumes == ['aVolume', 'aVolume2']


def test_rm_volume_not_an_array():
    with pytest.raises(ScriptError) as e:
        RemoveAction.from_dict({'volume_names': 'aVolume'})

    assert str(e.value) == 'key \'volume_names\' is not an array'


def test_rm_volume_mandatory():
    with pytest.raises(ScriptError) as e:
        RemoveAction.from_dict({})

    assert str(e.value) == 'Key \'volume_names\' is mandatory'


def test_error():
    error = ErrorAction.from_dict({
        'message': 'an error'
    })

    assert error.message == 'an error'


def test_py_default():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    py = PyCodeAction.from_dict({
        'file': py_file,
        'function': 'a_fn'
    })

    assert py.file == Path(py_file).resolve()
    assert py.function == 'a_fn'


def test_py_file_mandatory():
    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'function': 'a_fn'
        })

    assert str(e.value) == 'Key \'file\' is mandatory'


def test_py_file_exists():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code_not_exist.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'a_fn'
        })

    assert str(e.value) == f'Action py : Path {py_file} does not exist'


def test_py_function_mandatory():
    with pytest.raises(ScriptError) as e:
        py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

        PyCodeAction.from_dict({
            'file': py_file
        })

    assert str(e.value) == 'Key \'function\' is mandatory'


def test_py_function_execute():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    actions = PyCodeAction.from_dict({
        'file': py_file,
        'function': 'not_found_copy_list'
    }).execute()

    assert actions == [CopyAction(source='dev', destination='dev-x')]


def test_py_function_execute_no_array():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    actions = PyCodeAction.from_dict({
        'file': py_file,
        'function': 'not_found_copy_no_array'
    }).execute()

    assert actions == [CopyAction(source='dev', destination='dev-x')]


def test_py_function_execute_all_actions():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    actions = PyCodeAction.from_dict({
        'file': py_file,
        'function': 'not_found_all_actions'
    }).execute()

    assert actions == [
        CopyAction(source='dev', destination='dev-x'),
        UseAction(volume='dev'),
        RemoveAction(volumes=['dev-y']),
        ErrorAction()
    ]


def test_py_function_execute_error_py():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'not_found_py'
        }).execute()

    print(e)

    assert str(e.value) == f'Action \'py\' is not authorize from a py action'


def test_py_function_execute_error_action_unknown():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'not_found_action_unknown'
        }).execute()

    print(e)

    assert str(e.value) == f'Action \'action\' is unknown'


def test_py_function_execute_none():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    actions = PyCodeAction.from_dict({
        'file': py_file,
        'function': 'not_found_none'
    }).execute()

    assert actions is None


def test_py_function_execute_fn_not_exists():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'fn_not_exists'
        }).execute()

    assert str(e.value) == f'function \'fn_not_exists\' does not exist in \'{py_file}\''


def test_py_function_execute_fn_return_error():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'not_found_unknown_obj'
        }).execute()

    assert str(e.value) == 'function not_found_unknown_obj return \'object\' but this is not an action or a list of ' \
                           'action'


def test_py_function_execute_fn_raise_exception():
    py_file = str(TEST_FOLDER / 'resources/py/test_py_code.py')

    with pytest.raises(ScriptError) as e:
        PyCodeAction.from_dict({
            'file': py_file,
            'function': 'not_found_raise'
        }).execute()

    assert str(e.value) == 'function not_found_raise raise an error : ValueError(\'exception message\')'
