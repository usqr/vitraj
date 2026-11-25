from vitraj.impl.util.qt import ClickFocus, WA_MacShowFocusRect
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

class LocationBar(QLineEdit):

	clicked = Signal()

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFocusPolicy(ClickFocus)
		self.setAttribute(WA_MacShowFocusRect, 0)
		self.setReadOnly(True)
	def mousePressEvent(self, e):
		super().mousePressEvent(e)
		self.clicked.emit()
