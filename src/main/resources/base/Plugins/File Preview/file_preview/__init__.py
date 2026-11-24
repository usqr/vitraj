from vitraj import DirectoryPaneCommand, DirectoryPaneListener
from vitraj.impl.util.qt.thread import run_in_main_thread
from vitraj.url import splitscheme, basename, as_human_readable
from collections import namedtuple
from file_preview._async import AsyncRunner, Debouncer
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QFont, QImage, QImageReader
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit, \
	QStackedWidget, QScrollArea, QSizePolicy, QApplication

from functools import lru_cache

import os


@lru_cache(maxsize=1)
def _pil_image():
	"""
	Return PIL.Image, or None if Pillow is not installed. Import late:
	Pillow takes ~150 ms to import and only the AVIF preview needs it.
	"""
	try:
		from PIL import Image
	except ImportError:
		return None
	return Image

_TEXT_EXTENSIONS = {
	'.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.xml', '.html',
	'.htm', '.css', '.scss', '.less', '.md', '.markdown', '.yaml', '.yml',
	'.toml', '.cfg', '.ini', '.sh', '.bash', '.zsh', '.bat', '.cmd',
	'.ps1', '.log', '.csv', '.tsv', '.rst', '.java', '.c', '.h', '.cpp',
	'.hpp', '.cs', '.rs', '.go', '.rb', '.php', '.pl', '.lua', '.sql',
	'.r', '.m', '.swift', '.kt', '.scala', '.hs', '.ex', '.exs', '.erl',
	'.clj', '.lisp', '.vim', '.el', '.cmake', '.mk',
	'.gitignore', '.gitattributes', '.editorconfig',
	'.env', '.conf', '.properties', '.gradle', '.pom', '.sbt',
	'.cabal', '.lock', '.patch', '.diff',
}

_IMAGE_EXTENSIONS = {
	'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.ico', '.webp',
	'.tif', '.tiff',
}

_MAX_TEXT_SIZE = 1024 * 1024
_SNIFF_SIZE = 8192
_MAX_DIR_ENTRIES = 10000
# Render the first cursor move at once. Then wait for a pause this long:
_DEBOUNCE_MS = 80
# Show "Loading..." only when a preview takes longer than this:
_LOADING_DELAY_MS = 150

PreviewImage = namedtuple('PreviewImage', ('image', 'info', 'header'))
PreviewImage.__new__.__defaults__ = (None,)
PreviewImage.__doc__ = """
The result of a load function for PreviewWidget#show_image_async(...).
`image` is a QImage (not a QPixmap: QPixmap is not safe outside the main
thread). `header`, when not None, replaces the text of the header.
"""

def _format_size(size):
	if size < 1024:
		return '{:,} B'.format(size)
	elif size < 1024 * 1024:
		return '{:,.1f} KB'.format(size / 1024)
	elif size < 1024 * 1024 * 1024:
		return '{:,.1f} MB'.format(size / (1024 * 1024))
	else:
		return '{:,.1f} GB'.format(size / (1024 * 1024 * 1024))

def _looks_binary(sample):
	return b'\x00' in sample

def _load_qt_image(path, max_size):
	"""
	Decode the image at `path`, scaled down to fit in `max_size`. Return
	(QImage, original QSize). Safe to call outside the main thread.
	"""
	reader = QImageReader(path)
	original = reader.size()
	if original.isValid() and (
		original.width() > max_size.width() or
		original.height() > max_size.height()
	):
		reader.setScaledSize(original.scaled(max_size, Qt.KeepAspectRatio))
	image = reader.read()
	if image.isNull():
		raise ValueError(reader.errorString())
	if not original.isValid():
		original = image.size()
	return image, original

def _load_image(path, ext, max_size):
	image, original = _load_qt_image(path, max_size)
	w, h = original.width(), original.height()
	if ext == '.svg':
		return PreviewImage(image, 'SVG canvas: %d x %d' % (w, h))
	size = _file_size(path)
	return PreviewImage(image, '%d x %d px  |  %s' % (w, h, _format_size(size)))

