from vitraj import DirectoryPaneCommand, DirectoryPaneListener
from vitraj.impl.util.qt.thread import run_in_main_thread
from vitraj.url import splitscheme, basename, as_human_readable
from collections import namedtuple
from file_preview._async import AsyncRunner, Debouncer
from file_preview._view import ImageCanvas, PageView, clamp_zoom, fit_zoom, \
	step_zoom
from PySide6.QtCore import QEvent, QPointF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QPixmap, QFont, QImage, QImageReader
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, \
	QPlainTextEdit, QStackedWidget, QScrollArea, QSizePolicy, QApplication, \
	QToolButton

from math import ceil

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

PreviewImage = namedtuple('PreviewImage', ('image', 'info', 'header', 'size'))
PreviewImage.__new__.__defaults__ = (None, None)
PreviewImage.__doc__ = """
The result of a load function for PreviewWidget#show_image_async(...).
`image` is a QImage (not a QPixmap: QPixmap is not safe outside the main
thread). `header`, when not None, replaces the text of the header. `size`,
when not None, is the QSize of the original image in pixels: the size at a
zoom of 100%. A loader can give a smaller `image` than this size.
"""

PreviewPage = namedtuple(
	'PreviewPage', ('image', 'info', 'header', 'page_count', 'size')
)
PreviewPage.__doc__ = """
The result of a render function for PreviewWidget#show_pages_async(...).
`image` is a QImage of the page. `size` is the QSizeF of the page at a zoom
of 100%, in logical pixels (for a PDF: in points). `header`, when not None,
replaces the text of the header.
"""

