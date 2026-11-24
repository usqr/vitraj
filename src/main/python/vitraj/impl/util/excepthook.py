"""
vitraj's sys.excepthook. This replaces fbs_runtime.excepthook with the same
behavior:

 1. It adds the stack frames that PyQt hides when Python code calls Qt code
    that calls Python code again (see add_missing_qt_frames).
 2. It also receives the exceptions of other threads.
 3. It calls a list of ExceptionHandlers, until one of them returns True.
"""
from collections import namedtuple

import sys
import threading
import traceback

class ExceptionHandler:
	"""Extend this class and add it to the exception handlers of the app."""
	def init(self):
		pass
	def handle(self, exc_type, exc_value, enriched_tb):
		"""Return True to stop the handlers after this one."""
		raise NotImplementedError()

class StderrExceptionHandler(ExceptionHandler):
	def handle(self, exc_type, exc_value, enriched_tb):
		# sys.__excepthook__ does not work with the "fake" traceback of
		# add_missing_qt_frames(...). This call gives the same output:
		traceback.print_exception(exc_type, exc_value, enriched_tb)

class Excepthook:
	def __init__(self, handlers):
		self._handlers = handlers
	def install(self):
		for handler in self._handlers:
			handler.init()
		sys.excepthook = self
		enable_excepthook_for_threads()
	def __call__(self, exc_type, exc_value, exc_tb):
		if isinstance(exc_value, SystemExit):
			return
		enriched_tb = add_missing_qt_frames(exc_tb) if exc_tb else exc_tb
		for handler in self._handlers:
			if handler.handle(exc_type, exc_value, enriched_tb):
				break

def enable_excepthook_for_threads():
	"""
	Send the exceptions of threading.Thread objects to sys.excepthook. (By
	default, Python sends them to threading.excepthook instead.)
	"""
	init_original = threading.Thread.__init__
	def init(self, *args, **kwargs):
		init_original(self, *args, **kwargs)
		run_original = self.run
		def run_with_except_hook(*args2, **kwargs2):
			try:
				run_original(*args2, **kwargs2)
			except Exception:
				sys.excepthook(*sys.exc_info())
		self.run = run_with_except_hook
	threading.Thread.__init__ = init

def add_missing_qt_frames(tb):
	"""
	If Python function f calls Qt function g, and g calls Python function h
	which raises, then the traceback does not contain f. Return a "fake"
	traceback that also contains the frames of the callers.
	"""
	result = _FakeTb(tb.tb_frame, tb.tb_lasti, tb.tb_lineno, tb.tb_next)
	frame = tb.tb_frame.f_back
	while frame:
		result = _FakeTb(frame, frame.f_lasti, frame.f_lineno, result)
		frame = frame.f_back
	return result

_FakeTb = namedtuple('fake_tb', ('tb_frame', 'tb_lasti', 'tb_lineno', 'tb_next'))
