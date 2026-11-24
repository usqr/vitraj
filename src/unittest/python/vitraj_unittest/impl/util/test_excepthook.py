from vitraj.impl.util.excepthook import Excepthook, ExceptionHandler, \
	add_missing_qt_frames, enable_excepthook_for_threads
from threading import Thread
from unittest import TestCase

import sys
import threading

class ExcepthookTest(TestCase):
	def test_handlers_run_in_order_until_one_returns_true(self):
		calls = []
		hook = Excepthook([
			_Recorder(calls, 'a'), _Recorder(calls, 'b', stop=True),
			_Recorder(calls, 'c')
		])
		hook(*_exc_info())
		self.assertEqual(['a', 'b'], calls)
	def test_system_exit_is_ignored(self):
		calls = []
		hook = Excepthook([_Recorder(calls, 'a')])
		hook(SystemExit, SystemExit(0), None)
		self.assertEqual([], calls)
	def test_install_inits_handlers_and_sets_sys_excepthook(self):
		calls = []
		handler = _Recorder(calls, 'a')
		hook = Excepthook([handler])
		hook_before = sys.excepthook
		init_before = threading.Thread.__init__
		try:
			hook.install()
			self.assertIs(hook, sys.excepthook)
			self.assertTrue(handler.inited)
		finally:
			sys.excepthook = hook_before
			threading.Thread.__init__ = init_before

class ThreadExceptionsTest(TestCase):
	def test_thread_exception_goes_to_sys_excepthook(self):
		reported = []
		hook_before = sys.excepthook
		init_before = threading.Thread.__init__
		sys.excepthook = lambda *args: reported.append(args[0])
		try:
			enable_excepthook_for_threads()
			thread = Thread(target=lambda: 1 / 0)
			thread.start()
			thread.join()
		finally:
			sys.excepthook = hook_before
			threading.Thread.__init__ = init_before
		self.assertEqual([ZeroDivisionError], reported)

class AddMissingQtFramesTest(TestCase):
	def test_contains_caller_frames(self):
		def inner():
			raise ValueError()
		try:
			inner()
		except ValueError:
			tb = sys.exc_info()[2]
		names = []
		fake = add_missing_qt_frames(tb)
		while fake:
			names.append(fake.tb_frame.f_code.co_name)
			fake = fake.tb_next
		self.assertIn('test_contains_caller_frames', names)
		self.assertEqual('inner', names[-1])

class _Recorder(ExceptionHandler):
	def __init__(self, calls, name, stop=False):
		self._calls = calls
		self._name = name
		self._stop = stop
		self.inited = False
	def init(self):
		self.inited = True
	def handle(self, exc_type, exc_value, enriched_tb):
		self._calls.append(self._name)
		return self._stop

def _exc_info():
	try:
		raise ValueError('x')
	except ValueError:
		return sys.exc_info()
