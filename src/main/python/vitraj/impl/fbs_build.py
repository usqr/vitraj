"""
The only place where the app reads data that the fbs build system makes:
the build settings and, when vitraj runs from source, the resource dirs.

This is temporary. In the frozen app, `fbs freeze` injects the build
settings into fbs_runtime._frozen.BUILD_SETTINGS with a PyInstaller runtime
hook. When the build no longer uses fbs, replace this module.
"""
from vitraj.impl.app_context_base import is_frozen

def load_build_settings():
	if is_frozen():
		from fbs_runtime._frozen import BUILD_SETTINGS
		return BUILD_SETTINGS
	from fbs_runtime._source import load_build_settings, get_project_dir
	return load_build_settings(get_project_dir())

def get_source_resource_dirs():
	from fbs_runtime._source import get_resource_dirs, get_project_dir
	return get_resource_dirs(get_project_dir())
