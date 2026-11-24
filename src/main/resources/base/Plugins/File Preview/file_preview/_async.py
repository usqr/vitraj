"""
Helpers that keep slow preview work off the main thread.
"""
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

class Debouncer(QObject):
	"""
	Call fn(arg) at once for the first call of a burst. During the burst,
	remember only the last arg. Call fn with it when no call came for
	interval_ms. So a fast cursor move does not render each file.
	"""
	def __init__(self, fn, interval_ms, parent=None):
		super().__init__(parent)
		self._fn = fn
		self._pending = None
		self._timer = QTimer(self)
		self._timer.setSingleShot(True)
		self._timer.setInterval(interval_ms)
		self._timer.timeout.connect(self._on_timeout)
	def __call__(self, arg):
		if self._timer.isActive():
			self._pending = (arg,)
		else:
			self._fn(arg)
		self._timer.start()
	def cancel(self):
		self._timer.stop()
		self._pending = None
	def _on_timeout(self):
		if self._pending is None:
			return
		(arg,), self._pending = self._pending, None
		self._fn(arg)

class AsyncRunner(QObject):
	"""
	Run one function at a time in a worker thread. Give its result to a
	callback in the thread of this object. A later #run(...) or #cancel()
	makes the result of an earlier call stale, and the callback does not get
	it.

	There is only one worker thread. This is also necessary for PyMuPDF,
	which does not support concurrent use from more than one thread.
	"""

	_done = pyqtSignal(int, object)

	def __init__(self, parent=None):
		super().__init__(parent)
		self._pool = QThreadPool(self)
		self._pool.setMaxThreadCount(1)
		self._token = 0
		self._callback = None
		self._done.connect(self._on_done)
	def run(self, fn, on_result):
		"""
		Call fn() in the worker thread. Then call on_result(result) in this
		thread. If fn() raises an Exception, `result` is that exception.
		"""
		self.cancel()
		token = self._token
		self._callback = on_result
		self._pool.start(_Job(fn, lambda result: self._emit(token, result)))
	def cancel(self):
		self._token += 1
		self._callback = None
	def wait(self, msecs=-1):
		return self._pool.waitForDone(msecs)
	def _emit(self, token, result):
		try:
			self._done.emit(token, result)
		except RuntimeError:
			# The C++ object was deleted (the preview panel was closed).
			pass
	def _on_done(self, token, result):
		if token != self._token or self._callback is None:
			return
		callback, self._callback = self._callback, None
		callback(result)

class _Job(QRunnable):
	def __init__(self, fn, report):
		super().__init__()
		self._fn = fn
		self._report = report
	def run(self):
		try:
			result = self._fn()
		except Exception as e:
			result = e
		self._report(result)
