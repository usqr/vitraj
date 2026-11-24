from os.path import dirname, join
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipIf

from threading import Event
from time import sleep

import sys

_PLUGINS = join(
	dirname(__file__), '..', '..', '..', 'main', 'resources', 'base', 'Plugins'
)
for _plugin in ('File Preview', 'File Preview PDF'):
	if join(_PLUGINS, _plugin) not in sys.path:
		sys.path.append(join(_PLUGINS, _plugin))

from PySide6.QtCore import QSize, Qt # noqa: E402
from PySide6.QtGui import QImage # noqa: E402
from vitraj_unittest.qt_wait import qwait # noqa: E402
from PySide6.QtWidgets import QApplication # noqa: E402

from file_preview import PreviewWidget, PreviewImage, _directory_info, \
	_load_qt_image, _LOADING_DELAY_MS # noqa: E402
from file_preview._async import AsyncRunner, Debouncer # noqa: E402
from vitraj.url import as_url # noqa: E402

import file_preview_pdf # noqa: E402

_app = QApplication.instance() or QApplication([])

def _wait_until(condition, timeout_ms=3000):
	waited = 0
	while not condition() and waited < timeout_ms:
		qwait(10)
		waited += 10
	return condition()

def _write_png(path, width, height):
	image = QImage(width, height, QImage.Format_RGB32)
	image.fill(Qt.red)
	assert image.save(str(path))

class DebouncerTest(TestCase):
	def setUp(self):
		self.calls = []
		self.debouncer = Debouncer(self.calls.append, 30)
	def test_first_call_is_immediate(self):
		self.debouncer('a')
		self.assertEqual(['a'], self.calls)
	def test_burst_calls_only_last_after_pause(self):
		for arg in 'abcd':
			self.debouncer(arg)
		self.assertEqual(['a'], self.calls)
		self.assertTrue(_wait_until(lambda: len(self.calls) == 2))
		self.assertEqual(['a', 'd'], self.calls)
	def test_cancel_drops_pending_call(self):
		self.debouncer('a')
		self.debouncer('b')
		self.debouncer.cancel()
		qwait(60)
		self.assertEqual(['a'], self.calls)

class AsyncRunnerTest(TestCase):
	def setUp(self):
		self.runner = AsyncRunner()
		self.results = []
	def test_result_reaches_callback(self):
		self.runner.run(lambda: 42, self.results.append)
		self.assertTrue(_wait_until(lambda: self.results))
		self.assertEqual([42], self.results)
	def test_exception_is_the_result(self):
		self.runner.run(lambda: 1 / 0, self.results.append)
		self.assertTrue(_wait_until(lambda: self.results))
		self.assertIsInstance(self.results[0], ZeroDivisionError)
	def test_later_run_makes_earlier_result_stale(self):
		self.runner.run(lambda: 'old', self.results.append)
		self.runner.run(lambda: 'new', self.results.append)
		self.assertTrue(_wait_until(lambda: self.results))
		qwait(30)
		self.assertEqual(['new'], self.results)
	def test_cancel_after_finished_job(self):
		self.runner.run(lambda: 1, self.results.append)
		self.assertTrue(_wait_until(lambda: self.results))
		self.runner.wait()
		self.runner.cancel()
	def test_cancel_removes_queued_job(self):
		release = Event()
		ran = []
		self.runner.run(release.wait, self.results.append)
		other = AsyncRunner()
		other.run(lambda: ran.append('queued'), self.results.append)
		other.cancel()
		release.set()
		self.runner.wait()
		qwait(30)
		self.assertEqual([], ran)
	def test_cancel_drops_result(self):
		self.runner.run(lambda: 'x', self.results.append)
		self.runner.cancel()
		self.runner.wait()
		qwait(30)
		self.assertEqual([], self.results)

class LoadQtImageTest(TestCase):
	def test_scales_down_large_image(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'big.png')
			_write_png(path, 400, 200)
			image, original = _load_qt_image(str(path), QSize(100, 100))
		self.assertEqual(QSize(100, 50), image.size())
		self.assertEqual(QSize(400, 200), original)
	def test_does_not_scale_up_small_image(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'small.png')
			_write_png(path, 40, 20)
			image, _ = _load_qt_image(str(path), QSize(100, 100))
		self.assertEqual(QSize(40, 20), image.size())
	def test_invalid_image_raises(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'broken.png')
			path.write_bytes(b'not an image')
			with self.assertRaises(ValueError):
				_load_qt_image(str(path), QSize(100, 100))

class DirectoryInfoTest(TestCase):
	def test_counts(self):
		with TemporaryDirectory() as tmp_dir:
			Path(tmp_dir, 'a.txt').write_text('1234')
			Path(tmp_dir, 'sub').mkdir()
			info = _directory_info(tmp_dir)
		self.assertIn('1 files, 1 folders', info)
		self.assertIn('Size (files only): 4 B', info)
	def test_missing_directory_raises(self):
		with self.assertRaises(OSError):
			_directory_info('/nonexistent/vitraj-test')

