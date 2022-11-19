import sys

from aki._colorize import colorize_in_red, colorize_in_green

PRINT_VERBOSE = False


def _set_print_verbose(new_print_verbose):
    """
    Set if the script can print verbose text
    """
    global PRINT_VERBOSE
    PRINT_VERBOSE = new_print_verbose


def print_info(text: str = '', **kwargs):
    """
    Print text
    """
    print(text, **kwargs)


def print_error(text, **kwargs):
    """
    Print error text to file sys.stderr
    """
    print(colorize_in_red(text), file=sys.stderr, **kwargs)


def print_success(text, **kwargs):
    """
    Print success text
    """
    print(colorize_in_green(text), **kwargs)


def print_verbose(text='', **kwargs):
    """
    Print verbose text
    """
    if PRINT_VERBOSE:
        print(text, **kwargs)
    else:
        pass


def print_debug_def(fn, **kwargs):
    """
    If verbose, execute function and print result
    """
    if PRINT_VERBOSE:
        print(fn(), **kwargs)
    else:
        pass
