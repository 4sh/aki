from sys import platform


def is_linux():
    return platform == "linux" or platform == "linux2"