class PreviewWidgetTest(TestCase):
	def setUp(self):
		self.widget = PreviewWidget()
		self.widget.resize(300, 300)
	def tearDown(self):
		self.widget._runner.wait()
		self.widget.deleteLater()
	def test_image_preview_shows_original_size(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'pic.png')
			_write_png(path, 120, 60)
			self.widget.show_preview(as_url(str(path)))
			self.assertTrue(_wait_until(self._image_shown))
		self.assertIn('120 x 60 px', self.widget._image_info.text())
	def test_loading_message_does_not_replace_result(self):
		with TemporaryDirectory() as tmp_dir:
			Path(tmp_dir, 'a.txt').write_text('x')
			self.widget.show_preview(as_url(tmp_dir))
			qwait(_LOADING_DELAY_MS + 100)
		self.assertIn('Directory', self.widget._fallback.text())
	def test_directory_preview(self):
		with TemporaryDirectory() as tmp_dir:
			Path(tmp_dir, 'a.txt').write_text('x')
			self.widget.show_preview(as_url(tmp_dir))
			self.assertTrue(_wait_until(
				lambda: 'Directory' in self.widget._fallback.text()
			))
	def test_fast_moves_render_only_last_file(self):
		with TemporaryDirectory() as tmp_dir:
			paths = [Path(tmp_dir, 'f%d.txt' % i) for i in range(3)]
			for i, path in enumerate(paths):
				path.write_text('content %d' % i)
			for path in paths:
				self.widget.show_preview(as_url(str(path)))
			self.assertEqual('content 0', self._text())
			self.assertTrue(_wait_until(lambda: self._text() == 'content 2'))
	def test_stale_result_does_not_replace_next_file(self):
		image = QImage(4, 4, QImage.Format_RGB32)
		def slow_handler(widget, path):
			def load():
				# Shorter than the debounce, so it ends before the next render:
				sleep(.03)
				return PreviewImage(image, 'info', 'STALE HEADER')
			widget.show_image_async(load)
		PreviewWidget.register_handler('.slow', slow_handler)
		self.addCleanup(PreviewWidget._preview_handlers.pop, '.slow')
		with TemporaryDirectory() as tmp_dir:
			slow = Path(tmp_dir, 'a.slow')
			slow.write_text('x')
			text = Path(tmp_dir, 'b.txt')
			text.write_text('text')
			self.widget.show_preview(as_url(str(slow)))
			self.widget.show_preview(as_url(str(text)))
			qwait(500)
		self.assertEqual('b.txt', self.widget._header.text())
		self.assertEqual('text', self._text())
	def _image_shown(self):
		return self.widget._stack.currentIndex() == 1
	def _text(self):
		return self.widget._text_view.toPlainText()

@skipIf(file_preview_pdf._load_fitz() is None, 'PyMuPDF is not installed')
class RenderPdfTest(TestCase):
	def test_missing_pymupdf_raises_in_worker(self):
		load_before = file_preview_pdf._load_fitz
		file_preview_pdf._load_fitz = lambda: None
		self.addCleanup(setattr, file_preview_pdf, '_load_fitz', load_before)
		with self.assertRaises(ImportError):
			file_preview_pdf._render_pdf('/nonexistent.pdf')
	def test_renders_first_page(self):
		fitz = file_preview_pdf._load_fitz()
		with TemporaryDirectory() as tmp_dir:
			path = join(tmp_dir, 'doc.pdf')
			doc = fitz.open()
			doc.new_page()
			doc.new_page()
			doc.save(path)
			doc.close()
			result = file_preview_pdf._render_first_page(fitz, path)
		self.assertFalse(result.image.isNull())
		self.assertEqual('doc.pdf (2 pages)', result.header)

class UpdatePreviewTest(TestCase):
	def test_reads_cursor_in_main_thread(self):
		from file_preview import _update_preview
		from threading import Thread
		calls = []
		Thread(
			target=_update_preview, args=(_SpyPane(calls),), daemon=True
		).start()
		self.assertTrue(_wait_until(lambda: calls))
		self.assertEqual([('cursor-url', True, True)], calls)
	def test_no_active_preview_does_nothing(self):
		from file_preview import _update_preview
		calls = []
		_update_preview(_SpyPane(calls, panel_id='settings'))
		self.assertEqual([], calls)
	def test_deleted_widget_is_ignored(self):
		from file_preview import _update_preview
		_update_preview(_SpyPane([], deleted=True))

class _SpyPane:
	def __init__(self, calls, panel_id='preview', deleted=False):
		from vitraj.impl.util.qt.thread import is_in_main_thread
		pane = self
		self._cursor_read_in_main = None
		class Widget:
			def show_preview(self, url):
				if deleted:
					raise RuntimeError('wrapped C/C++ object has been deleted')
				calls.append((url, is_in_main_thread(), pane._cursor_read_in_main))
		class Window:
			def get_active_panel(self, p):
				return panel_id, Widget()
		self.window = Window()
		self._is_in_main_thread = is_in_main_thread
	def get_file_under_cursor(self):
		self._cursor_read_in_main = self._is_in_main_thread()
		return 'cursor-url'

class RunnerDeletedTest(TestCase):
	def test_result_after_delete_is_dropped(self):
		import shiboken6
		release = Event()
		results = []
		runner = AsyncRunner()
		runner.run(release.wait, results.append)
		shiboken6.delete(runner)
		release.set()
		qwait(100)
		self.assertEqual([], results)
