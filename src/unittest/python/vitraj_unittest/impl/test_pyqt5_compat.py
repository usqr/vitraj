from os.path import dirname, join
from unittest import TestCase

import subprocess
import sys

_SRC = join(dirname(__file__), '..', '..', '..', '..', 'main', 'python')

class PyQt5CompatTest(TestCase):
	"""
	Each test runs in a new Python process, so that the PyQt5 modules of the
	compatibility layer do not stay in this process.
	"""
	def test_star_imports(self):
		self._run(
			'from PyQt5.QtWidgets import *',
			'from PyQt5.QtCore import *',
			'assert QPushButton and QAction and Qt and pyqtSignal'
		)
	def test_module_import_and_signal(self):
		self._run(
			'from PyQt5 import QtCore',
			'from PyQt5.QtWidgets import QApplication',
			'app = QApplication([])',
			'class C(QtCore.QObject):',
			'    changed = QtCore.pyqtSignal(int)',
			'got = []',
			'c = C()',
			'c.changed.connect(got.append)',
			'c.changed.emit(5)',
			'assert got == [5], got'
		)
	def test_qvariant_and_versions(self):
		self._run(
			'from PyQt5.QtCore import QVariant, QT_VERSION_STR',
			'assert QVariant() is None and QVariant(3) == 3',
			'assert QT_VERSION_STR.startswith("6.")'
		)
	def test_sip(self):
		self._run(
			'import sip',
			'from PyQt5.QtCore import QObject',
			'o = QObject()',
			'assert not sip.isdeleted(o)',
			'sip.transferto(o, None)',
			'sip.delete(o)',
			'assert sip.isdeleted(o)'
		)
	def _run(self, *lines):
		code = '\n'.join([
			'import sys',
			'sys.path.insert(0, %r)' % _SRC,
			'from vitraj.impl import pyqt5_compat',
			'pyqt5_compat.install()',
		] + list(lines))
		result = subprocess.run(
			[sys.executable, '-c', code], capture_output=True, text=True
		)
		self.assertEqual(0, result.returncode, result.stderr)
