from build_impl import copy_python_library
from build_impl.freeze import generate_resources, run_pyinstaller
from build_impl.settings import path
from os import remove
from os.path import join, dirname
from shutil import copy, rmtree

def freeze():
	run_pyinstaller(['--icon', path('src/main/icons/Icon.ico')])
	generate_resources()
	copy(path('src/main/icons/Icon.ico'), path('${freeze_dir}'))
	_copy_winpty_files()
	rmtree(path('${core_plugin_in_freeze_dir}/bin/mac'))
	rmtree(path('${core_plugin_in_freeze_dir}/bin/linux'))
	# Open Sans is only used on Linux. Further, it fails to load on some users'
	# Windows systems (see fman issue #480). Remove it to avoid problems,
	# improve startup performance and decrease fman's download size.
	# (Also note that a more elegant solution would be to only place
	# Open Sans.ttf in src/main/resources/*linux*/Plugins/Core. But the current
	# implementation cannot handle multiple dirs .../resources/main,
	# .../resources/linux for one plugin.)
	remove(path('${core_plugin_in_freeze_dir}/Open Sans.ttf'))
	copy_python_library('send2trash', path('${core_plugin_in_freeze_dir}'))

def _copy_winpty_files():
	import winpty
	winpty_dir = dirname(winpty.__file__)
	copy(join(winpty_dir, 'winpty-agent.exe'), path('${freeze_dir}'))
