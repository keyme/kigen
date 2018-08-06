#!/usr/bin/env python3
import os
from unittest.mock import patch
import unittest

import kigen

_test_block = """This is just a test
# KIGEN_start foo_func arg1:a arg2:b arg3:c
# Yeah, just a comment
# WOO!
# KIGEN_end
Some useless stuff
// C style inline comments work too
// KIGEN_start bar_func arg1:a arg2:c arg3:e
int main() {
  dothebusiness();
}
// KIGEN_end

Need to test empty blocks
## KIGEN_start baz_func
## KIGEN_end
"""

_test_block_content = [
    "This is just a test",
    "Some useless stuff\n// C style inline comments work too",
    "\nNeed to test empty blocks"
]

_test_block2 = """# KIGEN_start foo_func
# KIGEN_end
This is just a test
# KIGEN_start foo_func arg1:a arg2:b arg3:c
# Yeah, just a comment
# WOO!
# KIGEN_end
Some useless stuff
// C style inline comments work too
// KIGEN_start bar_func arg1:a arg2:c arg3:e
int main() {
  dothebusiness();
}
// KIGEN_end

Need to test empty blocks
## KIGEN_start baz_func
## KIGEN_end
"""

_test_block2_content = [
    '',
    "This is just a test",
    "Some useless stuff\n// C style inline comments work too",
    "\nNeed to test empty blocks"
]

_block_positions = (
    (1, 4),
    (7, 11),
    (14, 15)
)

_block_funcs = (
    'foo_func',
    'bar_func',
    'baz_func'
)

_block_args = (
    {'arg1': 'a', 'arg2': 'b', 'arg3': 'c'},
    {'arg1': 'a', 'arg2': 'c', 'arg3': 'e'},
    {}
)

_module_dir_data = {
    'expected_modules': [
        'foo',
        'bar',
        'baz'
    ]
}

_basic_template = "Hello {{ name }}"
_basic_args = {'name': 'Larry'}
_basic_expectation = "Hello Larry"

TEST_DATA_DIR = os.path.join('.', 'test_collateral')


class TestKiGen(unittest.TestCase):
    def test_block_extraction(self):
        blocks = kigen.extract_blocks(_test_block)
        assert len(blocks) == len(_block_positions)

        for idx, block in enumerate(blocks):
            assert block.start == _block_positions[idx][0]
            assert block.end == _block_positions[idx][1]
            assert block.command.function == _block_funcs[idx]
            assert len(block.command.args) == len(_block_args[idx])
            for arg in block.command.args:
                assert block.command.args[arg] == _block_args[idx][arg]

    def test_module_extraction(self):
        modules = kigen.enumerate_modules_in_dir(TEST_DATA_DIR)
        assert sorted(modules) == sorted(_module_dir_data['expected_modules'])

    def test_split_at_blocks_lead_in(self):
        blocks = kigen.extract_blocks(_test_block)
        file_chunks = kigen.split_file_at_blocks(_test_block, blocks)
        assert file_chunks == _test_block_content

    def test_split_at_blocks_no_lead_in(self):
        blocks = kigen.extract_blocks(_test_block2)
        file_chunks = kigen.split_file_at_blocks(_test_block2, blocks)
        assert file_chunks == _test_block2_content

    def test_basic_expansion(self):
        result = kigen.expand_template(_basic_template, _basic_args)
        assert result == _basic_expectation

    def test_module_loading(self):
        module_names = kigen.enumerate_modules_in_dir(TEST_DATA_DIR)
        modules = kigen.load_modules(TEST_DATA_DIR, module_names)
        assert sorted(modules.keys()) == sorted(module_names)
