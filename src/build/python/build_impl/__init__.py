from vitraj.impl.util.platform_ import is_mac
from importlib import import_module
from os.path import dirname, join, basename
from shutil import copy, copytree
from subprocess import run

import re

def copy_framework(src_dir, dest_dir):
	assert is_mac()
	assert basename(src_dir).endswith('.framework')
	run(['cp', '-a', '-p', src_dir, dest_dir], check=True)

def copy_python_library(name, dest_dir):
	library = import_module(name)
	is_package = re.match(r'^__init__\.pyc?$', basename(library.__file__))
	if is_package:
		package_dir = dirname(library.__file__)
		copytree(package_dir, join(dest_dir, basename(package_dir)))
	else:
		copy(library.__file__, dest_dir)
