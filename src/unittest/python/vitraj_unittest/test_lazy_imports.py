from os.path import dirname, join
from unittest import TestCase

import subprocess
import sys

_SRC_MAIN = join(dirname(__file__), '..', '..', '..', 'main')
_PLUGINS = join(_SRC_MAIN, 'resources', 'base', 'Plugins')
_PATHS = [
	join(_SRC_MAIN, 'python'),
	join(_PLUGINS, 'Core'),
	join(_PLUGINS, 'File Preview'),
	join(_PLUGINS, 'File Preview PDF'),
]

class LazyImportsTest(TestCase):
	"""
	These modules load at startup. They must not import slow, optional
	packages before the user needs them.
	"""
	def test_github_does_not_import_requests(self):
		self._assert_not_imported('core.github', 'requests')
	def test_file_preview_does_not_import_pillow(self):
		self._assert_not_imported('file_preview', 'PIL')
	def test_file_preview_pdf_does_not_import_pymupdf(self):
		self._assert_not_imported('file_preview_pdf', 'fitz')
	def _assert_not_imported(self, module, heavy_module):
		code = (
			'import sys; sys.path[:0] = %r; import %s; '
			'print(%r in sys.modules)' % (_PATHS, module, heavy_module)
		)
		output = subprocess.run(
			[sys.executable, '-c', code], capture_output=True, text=True,
			check=True
		).stdout.strip()
		self.assertEqual('False', output)
