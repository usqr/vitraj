"""
The settings of the build: src/build/settings/<profile>.json, loaded with
the same rules as the app (vitraj.impl.build_settings).
"""
from vitraj.impl.build_settings import PROJECT_DIR, expand_placeholders, \
	get_profiles, load_project_settings
from os.path import isabs, join, normpath

SETTINGS = {}

def init(release=False):
	SETTINGS.clear()
	SETTINGS.update(load_project_settings(PROJECT_DIR, get_profiles(release)))

def path(path_str):
	"""
	The absolute path of the given project file. Use forward slashes. Settings
	placeholders work, for example path('${freeze_dir}/Contents').
	"""
	path_str = expand_placeholders(path_str, SETTINGS)
	if isabs(path_str):
		return normpath(path_str)
	return normpath(join(PROJECT_DIR, *path_str.split('/')))
