from vitraj.impl.util.platform_ import is_mac
from vitraj.impl.util.qt.key_event import QtKeyEvent
from PySide6.QtCore import Qt
from unittest import TestCase

class QtKeyEventTest(TestCase):
	def test_tab(self):
		self.assertTrue(QtKeyEvent(Qt.Key_Tab, 0).matches('Tab'))
	def test_ctrl_a(self):
		modifier = Qt.MetaModifier if is_mac() else Qt.ControlModifier
		self.assertTrue(QtKeyEvent(Qt.Key_A, modifier).matches('Ctrl+A'))
	def test_empty(self):
		self.assertFalse(QtKeyEvent(0, 0).matches('a'))
class QtKeyEventStrTest(TestCase):
	def test_key_name(self):
		self.assertTrue(str(QtKeyEvent(Qt.Key_A, Qt.NoModifier)).endswith('A'))
	def test_unknown_key_is_hex(self):
		self.assertEqual('0x00', str(QtKeyEvent(0, Qt.NoModifier)))
