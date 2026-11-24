"""
File Preview PDF - adds PDF rendering to the File Preview plugin.

Requires: PyMuPDF (pip install PyMuPDF)
Requires: File Preview plugin (must be loaded first)
"""
from PyQt5.QtGui import QPixmap, QImage

from functools import lru_cache

import os


@lru_cache(maxsize=1)
def _load_fitz():
	"""
	Return the PyMuPDF module, or None if it is not installed. Import late:
	PyMuPDF takes ~400 ms to import and vitraj loads this plugin at startup.
	"""
	try:
		import fitz
	except ImportError:
		return None
	return fitz

try:
	from file_preview import PreviewWidget, _format_size
except ImportError:
	PreviewWidget = None


def _show_pdf(widget, path):
	_fitz = _load_fitz()
	if _fitz is None:
		widget._show_message('PDF preview requires PyMuPDF.\n\npip install PyMuPDF')
		return
	try:
		with _fitz.open(path) as doc:
			if len(doc) == 0:
				widget._show_message('Empty PDF')
				return
			page = doc[0]
			mat = _fitz.Matrix(150 / 72, 150 / 72)
			pix = page.get_pixmap(matrix=mat)
			if pix.alpha:
				fmt = QImage.Format_RGBA8888
			else:
				fmt = QImage.Format_RGB888
			qimg = QImage(
				pix.samples, pix.width, pix.height, pix.stride, fmt
			).copy()
			pixmap = QPixmap.fromImage(qimg)
			num_pages = len(doc)
			page_info = '%d pages' % num_pages if num_pages > 1 else '1 page'
			name = os.path.basename(path)
			widget._header.setText('%s (%s)' % (name, page_info))
			try:
				size = os.path.getsize(path)
			except OSError:
				size = 0
			info = '%s  |  %d x %d px' % (
				_format_size(size), pix.width, pix.height
			)
		widget.show_image_pixmap(pixmap, info)
	except Exception as e:
		widget._show_message('Cannot render PDF: %s' % e)


if PreviewWidget is not None:
	PreviewWidget.register_handler('.pdf', _show_pdf)
