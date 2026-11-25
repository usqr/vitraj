"""
File Preview Media - adds audio and video to the File Preview plugin.

Requires: QtMultimedia (part of PySide6)
Requires: File Preview plugin (must be loaded first)

The preview does not start playback. Use the preview_play_pause command.
"""
from vitraj import DirectoryPaneCommand
from vitraj.impl.util.qt.thread import run_in_main_thread

try:
	from file_preview import PreviewWidget, _get_preview
except ImportError:
	PreviewWidget = _get_preview = None

_VIDEO_EXTENSIONS = {
	'.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi', '.mpg', '.mpeg', '.ogv',
}
_AUDIO_EXTENSIONS = {
	'.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.oga', '.opus',
	'.aif', '.aiff',
}
SEEK_STEP_MS = 5000


def _show_media(widget, path):
	# Import late: QtMultimedia loads FFmpeg, and vitraj loads this plugin at
	# startup.
	try:
		from file_preview_media._player import MediaView
	except ImportError as e:
		widget.show_message('Media preview not available: %s' % e)
		return
	widget.show_widget(MediaView(path))


class PreviewPlayPause(DirectoryPaneCommand):

	aliases = ('Preview: play / pause',)

	def __call__(self):
		_call_media(self.pane, 'toggle_play')

	def is_visible(self):
		return _media_view(self.pane) is not None


class PreviewSeekForward(DirectoryPaneCommand):

	aliases = ('Preview: seek forward',)

	def __call__(self):
		_call_media(self.pane, 'seek', SEEK_STEP_MS)

	def is_visible(self):
		return _media_view(self.pane) is not None


class PreviewSeekBackward(DirectoryPaneCommand):

	aliases = ('Preview: seek backward',)

	def __call__(self):
		_call_media(self.pane, 'seek', -SEEK_STEP_MS)

	def is_visible(self):
		return _media_view(self.pane) is not None


def _media_view(pane):
	"""The MediaView in the preview of `pane`, or None."""
	if PreviewWidget is None:
		return None
	preview = _get_preview(pane)
	if preview is None:
		return None
	widget = preview.custom_widget()
	if not getattr(widget, 'is_media_view', False):
		return None
	return widget


@run_in_main_thread
def _call_media(pane, method_name, *args):
	# vitraj runs commands in a background thread. Widgets need the main one.
	view = _media_view(pane)
	if view is None:
		return
	try:
		getattr(view, method_name)(*args)
	except RuntimeError:
		# Qt deleted the widget in the meantime (the file or panel changed).
		pass


if PreviewWidget is not None:
	for _ext in _VIDEO_EXTENSIONS | _AUDIO_EXTENSIONS:
		PreviewWidget.register_handler(_ext, _show_media)
