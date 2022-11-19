_TEXT_RED = 31
_TEXT_GREEN = 32


def colorize(color, message):
    return f'\033[{color}m{message}\033[0m'


def colorize_in_red(message):
    return colorize(_TEXT_RED, message)


def colorize_in_green(message):
    return colorize(_TEXT_GREEN, message)
