#!/usr/bin/env python3
import argparse
import collections
import itertools
import os
import pathlib
import pkgutil
import sys

import jinja2

START_MARKER = 'KIGEN_start'
STOP_MARKER = 'KIGEN_end'

ModuleCmd = collections.namedtuple('ModuleCmd', 'function args')
AutogenBlock = collections.namedtuple('AutogenBlock',
                                      'start end command commentmark')
ModuleSpace = collections.namedtuple('ModuleSpace',
                                     'base_path modules')
ExpansionModule = collections.namedtuple('ExpansionModule',
                                         'name base_path module')


class NestedBlockError(Exception):
    pass


class DanglingBlockEnd(Exception):
    pass


class UnknownExpansionModule(Exception):
    pass


class InvalidContent(Exception):
    pass


class ModuleConflict(Exception):
    pass


def expand_template(template_str: str, content) -> str:
    """Given a jinja template and a dictionary containing autogeneration
    fill content, returns a rendered template as a string.

    """
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
    """Given a line containing an autogen command string (i.e.`KIGEN_start
    foo bar:baz`) returns a tuple containing any leading comment
    marker (`#`, `//`, etc) and a ModuleCmd object

    """
    # Remove the marker leaving us with just a function and its
    # (optional) arguments
    commentmarker, line = split_marker(line)

    # Remove any pesky whitespace
    line = line.strip()

    function, *raw_args = line.split(' ')
    args = extract_args(raw_args)

    return commentmarker, ModuleCmd(function, args)


def extract_blocks(file_data: str):
    """Given a string, extracts all autogen blocks and returns a list of
    AutogenBlock objects

    """
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


def split_file_at_blocks(file_data: str, blocks):
    """Given a string and a list of AutogenBlock objects, returns a list
    of strings WITHOUT any autogen blocks present (i.e. a string split
    on AutogenBlocks)

    """
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

    mod_list = list(set(py_files).intersection(set(jinja_files)))
    return ModuleSpace(path, mod_list)


# Adapted from https://stackoverflow.com/questions/1057431
def load_modules(path: str, known_modules):
    """Given a path string and a list of strings representing module
    names, dynamically loads each python module provided it exists in
    the path and the list of known_modules and adds it to sys.modules
    (if it isn't already there).

    Returns a dictionary in the form {name: module,...}

    """
    result = {}
    for importer, package_name, _ in pkgutil.iter_modules([path]):
        full_package_name = '{}'.format(package_name)
        # Skip random python files that aren't part of the module
        if full_package_name not in known_modules:
            continue

        if full_package_name not in sys.modules:
            module = (importer.find_module(package_name)
                      .load_module(full_package_name))
        else:
            module = sys.modules[full_package_name]

        print("Loading module: {}".format(module.__name__))
        result[module.__name__] = module
    return result


def build_module_dict(path):
    """Returns a dictionary of all autogen modules in a given path

    """
    mod_space = enumerate_modules_in_dir(path)
    loader_dict = load_modules(path, mod_space.modules)
    return {
        k: ExpansionModule(k, mod_space.base_path, v)
        for k, v in loader_dict.items()
    }


def command_to_cmdstr(command: ModuleCmd) -> str:
    """ Renders a ModuleCmd as a string
    """
    function = "{}".format(command.function)
    arg_strs = []
    for k, v in command.args.items():
        arg_strs.append('{}:{}'.format(k, v))

    return ' '.join([function] + arg_strs)


def block_to_start_string(block: AutogenBlock) -> str:
    """ Renders an AutogenBlock as a start string
    """
    cmd = block.command
    result = "{} KIGEN_start {}".format(block.commentmark,
                                        command_to_cmdstr(cmd))

    return result


def block_to_end_string(block: AutogenBlock) -> str:
    """ Renders an AutogenBlock as an ending string
    """
    result = "{} KIGEN_end".format(block.commentmark)

    return result


def expansion_module_to_template(exp_mod: ExpansionModule) -> str:
    """Reads the template portion of an ExpansionMOdule and returns a
    string with its contents

    """
    path = os.path.join(exp_mod.base_path,
                        '{}.jinja2'.format(exp_mod.name))

    with open(path) as ifile:
        return ifile.read()


