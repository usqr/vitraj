from PySide6.QtCore import QItemSelectionModel as QISM, QEvent
from PySide6.QtWidgets import QTableView

class MoveWithoutUpdatingSelection(QTableView):
	def selectionCommand(self, index, event):
		if event:
			if event.type() == QEvent.MouseButtonPress and event.modifiers():
				super_result = super().selectionCommand(index, event)
				# Don't blindly select - toggle:
				return super_result & (~QISM.Select) | QISM.Toggle
		return QISM.NoUpdate