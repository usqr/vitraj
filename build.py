from os.path import dirname, join
import sys
sys.path.append(join(dirname(__file__), *'src/build/python'.split('/')))

from fbs_runtime.platform import is_windows, is_mac, is_linux, is_ubuntu, \
	is_fedora, is_arch_linux, linux_distribution
from os.path import dirname

import fbs.builtin_commands
import fbs.cmdline

# Import fbs's built-in commands first (above). The imports below then
# replace some of them (for example freeze) with vitraj's own versions.
# The other order would silently use fbs's freeze, without the Sparkle
# copy, the bundle strip and the ad-hoc signing.
# These imports register the platform's build commands with fbs (the
# @command decorator runs on import). So the names are not used here.
if is_windows():
	from build_impl.windows import freeze # noqa: F401
	from fbs.builtin_commands import sign, installer, sign_installer # noqa: F401
elif is_mac():
	from build_impl.mac import freeze, sign, sign_installer # noqa: F401
	from fbs.builtin_commands import installer # noqa: F401
elif is_linux():
	from fbs.builtin_commands import installer # noqa: F401
	if is_ubuntu() or linux_distribution() == 'Debian GNU/Linux':
		from build_impl.ubuntu import freeze # noqa: F401
	elif is_arch_linux():
		from build_impl.arch import freeze # noqa: F401
		from fbs.builtin_commands import sign_installer # noqa: F401
	elif is_fedora():
		from build_impl.fedora import freeze # noqa: F401
		from fbs.builtin_commands import sign_installer # noqa: F401
	else:
		raise NotImplementedError(linux_distribution())

if __name__ == '__main__':
	project_dir = dirname(__file__)
	fbs.cmdline.main(project_dir)