def _load_pillow_image(path, max_size):
	pil_image = _pil_image()
	if pil_image is None:
		raise ImportError('AVIF preview requires Pillow (pip install Pillow)')
	with pil_image.open(path) as img:
		w, h = img.width, img.height
		img.thumbnail((max_size.width(), max_size.height()))
		rgba = img.convert('RGBA')
		data = rgba.tobytes('raw', 'RGBA')
		image = QImage(
			data, rgba.width, rgba.height, QImage.Format_RGBA8888
		).copy()
	info = '%d x %d px  |  %s' % (w, h, _format_size(_file_size(path)))
	return PreviewImage(image, info)

def _file_size(path):
	try:
		return os.path.getsize(path)
	except OSError:
		return 0

def _directory_info(path):
	"""Return a summary of the directory at `path`. Raise OSError on error."""
	num_files = num_dirs = total_size = 0
	truncated = False
	with os.scandir(path) as it:
		for i, entry in enumerate(it):
			if i >= _MAX_DIR_ENTRIES:
				truncated = True
				break
			try:
				if entry.is_dir(follow_symlinks=False):
					num_dirs += 1
				else:
					num_files += 1
					total_size += entry.stat().st_size
			except OSError:
				num_files += 1
	count_str = '{:,} files, {:,} folders'.format(num_files, num_dirs)
	if truncated:
		count_str += ' (first {:,} entries)'.format(_MAX_DIR_ENTRIES)
	lines = ['Directory\n', count_str]
	if total_size > 0:
		lines.append('Size (files only): %s' % _format_size(total_size))
	return '\n'.join(lines)

def _max_image_size(widget):
	"""The largest size that is useful for a preview: the screen size."""
	screen = widget.screen() or QApplication.primaryScreen()
	return screen.size() * screen.devicePixelRatio()


