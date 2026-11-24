from build_impl import check_output_decode, remove_if_exists
from build_impl.linux import postprocess_exe
from fbs import path
from fbs.cmdline import command
from fbs.freeze.ubuntu import freeze_ubuntu

import re

@command
def freeze():
	freeze_ubuntu()
	postprocess_exe()
	# We're using Python library `pgi` instead of `gi`, `GObject` or other more
	# well-known alternatives. PyInstaller does not know how to handle this
	# properly and includes .so files it shouldn't include. In particular, we
	# use libgtk-3.so.0 via pgi. PyInstaller does *not* include that file. BUT
	# it does include some of its dependencies. When we then deploy fman to a
	# different Linux version, PyInstaller loads that distribution's
	# libgtk-3.so.0 but our copy of its dependencies, which fails. We thus
	# exclude the dependencies so that when fman runs on a different system,
	# PyInstaller loads the dependencies from that system:
	_remove_gtk_dependencies()

def _remove_gtk_dependencies():
	output = check_output_decode(
		'ldd /usr/lib/x86_64-linux-gnu/libgtk-3.so.0', shell=True
	)
	assert output.endswith('\n')
	for line in output.split('\n')[:-1]:
		if not '=>' in line:
			continue
		match = re.match('\t(?:(.*) => )?(.*) \(0x[0-9a-f]+\)', line)
		if not match:
			raise ValueError(repr(line))
		so_name, so_path = match.groups()
		if so_name and so_path:
			# libQt5Widgets.so.0 depends on libpng12.so.0. This file is present
			# on Ubuntu versions < 17.04. On 17.04 (and above?), libpng16.so.0
			# is used instead. We therefore need to keep libpng12.so.0 so fman
			# can run on Ubuntu 17.04+:
			if so_name != 'libpng12.so.0':
				remove_if_exists(path('${freeze_dir}/' + so_name))
