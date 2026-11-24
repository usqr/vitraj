"""
The base of vitraj's application context. This replaces the
ApplicationContext of fbs_runtime with the same behavior.
"""
from functools import lru_cache
from os.path import dirname, exists, join, pardir, realpath
from vitraj.impl.util.excepthook import Excepthook, StderrExceptionHandler
from vitraj.impl.util.platform_ import is_mac, is_windows
from vitraj.impl.util.signal_wakeup import SignalWakeupHandler

import errno
import os
import sys

def cached_property(getter):
	"""A @property that computes its value one time."""
	return property(lru_cache()(getter))

def is_frozen():
	"""True in the compiled app, False when vitraj runs from source."""
	return getattr(sys, 'frozen', False)

_APPLICATION_CONTEXT = None

def get_application_context(development_cls, frozen_cls=None):
	global _APPLICATION_CONTEXT
	if _APPLICATION_CONTEXT is None:
		cls = (frozen_cls or development_cls) if is_frozen() \
			else development_cls
		_APPLICATION_CONTEXT = cls()
	return _APPLICATION_CONTEXT

class ApplicationContext:
	def __init__(self):
		if self.excepthook:
			self.excepthook.install()
		# Many Qt classes need a QApplication. So make it before all else:
		self.app
		# On Windows, vitraj is not a console app. So Ctrl+C does not apply:
		if not is_windows():
			from PyQt5.QtNetwork import QAbstractSocket
			self._signal_wakeup_handler = \
				SignalWakeupHandler(self.app, QAbstractSocket)
			self._signal_wakeup_handler.install()
		if self.app_icon:
			self.app.setWindowIcon(self.app_icon)
	def run(self):
		raise NotImplementedError()
	@cached_property
	def app(self):
		from PyQt5.QtWidgets import QApplication
		result = QApplication([])
		result.setApplicationName(self.build_settings['app_name'])
		result.setApplicationVersion(self.build_settings['version'])
		return result
	@cached_property
	def build_settings(self):
		from vitraj.impl.fbs_build import load_build_settings
		return load_build_settings()
	def get_resource(self, *rel_path):
		"""
		Return the absolute path of the given resource. Raise
		FileNotFoundError if it does not exist.
		"""
		for resource_dir in self._resource_dirs:
			resource_path = join(resource_dir, *rel_path)
			if exists(resource_path):
				return realpath(resource_path)
		raise FileNotFoundError(
			errno.ENOENT, 'Could not locate resource', os.sep.join(rel_path)
		)
	@cached_property
	def exception_handlers(self):
		return [StderrExceptionHandler()]
	@cached_property
	def app_icon(self):
		# On Mac, the OS shows the icon of the app bundle.
		if not is_mac():
			from PyQt5.QtGui import QIcon
			return QIcon(self.get_resource('Icon.ico'))
	@cached_property
	def excepthook(self):
		return Excepthook(self.exception_handlers)
	@cached_property
	def _resource_dirs(self):
		if is_frozen():
			app_dir = dirname(sys.executable)
			return [join(app_dir, pardir, 'Resources') if is_mac() else app_dir]
		from vitraj.impl.fbs_build import get_source_resource_dirs
		return get_source_resource_dirs()
