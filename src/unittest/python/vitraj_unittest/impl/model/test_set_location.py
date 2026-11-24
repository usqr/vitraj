from vitraj.impl.model import SortedFileSystemModel
from vitraj.impl.plugins.builtin import NullFileSystem, NullColumn
from vitraj.impl.plugins.mother_fs import MotherFileSystem
from vitraj.impl.util.qt.thread import is_in_main_thread
from vitraj_unittest.impl.model import StubFileSystem
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from unittest import TestCase

import sys

_app = QApplication.instance() or QApplication([])

class SetLocationTest(TestCase):
	"""
	SortedFileSystemModel#set_location(...) resolves in a background thread
	and reports errors to onerror(...) in the main thread.
	"""
	def setUp(self):
		self.fs = MotherFileSystem(_StubIconProvider())
		self.fs.add_child('null://', NullFileSystem())
		column = NullColumn()
		self.fs.register_column(column.get_qualified_name(), column)
		self.stub = _RecordingStubFileSystem({
			'': {'is_dir': True, 'files': ['dir']},
			'dir': {'is_dir': True}
		}, default_columns=(column.get_qualified_name(),))
		self.fs.add_child('stub://', self.stub)
		self.model = SortedFileSystemModel(None, self.fs, 'null://')
	def tearDown(self):
		self.model.sourceModel().shutdown()
		self.model._resolver.shutdown()
	def test_resolves_outside_main_thread(self):
		self.model.set_location('stub://dir')
		self.assertTrue(_wait_until(
			lambda: self.model.get_location() == 'stub://dir'
		))
		self.assertEqual([False], self.stub.resolved_in_main_thread)
	def test_error_goes_to_onerror_in_main_thread(self):
		calls = []
		def onerror(e, url):
			calls.append((type(e), url, is_in_main_thread()))
		self.model.set_location('stub://missing', onerror=onerror)
		self.assertTrue(_wait_until(lambda: calls))
		self.assertEqual([(FileNotFoundError, 'stub://missing', True)], calls)
		self.assertEqual('null://', self.model.get_location())
	def test_onerror_gives_next_url(self):
		self.model.set_location(
			'stub://missing', onerror=lambda e, url: 'stub://dir'
		)
		self.assertTrue(_wait_until(
			lambda: self.model.get_location() == 'stub://dir'
		))
	def test_bare_raise_in_onerror_goes_to_excepthook(self):
		reported = self._capture_excepthook()
		def onerror(e, url):
			raise
		self.model.set_location('stub://missing', onerror=onerror)
		self.assertTrue(_wait_until(lambda: reported))
		self.assertEqual([FileNotFoundError], reported)
	def test_same_failing_url_goes_to_excepthook(self):
		reported = self._capture_excepthook()
		self.model.set_location(
			'stub://missing', onerror=lambda e, url: 'stub://missing'
		)
		self.assertTrue(_wait_until(lambda: reported))
		self.assertEqual([FileNotFoundError], reported)
	def test_later_call_wins(self):
		self.model.set_location('stub://dir')
		self.model.set_location('stub://')
		QTest.qWait(200)
		self.assertEqual('stub://', self.model.get_location())
	def _capture_excepthook(self):
		reported = []
		excepthook_before = sys.excepthook
		sys.excepthook = lambda *args: reported.append(args[0])
		self.addCleanup(setattr, sys, 'excepthook', excepthook_before)
		return reported

def _wait_until(condition, timeout_ms=3000):
	waited = 0
	while not condition() and waited < timeout_ms:
		QTest.qWait(10)
		waited += 10
	return bool(condition())

class _StubIconProvider:
	def get_icon(self, url):
		return None

class _RecordingStubFileSystem(StubFileSystem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.resolved_in_main_thread = []
	def resolve(self, path):
		self.resolved_in_main_thread.append(is_in_main_thread())
		return super().resolve(path)
