from os.path import dirname, join
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase, skipIf
from unittest.mock import patch

import shutil
import subprocess
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
	PreviewPlayPause, PreviewSeekBackward, PreviewSeekForward, \
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

def _ffmpeg(*args):
	subprocess.run(
		['ffmpeg', '-loglevel', 'error', '-y'] + list(args), check=True
	)

_NO_FFMPEG = shutil.which('ffmpeg') is None

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
	def test_same_widget_again_keeps_it(self):
		self.preview.show_widget(self.custom)
		self.assertEqual(0, self.custom.hidden)
		self.assertIs(self.custom, self.preview._stack.currentWidget())
	def test_show_message(self):
		self.preview.show_message('Hello')
		self.assertEqual('Hello', self.preview._fallback.text())
		self.assertIs(self.preview._fallback, self.preview._stack.currentWidget())

class HandlerWidgetTest(TestCase):
	def setUp(self):
		self.preview = PreviewWidget()
		self.preview.show()
		self.shown = []
		def handler(widget, path):
			label = _HideRecorder()
			self.shown.append(label)
			widget.show_widget(label)
		PreviewWidget.register_handler('.custom', handler)
		self.addCleanup(PreviewWidget._preview_handlers.pop, '.custom')
	def tearDown(self):
		self.preview._runner.wait()
		self.preview.deleteLater()
	def test_handler_widget_goes_on_next_file(self):
		with TemporaryDirectory() as tmp_dir:
			custom = Path(tmp_dir, 'a.custom')
			custom.write_text('x')
			text = Path(tmp_dir, 'b.txt')
			text.write_text('text')
			self.preview.show_preview(as_url(str(custom)))
			self.assertTrue(_wait_until(lambda: self.shown))
			self.assertIs(self.shown[0], self.preview.custom_widget())
			self.preview.show_preview(as_url(str(text)))
			self.assertEqual(1, self.shown[0].hidden)
			self.assertTrue(_wait_until(
				lambda: self.preview._text_view.toPlainText() == 'text'
			))
		self.assertIsNone(self.preview.custom_widget())

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
	def test_audio_without_tags_shows_note(self):
		self.assertTrue(_wait_until(lambda: self.view._cover.text() == '♪'))
		self.assertEqual('', self.view._info.text())
		self.assertFalse(self.view._video.isVisible())
	def test_slider_click_seeks(self):
		# A click on the track sets the value without sliderMoved:
		self.view._slider.setValue(1500)
		self.assertEqual(1500, self.view._player.position())
	def test_position_moves_slider_without_seek(self):
		self.view._on_position(1000)
		self.assertEqual(1000, self.view._slider.value())
		self.assertEqual(0, self.view._player.position())
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
		view._on_metadata()
		self.assertIn('Cannot play media', view._cover.text())

@skipIf(_NO_FFMPEG, 'ffmpeg is not installed')
class MediaViewFfmpegTest(TestCase):
	def setUp(self):
		self._tmp_dir = TemporaryDirectory()
		self.addCleanup(self._tmp_dir.cleanup)
	def test_video_shows_resolution_and_video(self):
		path = self._path('clip.mp4')
		_ffmpeg(
			'-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=10',
			'-pix_fmt', 'yuv420p', '-metadata', 'title=Clip', path
		)
		view = self._view(path)
		self.assertTrue(_wait_until(lambda: view._info.text() == '320 x 240'))
		self.assertTrue(view._video.isVisible())
		self.assertFalse(view._cover.isVisible())
	def test_audio_shows_title_and_artist(self):
		path = self._path('tone.mp3')
		_ffmpeg(
			'-f', 'lavfi', '-i', 'sine=duration=1', '-metadata', 'title=Tone',
			'-metadata', 'artist=Band', path
		)
		view = self._view(path)
		self.assertTrue(_wait_until(lambda: view._info.text() == 'Tone – Band'))
		self.assertEqual('♪', view._cover.text())
	def test_audio_shows_cover_art(self):
		path = self._path('cover.mp3')
		_ffmpeg(
			'-f', 'lavfi', '-i', 'sine=duration=1', '-f', 'lavfi', '-i',
			'testsrc=size=64x64', '-frames:v', '1', '-map', '0:a', '-map',
			'1:v', '-c:v', 'mjpeg', '-disposition:v', 'attached_pic', path
		)
		view = self._view(path)
		self.assertTrue(_wait_until(lambda: view._cover.pixmap() is not None
			and not view._cover.pixmap().isNull()))
		self.assertFalse(view._video.isVisible())
	def _path(self, name):
		return str(Path(self._tmp_dir.name, name))
	def _view(self, path):
		view = MediaView(path)
		view.show()
		self.addCleanup(view.deleteLater)
		return view

class MediaCommandTest(TestCase):
	def test_calls_media_method_in_main_thread(self):
		calls = []
		class View:
			is_media_view = True
			def toggle_play(self):
				calls.append(is_in_main_thread())
		pane = _PanelPane(_Preview(View()))
		Thread(
			target=_call_media, args=(pane, 'toggle_play'), daemon=True
		).start()
		self.assertTrue(_wait_until(lambda: calls))
		self.assertEqual([True], calls)
	def test_seek_commands_call_seek(self):
		calls = []
		class View:
			is_media_view = True
			def seek(self, delta_ms):
				calls.append(delta_ms)
		pane = _PanelPane(_Preview(View()))
		PreviewSeekForward(pane)()
		PreviewSeekBackward(pane)()
		self.assertTrue(_wait_until(lambda: len(calls) == 2))
		self.assertEqual([SEEK_STEP_MS, -SEEK_STEP_MS], calls)
	def test_commands_are_visible_only_for_media(self):
		class View:
			is_media_view = True
		media = _PanelPane(_Preview(View()))
		other = _PanelPane(_Preview(QLabel()))
		for command in (PreviewPlayPause, PreviewSeekForward, PreviewSeekBackward):
			self.assertTrue(command(media).is_visible())
			self.assertFalse(command(other).is_visible())
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