class PreviewWidget(QWidget):

	_preview_handlers = {}

	@classmethod
	def register_handler(cls, ext, handler):
		cls._preview_handlers[ext] = handler

	def __init__(self, parent=None):
		super().__init__(parent)
		self._current_pixmap = None
		self._last_url = None
		self._runner = AsyncRunner(self)
		self._render_debounced = Debouncer(self._render, _DEBOUNCE_MS, self)
		# A child of this widget, so it stops when the widget is deleted:
		self._loading_timer = QTimer(self)
		self._loading_timer.setSingleShot(True)
		self._loading_timer.setInterval(_LOADING_DELAY_MS)
		self._loading_timer.timeout.connect(
			lambda: self._show_message('Loading...')
		)
		self._init_ui()

	def _init_ui(self):
		self.setMinimumWidth(0)
		self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self._header = QLabel()
		self._header.setObjectName('preview-header')
		self._header.setWordWrap(True)
		self._header.setStyleSheet(
			'QLabel { padding: 4px 8px; font-weight: bold; }'
		)
		layout.addWidget(self._header)

		self._stack = QStackedWidget()

		self._text_view = QPlainTextEdit()
		self._text_view.setReadOnly(True)
		self._text_view.setLineWrapMode(QPlainTextEdit.NoWrap)
		font = QFont()
		font.setStyleHint(QFont.Monospace)
		font.setFamily(font.defaultFamily())
		font.setPointSize(12)
		self._text_view.setFont(font)
		self._stack.addWidget(self._text_view)

		image_page = QWidget()
		image_layout = QVBoxLayout()
		image_layout.setContentsMargins(0, 0, 0, 0)
		image_layout.setSpacing(0)
		self._image_info = QLabel()
		self._image_info.setStyleSheet(
			'QLabel { padding: 2px 8px; font-size: 11px; }'
		)
		image_layout.addWidget(self._image_info)
		self._image_scroll = QScrollArea()
		self._image_scroll.setWidgetResizable(True)
		self._image_scroll.setAlignment(Qt.AlignCenter)
		self._image_label = QLabel()
		self._image_label.setAlignment(Qt.AlignCenter)
		self._image_label.setSizePolicy(
			QSizePolicy.Ignored, QSizePolicy.Ignored
		)
		self._image_scroll.setWidget(self._image_label)
		image_layout.addWidget(self._image_scroll)
		image_page.setLayout(image_layout)
		self._stack.addWidget(image_page)

		self._fallback = QLabel()
		self._fallback.setAlignment(Qt.AlignCenter)
		self._fallback.setWordWrap(True)
		self._fallback.setStyleSheet('QLabel { padding: 20px; }')
		self._stack.addWidget(self._fallback)

		layout.addWidget(self._stack)
		self.setLayout(layout)

	def show_preview(self, file_url):
		if file_url == self._last_url:
			return
		self._last_url = file_url
		# Drop the result of the previous file at once. Else it could show
		# (with its header) under the new file until the debounced render:
		self._runner.cancel()
		self._loading_timer.stop()
		if file_url is not None:
			self._header.setText(basename(file_url))
		self._render_debounced(file_url)

	def show_image_pixmap(self, pixmap, info_text):
		"""Public API for handler plugins to display a pixmap with info."""
		self._current_pixmap = pixmap
		self._image_info.setText(info_text)
		self._scale_image()
		self._stack.setCurrentIndex(1)

	def show_image_async(self, load_fn, error_prefix='Cannot load image'):
		"""
		Public API for handler plugins. Call load_fn() in a worker thread. It
		must return a PreviewImage and must not touch any widget. Then show
		the image, unless the user moved to another file in the meantime.
		"""
		def on_result(result):
			if isinstance(result, Exception):
				self._show_message('%s: %s' % (error_prefix, result))
				return
			if result.header is not None:
				self._header.setText(result.header)
			self.show_image_pixmap(QPixmap.fromImage(result.image), result.info)
		self._run_async(load_fn, on_result)

	def clear(self):
		self._render_debounced.cancel()
		self._runner.cancel()
		self._loading_timer.stop()
		self._header.setText('')
		self._text_view.clear()
		self._image_label.clear()
		self._image_info.setText('')
		self._current_pixmap = None
		self._last_url = None
		self._fallback.setText('')
		self._stack.setCurrentIndex(2)

	def resizeEvent(self, event):
		super().resizeEvent(event)
		if self._current_pixmap and self._stack.currentIndex() == 1:
			self._scale_image()

	def _render(self, file_url):
		self._runner.cancel()
		self._loading_timer.stop()
		if file_url is None:
			self._show_message('No file selected')
			return
		# A handler (for example PDF) can change the header. Reset it:
		self._header.setText(basename(file_url))
		scheme, _ = splitscheme(file_url)
		if scheme != 'file://':
			self._show_message('Preview not available for %s' % scheme)
			return
		path = as_human_readable(file_url)
		if os.path.isdir(path):
			self._show_directory_info(path)
			return
		ext = os.path.splitext(path)[1].lower()
		handler = self._preview_handlers.get(ext)
		if handler:
			handler(self, path)
		elif ext in _IMAGE_EXTENSIONS:
			self._show_image(path, ext)
		elif ext == '.avif':
			self._show_pillow_image(path)
		elif ext in _TEXT_EXTENSIONS:
			self._show_text(path)
		else:
			self._show_by_sniffing(path)

	def _run_async(self, fn, on_result):
		def on_result_wrapper(result):
			self._loading_timer.stop()
			on_result(result)
		self._runner.run(fn, on_result_wrapper)
		self._loading_timer.start()

	def _show_text(self, path):
		try:
			size = os.path.getsize(path)
			with open(path, 'r', encoding='utf-8', errors='replace') as f:
				content = f.read(_MAX_TEXT_SIZE)
			if size > _MAX_TEXT_SIZE:
				content += '\n\n[... truncated at 1 MB ...]'
			self._text_view.setPlainText(content)
			self._stack.setCurrentIndex(0)
		except (OSError, UnicodeDecodeError) as e:
			self._show_message('Cannot read file: %s' % e)

	def _show_pillow_image(self, path):
		max_size = _max_image_size(self)
		# The worker imports Pillow (~150 ms) at the first use:
		self.show_image_async(lambda: _load_pillow_image(path, max_size))

	def _show_image(self, path, ext=None):
		max_size = _max_image_size(self)
		self.show_image_async(lambda: _load_image(path, ext, max_size))

	def _scale_image(self):
		if not self._current_pixmap:
			return
		available = self._image_scroll.size()
		scaled = self._current_pixmap.scaled(
			available, Qt.KeepAspectRatio, Qt.SmoothTransformation
		)
		self._image_label.setPixmap(scaled)

	def _show_by_sniffing(self, path):
		try:
			with open(path, 'rb') as f:
				sample = f.read(_SNIFF_SIZE)
				try:
					file_size = os.fstat(f.fileno()).st_size
				except OSError:
					file_size = 0
		except OSError as e:
			self._show_message('Cannot read file: %s' % e)
			return
		if not sample:
			self._show_text(path)
			return
		if _looks_binary(sample):
			self._show_message(
				'Binary file\n\n%s\n%s' % (
					os.path.basename(path), _format_size(file_size)
				)
			)
			return
		try:
			sample.decode('utf-8')
			self._show_text(path)
		except UnicodeDecodeError:
			self._show_message(
				'Binary file\n\n%s\n%s' % (
					os.path.basename(path), _format_size(file_size)
				)
			)

	def _show_directory_info(self, path):
		def on_result(result):
			if isinstance(result, Exception):
				self._show_message('Cannot read directory: %s' % result)
			else:
				self._show_message(result)
		self._run_async(lambda: _directory_info(path), on_result)

	def _show_message(self, text):
		self._current_pixmap = None
		self._fallback.setText(text)
		self._stack.setCurrentIndex(2)


