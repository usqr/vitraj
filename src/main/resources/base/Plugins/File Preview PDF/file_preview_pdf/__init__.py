"""
File Preview PDF - adds PDF rendering to the File Preview plugin.

Requires: PyMuPDF (pip install PyMuPDF)
Requires: File Preview plugin (must be loaded first)
"""
from PyQt5.QtGui import QImage

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
	from file_preview import PreviewWidget, PreviewImage, _format_size
except ImportError:
	PreviewWidget = None


def _show_pdf(widget, path):
	fitz = _load_fitz()
	if fitz is None:
		widget._show_message('PDF preview requires PyMuPDF.\n\npip install PyMuPDF')
		return
	widget.show_image_async(
		lambda: _render_first_page(fitz, path), 'Cannot render PDF'
	)


def _render_first_page(fitz, path):
	"""Runs in a worker thread. Must not touch any widget."""
	with fitz.open(path) as doc:
		num_pages = len(doc)
		if num_pages == 0:
			raise ValueError('Empty PDF')
		mat = fitz.Matrix(150 / 72, 150 / 72)
		pix = doc[0].get_pixmap(matrix=mat)
		fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
		image = QImage(
			pix.samples, pix.width, pix.height, pix.stride, fmt
		).copy()
	page_info = '%d pages' % num_pages if num_pages > 1 else '1 page'
	header = '%s (%s)' % (os.path.basename(path), page_info)
	try:
		size = os.path.getsize(path)
	except OSError:
		size = 0
	info = '%s  |  %d x %d px' % (_format_size(size), pix.width, pix.height)
	return PreviewImage(image, info, header)


if PreviewWidget is not None:
	PreviewWidget.register_handler('.pdf', _show_pdf)
