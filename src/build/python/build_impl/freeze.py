"""
The freeze with PyInstaller. It replaces `fbs freeze`, with the same result:

 1. PyInstaller makes target/vitraj(.app).
 2. The public build settings go into build_settings.json in the resources.
    The frozen app reads them from there.
 3. src/freeze/<profile> goes into the app dir, and src/main/resources/
    <profile> into its resources dir. "${setting}" placeholders are filled
    in the files that the setting files_to_filter lists.
"""
from build_impl.settings import SETTINGS, path
from vitraj.impl.build_settings import FROZEN_SETTINGS_FILE, get_profiles, \
	filter_public_settings
from vitraj.impl.util.platform_ import is_mac
from os import makedirs, walk
from os.path import dirname, exists, join, relpath
from shutil import copy, copymode
from subprocess import run

import json
import os

def run_pyinstaller(extra_args=()):
	app_name = SETTINGS['app_name']
	args = [
		'pyinstaller', '--name', app_name, '--noupx', '--log-level', 'ERROR',
		'--noconfirm'
	]
	if not SETTINGS.get('show_console_window', False):
		args.append('--windowed')
	for hidden_import in SETTINGS['hidden_imports']:
		args.extend(['--hidden-import', hidden_import])
	args.extend(SETTINGS['extra_pyinstaller_args'])
	args.extend(extra_args)
	args.extend([
		'--distpath', path('target'),
		'--specpath', path('target/PyInstaller'),
		'--workpath', path('target/PyInstaller'),
		path(SETTINGS['main_module'])
	])
	run(args, check=True)

def get_resources_dir():
	if is_mac():
		return path('${freeze_dir}/Contents/Resources')
	return path('${freeze_dir}')

def generate_resources():
	for profile in get_profiles():
		copy_with_filtering(path('src/freeze/' + profile), path('${freeze_dir}'))
		copy_with_filtering(
			path('src/main/resources/' + profile), get_resources_dir()
		)
	write_build_settings(get_resources_dir())

def write_build_settings(dest_dir):
	makedirs(dest_dir, exist_ok=True)
	with open(join(dest_dir, FROZEN_SETTINGS_FILE), 'w') as f:
		json.dump(filter_public_settings(SETTINGS), f, indent='\t')

def copy_with_filtering(src_dir, dest_dir):
	"""
	Copy src_dir into dest_dir. In the files that files_to_filter lists, fill
	in "${setting}" placeholders.
	"""
	if not exists(src_dir):
		return
	to_filter = {path(p) for p in SETTINGS.get('files_to_filter', [])}
	for subdir, _, files in walk(src_dir):
		for name in files:
			src = join(subdir, name)
			if '__pycache__' in relpath(src, src_dir).split(os.sep):
				continue
			dest = join(dest_dir, relpath(src, src_dir))
			makedirs(dirname(dest), exist_ok=True)
			if src in to_filter:
				_copy_filtered(src, dest)
			else:
				copy(src, dest)

def _copy_filtered(src, dest):
	with open(src, 'rb') as f:
		data = f.read()
	for key, value in SETTINGS.items():
		data = data.replace(
			('${%s}' % key).encode('utf-8'), str(value).encode('utf-8')
		)
	with open(dest, 'wb') as f:
		f.write(data)
	copymode(src, dest)