_PANEL_ID = 'preview'
# Per-pane cursor tracking state (kept separately from PanelManager)
_cursor_connections = {}


class TogglePreview(DirectoryPaneCommand):

	aliases = ('Toggle preview', 'Preview file', 'View file')

	def __call__(self):
		w = self.pane.window
		if w.is_panel_active(self.pane, _PANEL_ID):
			_close_preview(self.pane)
		else:
			_open_preview(self.pane)

	def is_visible(self):
		return len(self.pane.window.get_panes()) >= 2


class ExitPreview(DirectoryPaneCommand):

	aliases = ('Exit preview', 'Close preview')

	def __call__(self):
		_close_preview(self.pane)

	def is_visible(self):
		return self.pane.window.is_panel_active(self.pane, _PANEL_ID)


class PreviewModeListener(DirectoryPaneListener):
	def on_path_changed(self):
		# vitraj calls listeners in a background thread. The preview uses
		# widgets and QTimers, so it must run in the main thread:
		_update_preview(self.pane)


@run_in_main_thread
def _update_preview(pane):
	# Read the panel and the cursor in this same main-thread task. Else a
	# cursor move between two tasks could show a stale file.
	active = pane.window.get_active_panel(pane)
	if not active or active[0] != _PANEL_ID:
		return
	try:
		active[1].show_preview(pane.get_file_under_cursor())
	except RuntimeError:
		# Qt deleted the widget in the meantime (the panel was closed).
		pass


def _open_preview(pane):
	file_view = pane._widget._file_view
	file_url = pane.get_file_under_cursor()

	def factory():
		preview = PreviewWidget()

		def on_cursor_changed(current, _previous):
			try:
				url = file_view.model().url(current)
			except (ValueError, RuntimeError):
				url = None
			try:
				preview.show_preview(url)
			except RuntimeError:
				# The preview widget's C++ object was already deleted (the panel
				# was deactivated). Stop tracking so we don't fire again.
				_disconnect_cursor_tracking(pane)

		# Connect signal on the main thread (inside factory)
		file_view.selectionModel().currentRowChanged.connect(on_cursor_changed)
		_cursor_connections[pane] = {
			'callback': on_cursor_changed,
			'file_view': file_view,
		}
		# The panel can be closed without going through _close_preview() — e.g.
		# PanelModeListener (Core) deactivates the panel directly on go_to /
		# switch_panes. Disconnect cursor tracking when the widget is destroyed
		# so a later currentRowChanged doesn't fire on a deleted widget.
		preview.destroyed.connect(lambda *_: _disconnect_cursor_tracking(pane))
		preview.show_preview(file_url)
		return preview

	pane.window.activate_panel(pane, factory, _PANEL_ID)


def _disconnect_cursor_tracking(pane):
	conn = _cursor_connections.pop(pane, None)
	if conn:
		try:
			conn['file_view'].selectionModel().currentRowChanged.disconnect(
				conn['callback']
			)
		except (TypeError, RuntimeError):
			pass


def _close_preview(pane):
	# Disconnect cursor tracking before panel is destroyed
	_disconnect_cursor_tracking(pane)
	pane.window.deactivate_panel(pane)
