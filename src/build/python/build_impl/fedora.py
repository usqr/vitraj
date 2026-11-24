from build_impl.linux import postprocess_exe
from fbs.cmdline import command
from fbs.freeze.fedora import freeze_fedora

@command
def freeze():
	freeze_fedora()
	postprocess_exe()
