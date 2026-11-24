"""The commands of build.py."""
from build_impl.settings import SETTINGS, init, path
from vitraj.impl.util.platform_ import is_linux, is_mac, is_windows
from os import environ, listdir, pathsep
from os.path import isdir, isfile, join
from shutil import rmtree
from unittest import TestSuite, TextTestRunner, defaultTestLoader

import subprocess
import sys

__all__ = ['init', 'get_commands']

def get_commands():
	"""{name: (function, help)} for the current OS."""
	result = {
		'run': (run, 'Run vitraj from source'),
		'test': (test, 'Run the automated tests'),
		'clean': (clean, 'Remove the build output in target/'),
		'freeze': (_platform().freeze, 'Make the standalone app with PyInstaller'),
		'release': (release, 'Show how to release vitraj'),
	}
	if is_mac():
		from build_impl import mac
		result['sign'] = (mac.sign, 'Sign and notarize the app')
		result['sign_installer'] = (mac.sign_installer, 'Sign and notarize the DMG')
	return result

def run():
	env = dict(environ)
	pythonpath = path('src/main/python')
	if env.get('PYTHONPATH'):
		pythonpath += pathsep + env['PYTHONPATH']
	env['PYTHONPATH'] = pythonpath
	process = subprocess.Popen(
		[sys.executable, path(SETTINGS['main_module'])], env=env
	)
	try:
		return process.wait()
	except KeyboardInterrupt:
		# Ctrl+C goes to the app and to this process. The app quits
		# cleanly on it, so wait for that and return its exit code:
		return process.wait()

def test():
	"""Discover the test packages in each of the setting test_dirs."""
	sys.path.append(path('src/main/python'))
	suite = TestSuite()
	for test_dir in map(path, SETTINGS['test_dirs']):
		if not isdir(test_dir):
			continue
		sys.path.append(test_dir)
		for name in sorted(listdir(test_dir)):
			if isfile(join(test_dir, name, '__init__.py')):
				suite.addTest(
					defaultTestLoader.discover(name, top_level_dir=test_dir)
				)
	result = TextTestRunner().run(suite)
	return 0 if result.wasSuccessful() else 1

def clean():
	rmtree(path('target'), ignore_errors=True)

def release():
	print(
		'vitraj releases run on GitHub Actions. To release, push a version\n'
		'tag, for example:\n\n'
		'    git tag v1.7.4 && git push origin v1.7.4\n\n'
		'See "Release pipeline" in AGENTS.md.'
	)

def _platform():
	if is_mac():
		from build_impl import mac as result
	elif is_windows():
		from build_impl import windows as result
	elif is_linux():
		from build_impl import linux as result
	else:
		raise RuntimeError('Unknown operating system.')
	return result
