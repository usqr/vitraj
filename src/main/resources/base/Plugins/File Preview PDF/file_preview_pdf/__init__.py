"""
File Preview PDF - adds PDF rendering to the File Preview plugin.

Requires: PyMuPDF (pip install PyMuPDF)
Requires: File Preview plugin (must be loaded first)
"""
from PySide6.QtCore import QSizeF
from PySide6.QtGui import QImage

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
	from file_preview import PreviewWidget, PreviewPage, _format_size
except ImportError:
	PreviewWidget = None


def _show_pdf(widget, path):
	# The worker imports PyMuPDF (~400 ms) at the first use:
	widget.show_pages_async(
		lambda index, view: _render_pdf(path, index, view), 'Cannot render PDF'
	)


def _render_pdf(path, index, view):
	fitz = _load_fitz()
	if fitz is None:
		raise ImportError('PDF preview requires PyMuPDF (pip install PyMuPDF)')
	return _render_page(fitz, path, index, view)


def _render_page(fitz, path, index, view):
	"""
	Runs in a worker thread. Must not touch any widget. Open the file for
	each page: this is fast, and no PyMuPDF object lives between two jobs.
	"""
	with fitz.open(path) as doc:
		num_pages = len(doc)
		if num_pages == 0:
			raise ValueError('Empty PDF')
		index = min(max(index, 0), num_pages - 1)
		page = doc[index]
		# 1 point = 1 logical pixel at a zoom of 100%:
		size = QSizeF(page.rect.width, page.rect.height)
		scale = view.render_scale(size)
		pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
		fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
		image = QImage(
			pix.samples, pix.width, pix.height, pix.stride, fmt
		).copy()
	name = os.path.basename(path)
	if num_pages > 1:
		header = '%s (page %d of %d)' % (name, index + 1, num_pages)
	else:
		header = '%s (1 page)' % name
	try:
		file_size = os.path.getsize(path)
	except OSError:
		file_size = 0
	info = '%s  |  %d x %d pt' % (
		_format_size(file_size), round(size.width()), round(size.height())
	)
	return PreviewPage(image, info, header, num_pages, size)


if PreviewWidget is not None:
	PreviewWidget.register_handler('.pdf', _show_pdf)
