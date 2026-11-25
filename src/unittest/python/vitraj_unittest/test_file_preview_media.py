from os.path import dirname, join
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase, skipIf
from unittest.mock import patch

import sys
import wave

_PLUGINS = join(
	dirname(__file__), '..', '..', '..', 'main', 'resources', 'base', 'Plugins'
)
for _plugin in ('File Preview', 'File Preview Media'):
	if join(_PLUGINS, _plugin) not in sys.path:
		sys.path.append(join(_PLUGINS, _plugin))

from PySide6.QtMultimedia import QMediaDevices # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel # noqa: E402
from vitraj_unittest.qt_wait import qwait # noqa: E402
from vitraj.impl.util.qt.thread import is_in_main_thread # noqa: E402
from vitraj.url import as_url # noqa: E402

from file_preview import PreviewWidget # noqa: E402
from file_preview_media import _call_media, _media_view, _show_media, \
	SEEK_STEP_MS # noqa: E402
from file_preview_media._player import MediaView, format_time # noqa: E402

_app = QApplication.instance() or QApplication([])

def _wait_until(condition, timeout_ms=3000):
	waited = 0
	while not condition() and waited < timeout_ms:
		qwait(10)
		waited += 10
	return condition()

def _write_wav(path, seconds):
	rate = 8000
	with wave.open(str(path), 'wb') as f:
		f.setnchannels(1)
		f.setsampwidth(2)
		f.setframerate(rate)
		f.writeframes(b'\0\0' * rate * seconds)

class _HideRecorder(QLabel):
	def __init__(self):
		super().__init__()
		self.hidden = 0
	def hideEvent(self, event):
		self.hidden += 1
		super().hideEvent(event)

class FormatTimeTest(TestCase):
	def test_minutes(self):
		self.assertEqual('0:07', format_time(7999))
	def test_hours(self):
		self.assertEqual('1:02:03', format_time(3723000))
	def test_negative_is_zero(self):
		self.assertEqual('0:00', format_time(-5))

class ShowWidgetTest(TestCase):
	def setUp(self):
		self.preview = PreviewWidget()
		self.preview.resize(300, 300)
		self.preview.show()
		self.custom = _HideRecorder()
		self.preview.show_widget(self.custom)
	def tearDown(self):
		self.preview._runner.wait()
		self.preview.deleteLater()
	def test_shows_widget(self):
		self.assertIs(self.custom, self.preview.custom_widget())
		self.assertIs(self.custom, self.preview._stack.currentWidget())
	def test_other_file_hides_widget_at_once(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'a.txt')
			path.write_text('x')
			self.preview.show_preview(as_url(str(path)))
		self.assertEqual(1, self.custom.hidden)
		self.assertIsNone(self.preview.custom_widget())
		self.assertEqual(-1, self.preview._stack.indexOf(self.custom))
	def test_clear_hides_widget(self):
		self.preview.clear()
		self.assertEqual(1, self.custom.hidden)
		self.assertIsNone(self.preview.custom_widget())
	def test_new_widget_replaces_old_one(self):
		other = QLabel()
		self.preview.show_widget(other)
		self.assertEqual(1, self.custom.hidden)
		self.assertIs(other, self.preview.custom_widget())

class ShowMediaTest(TestCase):
	def setUp(self):
		self.preview = PreviewWidget()
	def tearDown(self):
		self.preview.deleteLater()
	def test_media_extensions_are_registered(self):
		for ext in ('.mp4', '.webm', '.mp3', '.flac'):
			self.assertIs(_show_media, PreviewWidget._preview_handlers[ext])
	def test_missing_qt_multimedia_shows_message(self):
		with patch.dict(sys.modules, {'file_preview_media._player': None}):
			_show_media(self.preview, '/a.mp3')
		self.assertIn(
			'Media preview not available', self.preview._fallback.text()
		)
		self.assertIsNone(self.preview.custom_widget())

class MediaViewTest(TestCase):
	def setUp(self):
		self._tmp_dir = TemporaryDirectory()
		self.addCleanup(self._tmp_dir.cleanup)
		path = Path(self._tmp_dir.name, 'tone.wav')
		_write_wav(path, 3)
		self.view = MediaView(str(path))
		self.view.show()
		self.addCleanup(self.view.deleteLater)
		self.assertTrue(_wait_until(lambda: self.view._player.duration() > 0))
	def test_does_not_start_playback(self):
		qwait(100)
		self.assertFalse(self.view.is_playing())
		self.assertEqual('0:00 / 0:03', self.view._time.text())
	def test_seek_stops_at_the_limits(self):
		self.view.seek(-SEEK_STEP_MS)
		self.assertEqual(0, self.view._player.position())
		self.view.seek(SEEK_STEP_MS)
		self.assertEqual(3000, self.view._player.position())
	@skipIf(not QMediaDevices.audioOutputs(), 'No audio output device')
	def test_toggle_play_and_pause(self):
		self.view.toggle_play()
		self.assertTrue(_wait_until(self.view.is_playing))
		self.view.toggle_play()
		self.assertFalse(self.view.is_playing())
	@skipIf(not QMediaDevices.audioOutputs(), 'No audio output device')
	def test_hide_pauses(self):
		self.view.toggle_play()
		self.assertTrue(_wait_until(self.view.is_playing))
		self.view.hide()
		self.assertFalse(self.view.is_playing())
	def test_error_disables_controls(self):
		with TemporaryDirectory() as tmp_dir:
			path = Path(tmp_dir, 'broken.mp4')
			path.write_bytes(b'not a video')
			view = MediaView(str(path))
			self.addCleanup(view.deleteLater)
			self.assertTrue(_wait_until(
				lambda: not view._play_button.isEnabled()
			))
		self.assertIn('Cannot play media', view._cover.text())

class MediaCommandTest(TestCase):
	def test_calls_media_method_in_main_thread(self):
		calls = []
		class View:
			def toggle_play(self):
				calls.append(is_in_main_thread())
		pane = _PanelPane(_Preview(View()))
		Thread(
			target=_call_media, args=(pane, 'toggle_play'), daemon=True
		).start()
		self.assertTrue(_wait_until(lambda: calls))
		self.assertEqual([True], calls)
	def test_no_media_view_for_other_widget(self):
		self.assertIsNone(_media_view(_PanelPane(_Preview(QLabel()))))
	def test_no_media_view_without_preview(self):
		self.assertIsNone(_media_view(_PanelPane(None, panel_id='settings')))

class _Preview:
	def __init__(self, custom_widget):
		self._custom_widget = custom_widget
	def custom_widget(self):
		return self._custom_widget

class _PanelPane:
	def __init__(self, widget, panel_id='preview'):
		class Window:
			def get_active_panel(self, _pane):
				return panel_id, widget
		self.window = Window()