# Render a page again when the view needs more than this factor of the
# width of its image (else it is not sharp)...
_RERENDER_ABOVE = 1.05
# ... or less than this factor (else it uses memory for nothing):
_RERENDER_BELOW = .5
_WHEEL_ZOOM_PER_NOTCH = 1.25

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
		return PreviewImage(image, 'SVG canvas: %d x %d' % (w, h), None, original)
	info = '%d x %d px  |  %s' % (w, h, _format_size(_file_size(path)))
	return PreviewImage(image, info, None, original)

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
	return PreviewImage(image, info, None, QSize(w, h))

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
		self._last_url = None
		self._runner = AsyncRunner(self)
		self._render_debounced = Debouncer(self._render, _DEBOUNCE_MS, self)
		self._request_page_debounced = Debouncer(
			lambda _: self._request_page(), _DEBOUNCE_MS, self
		)
		# The size of the shown image at a zoom of 100%, in logical pixels:
		self._natural = QSizeF()
		self._zoom = None # None means "fit"
		self._render_page = None
		self._page_index = 0
		self._page_count = 0
		self._displayed_page = None
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

		self._stack.addWidget(self._create_image_page())

		self._fallback = QLabel()
		self._fallback.setAlignment(Qt.AlignCenter)
		self._fallback.setWordWrap(True)
		self._fallback.setStyleSheet('QLabel { padding: 20px; }')
		self._stack.addWidget(self._fallback)

		layout.addWidget(self._stack)
		self.setLayout(layout)

	def _create_image_page(self):
		page = QWidget()
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)
		layout.addWidget(self._create_toolbar())
		self._image_scroll = QScrollArea()
		self._image_scroll.setAlignment(Qt.AlignCenter)
		self._canvas = ImageCanvas()
		self._image_scroll.setWidget(self._canvas)
		# Resize, Cmd/Ctrl + wheel, and pinch go to #eventFilter(...):
		self._image_scroll.viewport().installEventFilter(self)
		layout.addWidget(self._image_scroll)
		page.setLayout(layout)
		return page

	def _create_toolbar(self):
		toolbar = QWidget()
		toolbar.setStyleSheet(
			'QLabel, QToolButton { font-size: 11px; } '
			'QLabel { padding: 2px 4px; }'
		)
		layout = QHBoxLayout()
		layout.setContentsMargins(4, 0, 4, 0)
		layout.setSpacing(0)
		self._previous_page_button = self._tool_button(
			'◀', 'Previous page', self.previous_page
		)
		self._page_label = QLabel()
		self._next_page_button = self._tool_button(
			'▶', 'Next page', self.next_page
		)
		self._image_info = QLabel()
		# Let a long text get cut in a narrow panel:
		self._image_info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
		self._zoom_label = QLabel()
		widgets = (
			self._previous_page_button, self._page_label,
			self._next_page_button, self._image_info,
			self._tool_button('−', 'Zoom out', self.zoom_out),
			self._zoom_label,
			self._tool_button('+', 'Zoom in', self.zoom_in),
			self._tool_button('Fit', 'Zoom to fit', self.zoom_fit),
			self._tool_button('1:1', 'Actual size', self.zoom_actual),
		)
		for widget in widgets:
			layout.addWidget(widget, 1 if widget is self._image_info else 0)
		toolbar.setLayout(layout)
		self._update_page_controls()
		return toolbar

	def _tool_button(self, text, tooltip, on_click):
		button = QToolButton()
		button.setText(text)
		button.setToolTip(tooltip)
		button.setAutoRaise(True)
		# Keep the keyboard focus in the file pane:
		button.setFocusPolicy(Qt.NoFocus)
		button.clicked.connect(on_click)
		return button

	def show_preview(self, file_url):
		if file_url == self._last_url:
			return
		self._last_url = file_url
		# Drop the result of the previous file at once. Else it could show
		# (with its header) under the new file until the debounced render:
		self._runner.cancel()
		self._request_page_debounced.cancel()
		# A zoom, a resize, or a page key before the debounced render must
		# not render a page of the previous file:
		self._render_page = None
		self._loading_timer.stop()
		if file_url is not None:
			self._header.setText(basename(file_url))
		self._render_debounced(file_url)

	def show_image_pixmap(self, pixmap, info_text, size=None):
		"""
		Public API for handler plugins to display a pixmap with info. `size`
		is the QSize in pixels at a zoom of 100%. The default is the size of
		`pixmap`.
		"""
		if size is None:
			size = pixmap.size()
		dpr = self.devicePixelRatioF()
		natural = QSizeF(size.width() / dpr, size.height() / dpr)
		self._show_pixmap(pixmap, info_text, natural)

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
			pixmap = QPixmap.fromImage(result.image)
			self.show_image_pixmap(pixmap, result.info, result.size)
		self._run_async(load_fn, on_result)

	def show_pages_async(self, render_fn, error_prefix='Cannot load document'):
		"""
		Public API for handler plugins, for a document with pages. Call
		render_fn(page_index, page_view) in a worker thread. It must return a
		PreviewPage and must not touch any widget. `page_view` is a PageView:
		use page_view.render_scale(size) to get the scale of the image. The
		widget calls render_fn again when the user goes to another page or
		changes the zoom.
		"""
		self._render_page = render_fn
		self._page_error = error_prefix
		self._request_page(first=True)

	def next_page(self):
		self.go_to_page(self._page_index + 1)

	def previous_page(self):
		self.go_to_page(self._page_index - 1)

	def go_to_page(self, index):
		if self._page_count < 2:
			return
		index = min(max(index, 0), self._page_count - 1)
		if index == self._page_index:
			return
		self._page_index = index
		self._update_page_controls()
		self._request_page_debounced(None)

	def page_count(self):
		"""The number of pages. 0 if the preview does not show a document."""
		return self._page_count

	def zoom_in(self):
		self._set_zoom(step_zoom(self._effective_zoom(), 1))

	def zoom_out(self):
		self._set_zoom(step_zoom(self._effective_zoom(), -1))

	def zoom_fit(self):
		self._set_zoom(None)

	def zoom_actual(self):
		self._set_zoom(1.0)

	def clear(self):
		self._render_debounced.cancel()
		self._runner.cancel()
		self._loading_timer.stop()
		self._reset_view()
		self._header.setText('')
		self._text_view.clear()
		self._canvas.set_pixmap(None)
		self._image_info.setText('')
		self._last_url = None
		self._fallback.setText('')
		self._stack.setCurrentIndex(2)

	def eventFilter(self, watched, event):
		if watched is not self._image_scroll.viewport():
			return False
		event_type = event.type()
		if event_type == QEvent.Resize:
			self._update_canvas()
			self._rerender_if_necessary()
		elif event_type == QEvent.Wheel:
			return self._on_wheel(event)
		elif event_type == QEvent.NativeGesture:
			return self._on_native_gesture(event)
		return False

	def _on_wheel(self, event):
		if not event.modifiers() & Qt.ControlModifier:
			return False
		notches = event.angleDelta().y() / 120
		factor = _WHEEL_ZOOM_PER_NOTCH ** notches
		self._set_zoom(self._effective_zoom() * factor, event.position())
		return True

	def _on_native_gesture(self, event):
		if event.gestureType() != Qt.ZoomNativeGesture:
			return False
		factor = 1 + event.value()
		self._set_zoom(self._effective_zoom() * factor, event.position())
		return True

	def _set_zoom(self, zoom, anchor=None):
		"""
		Set the zoom (None means "fit"). Keep the image point under `anchor`
		(a QPointF in the viewport) at the same position.
		"""
		if self._stack.currentIndex() != 1 or self._canvas.pixmap() is None:
			return
		if zoom is not None:
			zoom = clamp_zoom(zoom, self._effective_zoom())
		viewport = self._image_scroll.viewport()
		if anchor is None:
			anchor = QPointF(viewport.width() / 2, viewport.height() / 2)
		point = self._image_point_at(anchor)
		self._zoom = zoom
		self._update_canvas()
		self._scroll_image_point_to(point, anchor)
		self._rerender_if_necessary()

	def _effective_zoom(self):
		if self._zoom is not None:
			return self._zoom
		return fit_zoom(self._natural, self._image_scroll.maximumViewportSize())

	def _image_offset(self):
		"""The position of the image in the canvas."""
		zoom = self._effective_zoom()
		return QPointF(
			(self._canvas.width() - self._natural.width() * zoom) / 2,
			(self._canvas.height() - self._natural.height() * zoom) / 2
		)

	def _image_point_at(self, anchor):
		"""The point of the image (at a zoom of 100%) under `anchor`."""
		scroll = QPointF(
			self._image_scroll.horizontalScrollBar().value(),
			self._image_scroll.verticalScrollBar().value()
		)
		return (scroll + anchor - self._image_offset()) / self._effective_zoom()

	def _scroll_image_point_to(self, point, anchor):
		scroll = point * self._effective_zoom() + self._image_offset() - anchor
		self._image_scroll.horizontalScrollBar().setValue(round(scroll.x()))
		self._image_scroll.verticalScrollBar().setValue(round(scroll.y()))

	def _update_canvas(self):
		"""Give the canvas the size for the zoom."""
		zoom = self._effective_zoom()
		size = self._natural * zoom
		self._canvas.set_display_size(size)
		self._zoom_label.setText('%d%%' % round(zoom * 100))
		if self._zoom is None:
			# No scroll bars:
			self._canvas.resize(self._image_scroll.maximumViewportSize())
			return
		viewport = self._image_scroll.viewport().size()
		self._canvas.resize(
			max(ceil(size.width()), viewport.width()),
			max(ceil(size.height()), viewport.height())
		)

	def _show_pixmap(self, pixmap, info_text, natural):
		self._canvas.set_pixmap(pixmap)
		self._natural = natural
		self._image_info.setText(info_text)
		self._stack.setCurrentIndex(1)
		self._update_canvas()

	def _reset_view(self):
		"""Forget the zoom and the pages of the last file."""
		self._request_page_debounced.cancel()
		self._zoom = None
		self._render_page = None
		self._page_index = 0
		self._page_count = 0
		self._displayed_page = None
		self._update_page_controls()

	def _update_page_controls(self):
		has_pages = self._page_count > 1
		for widget in (
			self._previous_page_button, self._page_label,
			self._next_page_button
		):
			widget.setVisible(has_pages)
		if not has_pages:
			return
		index = self._page_index
		self._page_label.setText('%d / %d' % (index + 1, self._page_count))
		self._previous_page_button.setEnabled(index > 0)
		self._next_page_button.setEnabled(index < self._page_count - 1)

	def _page_view(self):
		return PageView(
			self._zoom, self._image_scroll.maximumViewportSize(),
			self.devicePixelRatioF()
		)

	def _request_page(self, first=False):
		render, index, view = self._render_page, self._page_index, \
			self._page_view()
		if render is None:
			return
		def load():
			return render(index, view)
		def on_result(result):
			self._on_page(result, index)
		if first:
			self._run_async(load, on_result)
		else:
			# Show the last image (not "Loading...") until the new one comes:
			self._runner.run(load, on_result)

	def _on_page(self, result, index):
		if isinstance(result, Exception):
			self._show_message('%s: %s' % (self._page_error, result))
			return
		if result.header is not None:
			self._header.setText(result.header)
		self._page_count = result.page_count
		self._update_page_controls()
		new_page = index != self._displayed_page
		self._displayed_page = index
		self._show_pixmap(QPixmap.fromImage(result.image), result.info, result.size)
		if new_page:
			self._image_scroll.verticalScrollBar().setValue(0)

	def _rerender_if_necessary(self):
		"""Render the page again if its image is too small or too large."""
		pixmap = self._canvas.pixmap()
		if self._displayed_page is None or pixmap is None:
			return
		scale = self._page_view().render_scale(self._natural)
		ratio = self._natural.width() * scale / max(pixmap.width(), 1)
		if _RERENDER_BELOW <= ratio <= _RERENDER_ABOVE:
			return
		self._request_page_debounced(None)

	def _render(self, file_url):
		self._runner.cancel()
		self._loading_timer.stop()
		self._reset_view()
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
		self._canvas.set_pixmap(None)
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


