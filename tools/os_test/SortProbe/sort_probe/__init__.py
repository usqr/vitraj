"""
Write the state of the vitraj window to a JSON file.

The os_test driver (tools/os_test/click_test.py) reads this file. It uses the
data to find the click points and to see which popups are open.

Do not install this plugin for normal use.
"""

from PyQt5.QtCore import QPoint, QTimer, Qt
from PyQt5.QtWidgets import (
	QAbstractButton, QApplication, QFrame, QLabel, QMessageBox
)
from vitraj import DirectoryPaneListener

import json
import os
import tempfile
import time

_INTERVAL_MS = 200
# The timer is on the QApplication, so that a reload of the plugin finds it:
_TIMER_ATTR = '_vitraj_os_test_timer'

def _state_path():
	return os.environ.get(
		'VITRAJ_OS_TEST_STATE',
		os.path.join(tempfile.gettempdir(), 'vitraj-os-test-state.json')
	)

def _rect(widget):
	top_left = widget.mapToGlobal(QPoint(0, 0))
	return [top_left.x(), top_left.y(), widget.width(), widget.height()]

def _texts(widget):
	result = []
	for label in widget.findChildren(QLabel):
		text = label.text()
		if text:
			result.append(text)
	return result

def _buttons(widget):
	result = []
	for button in widget.findChildren(QAbstractButton):
		if not button.isVisible():
			continue
		result.append({'text': button.text(), 'rect': _rect(button)})
	return result

def _pane_state(pane, index):
	widget = getattr(pane, '_widget', None)
	model = getattr(widget, '_model', None)
	view = getattr(widget, '_file_view', None)
	if model is None or view is None:
		return None
	return {
		'index': index,
		'url': model.get_location(),
		'rect': _rect(widget),
		'viewport': _rect(view.viewport()),
		'headers': _headers(model, view),
		'rows': _rows(model, view),
	}

def _headers(model, view):
	header = view.horizontalHeader()
	origin = header.viewport().mapToGlobal(QPoint(0, 0))
	top = header.mapToGlobal(QPoint(0, 0)).y()
	result = []
	for section in range(model.columnCount()):
		text = model.headerData(section, Qt.Horizontal)
		result.append({
			'section': section,
			'text': '' if text is None else str(text),
			'rect': [
				origin.x() + header.sectionViewportPosition(section),
				top, header.sectionSize(section), header.height()
			],
		})
	return result

def _rows(model, view):
	origin = view.viewport().mapToGlobal(QPoint(0, 0))
	current = view.currentIndex().row()
	result = []
	for row in range(model.rowCount()):
		index = model.index(row, 0)
		name = model.data(index)
		result.append({
			'row': row,
			'name': '' if name is None else str(name),
			# A plain click moves the cursor. It does not select the row.
			'current': row == current,
			'rect': [
				origin.x(), origin.y() + view.rowViewportPosition(row),
				view.viewport().width(), view.rowHeight(row)
			],
		})
	return result

def _popup(widget):
	return {
		'class': type(widget).__name__,
		'title': widget.windowTitle(),
		'rect': _rect(widget),
		'texts': _texts(widget),
		'buttons': _buttons(widget),
		'message_box': isinstance(widget, QMessageBox),
	}

def _popups(main_window):
	result = []
	for widget in QApplication.topLevelWidgets():
		if widget is main_window or not widget.isVisible():
			continue
		if type(widget).__name__.startswith('QTipLabel'):
			continue
		result.append(_popup(widget))
	if main_window is not None:
		# An Overlay is a child of the main window, not a top-level window.
		for widget in main_window.findChildren(QFrame):
			if type(widget).__name__ == 'Overlay' and widget.isVisible():
				result.append(_popup(widget))
	return result

def _write_state():
	from vitraj.impl.application_context import get_application_context
	context = get_application_context()
	main_window = context.main_window
	panes = []
	for index, pane in enumerate(context.window.get_panes()):
		state = _pane_state(pane, index)
		if state is not None:
			panes.append(state)
	state = {
		'pid': os.getpid(),
		'time': time.time(),
		'double_click_ms': QApplication.doubleClickInterval(),
		'panes': panes,
		'popups': _popups(main_window),
	}
	path = _state_path()
	tmp = path + '.tmp'
	with open(tmp, 'w') as f:
		json.dump(state, f)
	os.replace(tmp, path)

def _tick():
	try:
		_write_state()
	except Exception as e:
		path = _state_path()
		with open(path + '.tmp', 'w') as f:
			json.dump({'pid': os.getpid(), 'error': repr(e)}, f)
		os.replace(path + '.tmp', path)

def _start():
	# Plugin listeners are made on the main thread, so the timer fires there.
	app = QApplication.instance()
	old_timer, old_tick = getattr(app, _TIMER_ATTR, (None, None))
	if old_tick is _tick:
		return
	if old_timer is not None:
		# A reload of the plugin imported this module again.
		old_timer.stop()
	timer = QTimer(app)
	timer.setInterval(_INTERVAL_MS)
	timer.timeout.connect(_tick)
	timer.start()
	setattr(app, _TIMER_ATTR, (timer, _tick))

class SortProbeListener(DirectoryPaneListener):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		_start()
