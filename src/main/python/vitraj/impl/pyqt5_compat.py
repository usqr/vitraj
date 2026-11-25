"""
Third-party plugins (from fman and vitraj) import PyQt5. vitraj uses PySide6
(Qt 6). install() makes `import PyQt5...` give PySide6, with the PyQt5 names
that plugins use: pyqtSignal, pyqtSlot, pyqtProperty, QVariant, sip and the
classes that Qt 6 moved from QtWidgets to QtGui (for example QAction).

It cannot hide all differences between PyQt5 and PySide6. For example,
enum values through an instance (`self.Yes`) do not work in PySide6.
"""
from importlib import import_module
from PySide6.QtCore import Property, Signal, Slot, qVersion

import shiboken6
import sys
import types

_MODULES = ('QtCore', 'QtGui', 'QtWidgets', 'QtNetwork', 'QtSvg', 'QtTest')
_MOVED_TO_QTGUI = (
	'QAction', 'QActionGroup', 'QShortcut', 'QFileSystemModel',
	'QUndoCommand', 'QUndoGroup', 'QUndoStack'
)

def install():
	package = types.ModuleType('PyQt5')
	package.__path__ = []
	package.vitraj_compat = True
	sys.modules['PyQt5'] = package
	for name in _MODULES:
		try:
			source = import_module('PySide6.' + name)
		except ImportError:
			continue
		module = _make_module('PyQt5.' + name, source)
		sys.modules[module.__name__] = module
		setattr(package, name, module)
	_add_pyqt5_names(sys.modules['PyQt5.QtCore'])
	_add_moved_classes()
	for name in _MODULES:
		module = sys.modules.get('PyQt5.' + name)
		if module is not None:
			module.__all__ = sorted(set(module.__all__) | set(_public(module)))
	sip = _make_sip_module()
	sys.modules['PyQt5.sip'] = sip
	package.sip = sip
	# Old plugins use `import sip`:
	sys.modules.setdefault('sip', sip)

def _make_module(name, source):
	"""
	A module that forwards to `source`. PySide6 loads its classes lazily, so
	use __getattr__, and __all__ for `from ... import *`.
	"""
	result = types.ModuleType(name)
	result.__getattr__ = lambda attr: getattr(source, attr)
	result.__all__ = [key for key in dir(source) if not key.startswith('_')]
	return result

def _public(module):
	return [key for key in vars(module) if not key.startswith('_')]

def _add_pyqt5_names(qt_core):
	qt_core.pyqtSignal = _pyqt_signal
	qt_core.pyqtSlot = _pyqt_slot
	qt_core.pyqtProperty = _pyqt_property
	qt_core.QVariant = QVariant
	qt_core.QT_VERSION_STR = qVersion()
	qt_core.PYQT_VERSION_STR = '5.15 (vitraj PySide6 compatibility)'

class QVariant:
	"""
	PySide6 has no QVariant. Plain Python values take its place:
	QVariant(x) gives x. As a type (for example pyqtSignal(QVariant)), it
	means `object`.
	"""
	def __new__(cls, value=None):
		return value

def _to_pyside_type(type_):
	if isinstance(type_, (list, tuple)):
		return type(type_)(_to_pyside_type(t) for t in type_)
	return object if type_ is QVariant or type_ == 'QVariant' else type_

def _pyqt_signal(*types, **kwargs):
	return Signal(*(_to_pyside_type(t) for t in types), **kwargs)

def _pyqt_slot(*types, **kwargs):
	return Slot(*(_to_pyside_type(t) for t in types), **kwargs)

def _pyqt_property(type_, *args, **kwargs):
	return Property(_to_pyside_type(type_), *args, **kwargs)

def _add_moved_classes():
	qt_gui = sys.modules.get('PyQt5.QtGui')
	qt_widgets = sys.modules.get('PyQt5.QtWidgets')
	if qt_gui is None or qt_widgets is None:
		return
	for name in _MOVED_TO_QTGUI:
		if hasattr(qt_gui, name):
			setattr(qt_widgets, name, getattr(qt_gui, name))

def _make_sip_module():
	result = types.ModuleType('PyQt5.sip')
	result.isdeleted = lambda obj: not shiboken6.isValid(obj)
	result.delete = shiboken6.delete
	# PySide6 manages ownership by itself. These have no effect:
	result.transferto = lambda obj, owner: None
	result.transferback = lambda obj: None
	return result
