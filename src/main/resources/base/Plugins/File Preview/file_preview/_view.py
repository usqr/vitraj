"""
The zoom math and the canvas that shows a preview image at a zoom.
"""
from collections import namedtuple
from math import sqrt

from PySide6.QtCore import QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

ZOOM_STEPS = (0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4)
MIN_ZOOM = ZOOM_STEPS[0]
MAX_ZOOM = ZOOM_STEPS[-1]
# The largest image (in pixels) that a page render can make. A higher zoom
# scales this image up when it paints:
MAX_RENDER_PIXELS = 40 * 1000 * 1000

def clamp_zoom(zoom):
	return min(max(zoom, MIN_ZOOM), MAX_ZOOM)

def step_zoom(current, direction):
	"""The next step in ZOOM_STEPS above (direction > 0) or below `current`."""
	if direction > 0:
		bigger = (z for z in ZOOM_STEPS if z > current * 1.01)
		return next(bigger, MAX_ZOOM)
	smaller = (z for z in reversed(ZOOM_STEPS) if z < current / 1.01)
	return next(smaller, MIN_ZOOM)

def fit_zoom(natural, available):
	"""The zoom that fits a QSizeF `natural` into the QSize `available`."""
	if natural.isEmpty() or available.isEmpty():
		return 1.0
	return min(
		available.width() / natural.width(),
		available.height() / natural.height()
	)

def capped_scale(natural, scale):
	"""
	Make `scale` smaller if `natural` * `scale` has more than
	MAX_RENDER_PIXELS pixels.
	"""
	area = natural.width() * natural.height() * scale * scale
	if area <= MAX_RENDER_PIXELS:
		return scale
	return scale * sqrt(MAX_RENDER_PIXELS / area)

class PageView(namedtuple('PageView', ('zoom', 'available', 'dpr'))):
	"""
	What a page render must produce. `zoom` is None for "fit". `available`
	is the QSize of the view in logical pixels. `dpr` is the device pixel
	ratio of the screen.
	"""
	__slots__ = ()
	def render_scale(self, natural):
		"""
		The scale from the QSizeF `natural` (the size at 100%, in logical
		pixels) to the pixels of the image that a render must make.
		"""
		zoom = self.zoom
		if zoom is None:
			zoom = fit_zoom(natural, self.available)
		return capped_scale(natural, zoom * self.dpr)

class ImageCanvas(QWidget):
	"""
	Paints a pixmap at a size, in the center of the widget. A pixmap that is
	larger than the size is scaled down one time, for quality. A pixmap that
	is smaller is scaled up when it paints. So a high zoom does not make a
	very large pixmap.
	"""
	def __init__(self, parent=None):
		super().__init__(parent)
		self._pixmap = None
		self._scaled = None
		self._size = QSizeF()
	def set_pixmap(self, pixmap):
		self._pixmap = pixmap
		self._scaled = None
		self.update()
	def pixmap(self):
		return self._pixmap
	def set_display_size(self, size):
		"""`size` is a QSizeF in logical pixels."""
		if size != self._size:
			self._size = size
			self._scaled = None
			self.update()
	def paintEvent(self, _event):
		pixmap = self._display_pixmap()
		if pixmap is None:
			return
		rect = QRectF(0, 0, self._size.width(), self._size.height())
		rect.moveCenter(QRectF(self.rect()).center())
		painter = QPainter(self)
		painter.setRenderHint(QPainter.SmoothPixmapTransform)
		painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
	def _display_pixmap(self):
		if self._pixmap is None or self._size.isEmpty():
			return None
		if self._scaled is None:
			self._scaled = self._scale_down(self._pixmap)
		return self._scaled
	def _scale_down(self, pixmap):
		dpr = self.devicePixelRatioF()
		device = QSize(
			round(self._size.width() * dpr), round(self._size.height() * dpr)
		)
		if device.width() >= pixmap.width():
			return pixmap
		return pixmap.scaled(device, Qt.KeepAspectRatio, Qt.SmoothTransformation)
