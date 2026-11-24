from vitraj.impl.model.model import Model
from vitraj.impl.model.drag_and_drop import DragAndDrop
from vitraj.impl.model.diff import ComputeDiff
from vitraj.impl.model.file_watcher import FileWatcher
from vitraj.impl.model.table import TableModel, Cell, Row
from vitraj.impl.model.worker import Worker
from vitraj.impl.util.qt.thread import run_in_main_thread
from vitraj.impl.util.url import is_pardir
from vitraj.url import dirname, splitscheme
from PySide6.QtCore import Signal, QSortFilterProxyModel, Qt

from threading import Lock

import errno
import sys

class SortedFileSystemModel(QSortFilterProxyModel):

	location_changed = Signal(str)
	location_loaded = Signal(str)
	file_renamed = Signal(str, str)
	files_dropped = Signal(list, str, bool)
	sort_order_changed = Signal(int, int)
	transaction_ended = Signal()

	def __init__(self, parent, fs, null_location):
		super().__init__(parent)
		self._fs = fs
		self._null_location = null_location
		self._filters = []
		self._already_visited = set()
		self._num_rows_to_preload = 0
		self._location_request = 0
		self._location_request_lock = Lock()
		self._resolver = Worker()
		self._resolver.start()
		# Synchronous, so that there always is a source model:
		self._show(*self._resolve(null_location, ''), True, lambda: None)
		self._fs.file_removed.add_callback(self._on_file_removed)
	def set_num_rows_to_preload(self, preload_rows):
		self._num_rows_to_preload = preload_rows
	def set_location(
		self, url, sort_column='', ascending=True, callback=None, onerror=None
	):
		"""
		Resolve `url` in a background thread, then show it. This keeps a slow
		drive from blocking the main thread. A later call cancels an earlier
		one. On an error, call onerror(e, url) in the main thread, inside the
		`except` block (so a bare `raise` works). onerror returns the next URL
		to try, or None to stop. If onerror raises, or a URL fails two times,
		the error goes to sys.excepthook.
		"""
		if callback is None:
			callback = lambda: None
		if onerror is None:
			onerror = _reraise
		# set_path(...) can run in any thread. So count under a lock:
		with self._location_request_lock:
			self._location_request += 1
			request_id = self._location_request
		request = _LocationRequest(
			request_id, sort_column, ascending, callback, onerror
		)
		self._resolve_async(request, url)
	def _resolve_async(self, request, url):
		def task():
			try:
				try:
					resolved = self._resolve(url, request.sort_column)
				except Exception as e:
					self._on_resolve_error(request, e, url)
				else:
					self._on_resolved(request, *resolved)
			except SystemExit:
				# run_in_main_thread raises this when the app quits. Then the
				# location change does not matter any more.
				pass
		self._resolver.submit(1, task)
	@run_in_main_thread
	def _on_resolve_error(self, request, e, url):
		if request.id != self._location_request:
			return
		try:
			try:
				raise e
			except Exception:
				next_url = request.onerror(e, url)
		except Exception:
			sys.excepthook(*sys.exc_info())
			return
		if next_url is None:
			return
		if next_url in request.error_urls:
			sys.excepthook(type(e), e, e.__traceback__)
			return
		request.error_urls.add(next_url)
		self._resolve_async(request, next_url)
	@run_in_main_thread
	def _on_resolved(self, request, url, columns, sort_col_index):
		if request.id != self._location_request:
			return
		self._show(url, columns, sort_col_index, request.ascending, request.callback)
	def _show(self, url, columns, sort_col_index, ascending, callback):
		old_model = self.sourceModel()
		if old_model:
			if url == old_model.get_location():
				callback()
				return
			old_model.shutdown()
		if url in self._already_visited:
			orig_callback = callback
			def callback():
				orig_callback()
				self.reload()
		self._set_location_main(
			url, columns, sort_col_index, ascending, callback
		)
	def _resolve(self, url, sort_column):
		"""
		Do the file system work of a location change: resolve `url` and get
		its columns. Return (url, columns, sort_col_index).
		"""
		try:
			url_resolved = self._fs.resolve(url)
		except FileNotFoundError:
			raise
		except OSError as e:
			if e.errno == errno.ENOENT:
				raise
			# For example: On Windows, Path(...).resolve()'ing on a directory
			# in a Cryptomator mapped drive gives:
			# 	OSError: [WinError 1] Incorrect function
			# But we can still list the dir's contents and do everything else
			# that's required. So ignore the error and continue:
			url_resolved = url
		if splitscheme(url_resolved)[0] != splitscheme(url)[0]:
			# In general, we do not want to simply rewrite the URL to its
			# resolved form. This is for instance because we don't want to
			# rewrite C:\Windows\System32 -> ...\SysWOW64. However, if the
			# file system changes, we do need to follow the rewrite to support
			# cases such as zip:/// resolving to file:///.
			url = url_resolved
		columns = self._fs.get_columns(url)
		sort_col_index = 0
		if sort_column:
			column_names = [col.get_qualified_name() for col in columns]
			try:
				sort_col_index = column_names.index(sort_column)
			except ValueError:
				pass
		return url, columns, sort_col_index
	@run_in_main_thread
	def _set_location_main(
		self, url, columns, sort_col_index, ascending, callback
	):
		old_model = self.sourceModel()
		if old_model:
			self._disconnect_signals(old_model)
		new_model = Model(
			self._fs, url, columns, sort_col_index, ascending,
			self._num_rows_to_preload, self._filters
		)
		self.setSourceModel(new_model)
		self._connect_signals(new_model)
		self._already_visited.add(url)
		self.location_changed.emit(url)
		order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
		# The signal carries ints. In PySide6, Qt.SortOrder is a Python enum:
		self.sort_order_changed.emit(sort_col_index, order.value)
		# Start model at the very end to ensure the above signals, in particular
		# location_changed, are processed beforehand. The motivation for this is
		# that the FilterBar relies on this signal to clear its filter. If we
		# start the model before the FilterBar has had a chance to do this, then
		# the model may start loading files with the wrong filter.
		new_model.start(callback)
	def setSourceModel(self, model):
		# Qt does not own the source model. Keep a Python reference, so that
		# Python does not delete it while the proxy uses it:
		self._source_model = model
		super().setSourceModel(model)
	def row_is_loaded(self, i):
		source_row = self.mapToSource(self.index(i, 0)).row()
		return self.sourceModel().row_is_loaded(source_row)
	def load_rows(self, rows, callback=None):
		source_rows = [self._map_row_to_source(row) for row in rows]
		self.sourceModel().load_rows(source_rows, callback)
	def _map_row_to_source(self, i):
		return self.mapToSource(self.index(i, 0)).row()
	def get_location(self):
		return self.sourceModel().get_location()
	def get_columns(self):
		return self.sourceModel().get_columns()
	def reload(self):
		self.sourceModel().reload()
	def sort(self, column, order=Qt.AscendingOrder):
		self.sourceModel().sort(column, order)
	def add_filter(self, filter_):
		self._filters.append(filter_)
		self.sourceModel().add_filter(filter_)
	def remove_filter(self, filter_):
		try:
			self._filters.remove(filter_)
		except ValueError:
			pass
		self.sourceModel().remove_filter(filter_)
	def url(self, index):
		return self.sourceModel().url(self.mapToSource(index))
	def find(self, url):
		return self.mapFromSource(self.sourceModel().find(url))
	def _on_file_removed(self, url):
		if not is_pardir(url, self.get_location()):
			return
		dir_ = dirname(url)
		if dir_ == url:
			self.set_location(self._null_location)
		else:
			self.set_location(dir_, onerror=self._on_parent_error)
	def _on_parent_error(self, e, url):
		# In a perfect world, would like to only handle FileNotFoundError
		# here. But there can of course also be other reasons. For example,
		# when on a network share on Windows, we may get a PermissionError
		# trying to list a parent directory we don't have access to. So go up
		# on all OSErrors and in the worst case go to null://.
		if not isinstance(e, OSError):
			raise
		parent = dirname(url)
		return self._null_location if parent == url else parent
	def _connect_signals(self, model):
		# Would prefer signal.connect(self.signal.emit) here. But PyQt doesn't
		# support it. So we need Python wrappers "_emit_...":
		model.location_loaded.connect(self._emit_location_loaded)
		model.location_disappeared.connect(self._on_file_removed)
		model.file_renamed.connect(self._emit_file_renamed)
		model.files_dropped.connect(self._emit_files_dropped)
		model.sort_order_changed.connect(self._emit_sort_order_changed)
		model.transaction_ended.add_callback(self._emit_transaction_ended)
	def _disconnect_signals(self, model):
		# Would prefer signal.disconnect(self.signal.emit) here. But PyQt
		# doesn't support it. So we need Python wrappers "_emit_...":
		model.location_loaded.disconnect(self._emit_location_loaded)
		model.location_disappeared.disconnect(self._on_file_removed)
		model.file_renamed.disconnect(self._emit_file_renamed)
		model.files_dropped.disconnect(self._emit_files_dropped)
		model.sort_order_changed.disconnect(self._emit_sort_order_changed)
		model.transaction_ended.remove_callback(self._emit_transaction_ended)
	def _emit_location_loaded(self, location):
		self.location_loaded.emit(location)
	def _emit_file_renamed(self, old, new):
		self.file_renamed.emit(old, new)
	def _emit_files_dropped(self, urls, dest, is_copy):
		self.files_dropped.emit(urls, dest, is_copy)
	def _emit_sort_order_changed(self, column, order):
		self.sort_order_changed.emit(column, order)
	def _emit_transaction_ended(self):
		self.transaction_ended.emit()
	def __str__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.get_location())

def _reraise(e, url):
	raise

class _LocationRequest:
	def __init__(self, id_, sort_column, ascending, callback, onerror):
		self.id = id_
		self.sort_column = sort_column
		self.ascending = ascending
		self.callback = callback
		self.onerror = onerror
		self.error_urls = set()
