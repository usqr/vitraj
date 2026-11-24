"""
The build settings of vitraj: src/build/settings/<profile>.json.

The build and the app (when it runs from source) use this module. The frozen
app reads the public settings from FROZEN_SETTINGS_FILE, which the freeze
writes into the app's resources.

The rules are the same as in fbs, which vitraj used before:
 - Later profiles override earlier ones. Lists are joined, dicts merged.
 - "${key}" in a value is replaced by the value of setting "key".
"""
from os.path import abspath, dirname, exists, join
from vitraj.impl.util.platform_ import name as platform_name

import json

FROZEN_SETTINGS_FILE = 'build_settings.json'

# src/main/python/vitraj/impl/build_settings.py -> the project dir:
PROJECT_DIR = abspath(join(dirname(__file__), '..', '..', '..', '..', '..'))

def get_profiles(release=False):
	# The "secret" profile is for local settings that must not go into git.
	result = ['base', 'secret', platform_name().lower()]
	if release:
		result.append('release')
	return result

def load_project_settings(project_dir=PROJECT_DIR, profiles=None):
	if profiles is None:
		profiles = get_profiles()
	json_paths = [
		join(project_dir, 'src', 'build', 'settings', profile + '.json')
		for profile in profiles
	]
	return load_settings(
		[p for p in json_paths if exists(p)], {'project_dir': project_dir}
	)

def load_settings(json_paths, base=None):
	result = dict(base or {})
	for json_path in json_paths:
		with open(json_path, 'r', encoding='utf-8') as f:
			result = _merge(result, json.load(f))
	# Expand until no placeholder changes any more:
	changed = True
	while changed:
		changed = False
		for key, value in result.items():
			new_value = expand_placeholders(value, result)
			if new_value != value:
				result[key] = new_value
				changed = True
				break
	return result

def expand_placeholders(obj, settings):
	if isinstance(obj, str):
		for key, value in settings.items():
			obj = obj.replace('${%s}' % key, str(value))
		return obj
	if isinstance(obj, list):
		return [expand_placeholders(o, settings) for o in obj]
	if isinstance(obj, dict):
		return {k: expand_placeholders(v, settings) for k, v in obj.items()}
	return obj

def filter_public_settings(settings):
	return {key: settings[key] for key in settings['public_settings']}

def _merge(a, b):
	if not a:
		return b
	if type(a) is not type(b):
		raise ValueError('Cannot merge %r and %r' % (a, b))
	if isinstance(a, list):
		return a + b
	if isinstance(a, dict):
		result = dict(a)
		for key, value in b.items():
			result[key] = _merge(a[key], value) if key in a else value
		return result
	return b
