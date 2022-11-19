from aki._colorize import colorize_in_red, colorize_in_green, colorize


def test_colorize_red():
    assert colorize_in_red('test') == '\033[31mtest\033[0m'


def test_colorize_green():
    assert colorize_in_green('test') == '\033[32mtest\033[0m'


def test_colorize():
    assert colorize(33, 'test') == '\033[33mtest\033[0m'