class PreviewNextPage(DirectoryPaneCommand):

	aliases = ('Preview: next page',)

	def __call__(self):
		_call_preview(self.pane, 'next_page')

	def is_visible(self):
		return _preview_page_count(self.pane) > 1


class PreviewPreviousPage(DirectoryPaneCommand):

	aliases = ('Preview: previous page',)

	def __call__(self):
		_call_preview(self.pane, 'previous_page')

	def is_visible(self):
		return _preview_page_count(self.pane) > 1


class PreviewZoomIn(DirectoryPaneCommand):

	aliases = ('Preview: zoom in',)

	def __call__(self):
		_call_preview(self.pane, 'zoom_in')

	def is_visible(self):
		return _get_preview(self.pane) is not None


class PreviewZoomOut(DirectoryPaneCommand):

	aliases = ('Preview: zoom out',)

	def __call__(self):
		_call_preview(self.pane, 'zoom_out')

	def is_visible(self):
		return _get_preview(self.pane) is not None


class PreviewZoomFit(DirectoryPaneCommand):

	aliases = ('Preview: zoom to fit',)

	def __call__(self):
		_call_preview(self.pane, 'zoom_fit')

	def is_visible(self):
		return _get_preview(self.pane) is not None


class PreviewZoomActual(DirectoryPaneCommand):

	aliases = ('Preview: actual size',)

	def __call__(self):
		_call_preview(self.pane, 'zoom_actual')

	def is_visible(self):
		return _get_preview(self.pane) is not None


def _get_preview(pane):
	"""The PreviewWidget of `pane`, or None if the preview is not open."""
	active = pane.window.get_active_panel(pane)
	if not active or active[0] != _PANEL_ID:
		return None
	return active[1]


def _preview_page_count(pane):
	preview = _get_preview(pane)
	return 0 if preview is None else preview.page_count()


@run_in_main_thread
def _call_preview(pane, method_name):
	# vitraj runs commands in a background thread. Widgets need the main one.
	preview = _get_preview(pane)
	if preview is None:
		return
	try:
		getattr(preview, method_name)()
	except RuntimeError:
		# Qt deleted the widget in the meantime (the panel was closed).
		pass


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
