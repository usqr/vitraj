"""
The OS and the desktop that vitraj runs on. This replaces
fbs_runtime.platform, with the same results, so that the app code does not
depend on fbs.
"""
import os
import sys

def name(sys_platform=None):
	"""Return 'Windows', 'Mac' or 'Linux'."""
	sys_platform = sys.platform if sys_platform is None else sys_platform
	if sys_platform in ('win32', 'cygwin'):
		return 'Windows'
	if sys_platform == 'darwin':
		return 'Mac'
	if sys_platform.startswith('linux'):
		return 'Linux'
	raise RuntimeError('Unknown operating system: %s' % sys_platform)

def is_windows():
	return name() == 'Windows'

def is_mac():
	return name() == 'Mac'

def is_linux():
	return name() == 'Linux'

def is_gnome_based(environ=None):
	environ = os.environ if environ is None else environ
	desktop = environ.get('XDG_CURRENT_DESKTOP', '').lower()
	return desktop in ('unity', 'gnome', 'x-cinnamon')

def is_kde_based(environ=None):
	environ = os.environ if environ is None else environ
	if environ.get('XDG_CURRENT_DESKTOP', '').lower() == 'kde':
		return True
	return environ.get('GDMSESSION', '').lower().startswith('kde')
