from build_impl.linux import postprocess_exe
from fbs.cmdline import command
from fbs.freeze.arch import freeze_arch

@command
def freeze():
	freeze_arch()
	postprocess_exe()
