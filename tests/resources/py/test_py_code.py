from pathlib import Path


def not_found_copy_list():
    return [{'action': 'copy', 'source': 'dev', 'destination': 'dev-x'}]


def not_found_copy_no_array():
    return {'action': 'copy', 'source': 'dev', 'destination': 'dev-x'}


def not_found_all_actions():
    return [
        {'action': 'copy', 'source': 'dev', 'destination': 'dev-x'},
        {'action': 'use', 'volume_name': 'dev'},
        {'action': 'remove', 'volume_names': ['dev-y']},
        {'action': 'error'}
    ]


def not_found_unknown_obj():
    return 'object'


def not_found_raise():
    raise ValueError('exception message')


def not_found_none():
    return None


def not_found_py():
    return {'action': 'py', 'file': Path(__file__).resolve().parent.parent, 'function': 'a_fn'}


def not_found_action_unknown():
    return {'action': 'action'}
