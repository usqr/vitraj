from build_impl import copy_python_library
from build_impl.freeze import generate_resources, run_pyinstaller
from build_impl.settings import path
from glob import glob
from os import remove
from shutil import copy, rmtree

def freeze():
	run_pyinstaller()
	generate_resources()
	copy(path('src/main/icons/Icon.ico'), path('${freeze_dir}'))
	# PyInstaller packages these libraries, but the versions of other
	# distributions then fail with "GLIBCXX_... not found". So use the
	# system's own versions:
	for pattern in (
		'libstdc++.so.*', 'libtinfo.so.*', 'libreadline.so.*', 'libdrm.so.*'
	):
		for file_path in glob(path('${freeze_dir}/' + pattern)):
			remove(file_path)
	_postprocess()

def _postprocess():
	rmtree(path('${core_plugin_in_freeze_dir}/bin/mac'))
	rmtree(path('${core_plugin_in_freeze_dir}/bin/windows'))
	# Roboto Bold is only used on Windows. For reasons not yet known, loading
	# fonts sometimes fails. (A known case is that Open Sans fails to load on
	# some user's Windows systems - see fman issue #480). Remove the unused font
	# to avoid potential problems, improve startup performance and decrease
	# fman's download size.
	# (Also note that a more elegant solution would be to only place
	# Open Sans.ttf in src/main/resources/*linux*/Plugins/Core. But the current
	# implementation cannot handle multiple dirs .../resources/main,
	# .../resources/linux for one plugin.)
	remove(path('${core_plugin_in_freeze_dir}/Roboto Bold.ttf'))
	copy_python_library('send2trash', path('${core_plugin_in_freeze_dir}'))