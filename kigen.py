#!/usr/bin/env python3
import collections
import os
import pkgutil
import sys

import jinja2

START_MARKER = 'KIGEN_start'
STOP_MARKER = 'KIGEN_end'

ModuleCmd = collections.namedtuple('ModuleCmd', 'function args')
AutogenBlock = collections.namedtuple('AutogenBlock',
                                      'start end command commentmark')


class NestedBlockError(Exception):
    pass


class DanglingBlockEnd(Exception):
    pass


def expand_template(template_str, content):
    template = jinja2.Template(template_str)
    return template.render(**content)


def split_marker(line) -> str:
    """Returns a tuple containing the comment marker (i.e. // or #) and a
    line absent the start marker and any preceeding comment indicators

    eg: '# KIGEN_start foo bar:baz' -> ('#', 'foo bar:baz')

    """
    idx = line.index(START_MARKER)
    return line[:idx].strip(), line[idx + len(START_MARKER):].strip()


def extract_args(raw_args):
    """Given a list of strings, where each string is in the form
    "key:value", returns a dictionary mapping keys to values

    """
    result = collections.OrderedDict()

    for arg in raw_args:
        k, v = arg.split(':')
        result[k] = v
    return result


def extract_command(line):
    # Remove the marker leaving us with just a function and its
    # (optional) arguments
    commentmarker, line = split_marker(line)

    # Remove any pesky whitespace
    line = line.strip()

    function, *raw_args = line.split(' ')
    args = extract_args(raw_args)

    return commentmarker, ModuleCmd(function, args)


def extract_blocks(file_data):
    result = []
    in_block = False
    block_start = 0
    command = None
    commentmarker = None
    for idx, line in enumerate(file_data.splitlines()):
        if START_MARKER in line:
            if in_block:
                raise NestedBlockError(
                    "Nested blocks are not supported. "
                    "Detected a new block at line {} "
                    "but the block startint at {} has not "
                    "yet been closed"
                    .format(idx, block_start)
                )
            in_block = True
            block_start = idx
            commentmarker, command = extract_command(line)
        if STOP_MARKER in line:
            if not in_block:
                raise DanglingBlockEnd(
                    "The block end at {} has no beginning!"
                    .format(idx)
                )
            in_block = False
            result.append(AutogenBlock(block_start, idx,
                                       command, commentmarker))
    return result


def split_file_at_blocks(file_data, blocks):
    result = []
    index = 0
    file_lines = file_data.splitlines()
    for block in blocks:
        result.append('\n'.join(file_lines[index:block.start]))
        index = block.end + 1
    return result


def file_path_to_base(path: str) -> str:
    """Given any file path (relative or absolute) returns just the
    filename without an extension

    """
    return os.path.splitext(os.path.basename(path))[0]


def enumerate_modules_in_dir(path: str):
    """Given the path to a directory, returns a list of strings
    representing the autogen modules in the folder.

    An autogen module is defined as a pair of files with the same base
    name, but with the extensions .py and .jinja2

    """
    assert os.path.isdir(path)

    files = [x for x in os.listdir(path)
             if os.path.isfile(os.path.join(path, x))]

    py_files = [file_path_to_base(x)
                for x in files if x.endswith('.py')]
    jinja_files = [file_path_to_base(x)
                   for x in files if x.endswith('.jinja2')]

    return list(set(py_files).intersection(set(jinja_files)))


# Adapted from https://stackoverflow.com/questions/1057431
def load_modules(path, known_modules):
    result = {}
    for importer, package_name, _ in pkgutil.iter_modules([path]):
        full_package_name = '{}'.format(package_name)
        # Skip random python files that aren't part of the module
        if full_package_name not in known_modules:
            continue
        if full_package_name not in sys.modules:
            module = (importer.find_module(package_name)
                      .load_module(full_package_name))
            print("Loading module: {}".format(module.__name__))
            result[module.__name__] = module
    return result


def main(input_file, module_path):
    pass


if __name__ == '__main__':
    pass
