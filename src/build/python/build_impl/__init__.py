from fbs_runtime.platform import is_windows, is_mac, is_linux
from importlib import import_module
from os import remove
from os.path import dirname, join, basename
from shutil import copy, copytree
from subprocess import run, check_output

import re
import sys

def copy_framework(src_dir, dest_dir):
	assert is_mac()
	assert basename(src_dir).endswith('.framework')
	run(['cp', '-a', '-p', src_dir, dest_dir], check=True)

def remove_if_exists(file_path):
	try:
		remove(file_path)
	except FileNotFoundError:
		pass

def copy_python_library(name, dest_dir):
	library = import_module(name)
	is_package = re.match(r'^__init__\.pyc?$', basename(library.__file__))
	if is_package:
		package_dir = dirname(library.__file__)
		copytree(package_dir, join(dest_dir, basename(package_dir)))
	else:
		copy(library.__file__, dest_dir)

def get_canonical_os_name():
	if is_windows():
		return 'windows'
	if is_mac():
		return 'mac'
	if is_linux():
		return 'linux'
	raise ValueError('Unknown operating system.')

def check_output_decode(*args, **kwargs):
	return check_output(*args, **kwargs).decode(sys.stdout.encoding)