def render_block(block: AutogenBlock, modules) -> str:
    """Given an AutogenBlock and a dictionary of Modules, returns the
    rendered body of the block as a string

    """
    start_str = block_to_start_string(block)

    try:
        exp_mod = modules[block.command.function]
    except KeyError:
        mod_dirs = [x.base_path for x in modules.values()]
        mod_dir_str = '\n'.format(['- {}'.format(x) for x in mod_dirs])
        raise UnknownExpansionModule("Expansion module `{}` not found "
                                     "in any of the following directories: {}"
                                     .format(block.command.function,
                                             mod_dir_str))

    content = exp_mod.module.get_content(**block.command.args)
    if type(content) != dict:
        raise InvalidContent("get_content functions must return a dictionary!"
                             "\nModule {} located in {} does not"
                             .format(exp_mod.name, exp_mod.base_path))

    template = expansion_module_to_template(exp_mod)

    body = expand_template(template, content)
    end_str = block_to_end_string(block)

    return '\n'.join([start_str, body, end_str])


def recombine(chunks, blocks) -> str:
    """Given a list of strings containing the non-autogen portions of a
    file, and a list of strings containng rendered AutogenBlocks,
    returns the combined content as a single string

    """
    return '\n'.join(itertools.chain(*zip(chunks, blocks)))


def render_file(input_file_text: str, modules) -> str:
    """Given a string of file contents and a dictionary of modules,
    returns a string containing the fully rendered/autogenerated file

    """
    blocks = extract_blocks(input_file_text)
    chunks = split_file_at_blocks(input_file_text, blocks)

    expanded_blocks = [render_block(x, modules) for x in blocks]

    recombined_file = recombine(chunks, expanded_blocks)

    return recombined_file


def load_multiple_module_dirs(mod_paths):
    """Given a list of strings representing directories, returns a
    dictionary of ExpansionModule objects. This dictionary will have
    only unique keys with single modules as values. If there is a
    naming conflict (i.e. two modules named `foo` in two separate
    directories) a ModuleConflict will be raised.

    """
    result = {}
    for path in mod_paths:
        assert os.path.isdir(path), "{} is not a directory!".format(path)
        local_mod = build_module_dict(path)
        for k, v in local_mod.items():
            if k in result:
                raise ModuleConflict(
                    "Module {} in {} conflicts with module {} in {}"
                    .format(k, v.base_path, k, result[k].base_path)
                )
            result[k] = v
    return result


def read_and_render_file(original_file: str, modules) -> str:
    """Given a string representing a path to a file and a dictionary of
    ExpansionModules, returns a string contianing the fully rendered
    file.

    """
    with open(original_file) as ifile:
        file_data = ifile.read()

    return render_file(file_data, modules)


def write_file(data: str, original_path: str, output_dir: str=None):
    """Given a string containing the file contents, the original file
    path, and an (optional) output directory, writes the file data to disk.

    If output_dir is None, the original file is overwritten (i.e. autogen in-place).

    If output_dir does not exist, it will be created (as will all
    parent directories).

    """
    if output_dir:
        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, os.path.basename(original_path))
        print("Rendering {} to {}".format(original_path, output_path))
    else:
        print("Rendering {} in place".format(original_path))
        output_path = original_path

    with open(output_path, 'w') as ofile:
        ofile.write(data)


def main(input_files, module_path, output_dir=None):

    # First, lets build up a giant dictionary of expansion modules
    modules = load_multiple_module_dirs(module_path)

    for ifile in input_files:
        assert os.path.isfile(ifile)

        file_data = read_and_render_file(ifile, modules)
        write_file(file_data, ifile, output_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument(
        '-i', '--input-files',
        nargs='*',
        required=True,
        help='Files to autogen'
    )
    parser.add_argument(
        '-m', '--module-path',
        nargs='*',
        required=True,
        help='Directories in which to search for autogen modules'
    )
    parser.add_argument(
        '-o', '--output-dir',
        action="store",
        help="If not in-place, a directory in which "
        "to save autogenerated files"
    )
    args = parser.parse_args()
    main(**vars(args))
