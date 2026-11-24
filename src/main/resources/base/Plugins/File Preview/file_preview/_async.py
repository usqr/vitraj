"""
Helpers that keep slow preview work off the main thread.
"""
import shiboken6
import weakref

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

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

	def __init__(self, parent=None):
		super().__init__(parent)
		self._pool = _shared_pool()
		self._relay = _shared_relay()
		self._job = None
		self._token = 0
		self._callback = None
	def run(self, fn, on_result):
		"""
		Call fn() in the worker thread. Then call on_result(result) in this
		thread. If fn() raises an Exception, `result` is that exception.
		"""
		self.cancel()
		token = self._token
		self._callback = on_result
		runner = weakref.ref(self)
		relay = self._relay
		self._job = _Job(
			fn, lambda result: relay.done.emit(runner, token, result)
		)
		self._pool.start(self._job)
	def cancel(self):
		self._token += 1
		self._callback = None
		if self._job is not None:
			# Remove the job if it did not start yet. A stale job that already
			# runs finishes, and #_on_done drops its result:
			try:
				self._pool.tryTake(self._job)
			except RuntimeError:
				# The job finished and Qt deleted it (autoDelete).
				pass
			self._job = None
	def wait(self, msecs=-1):
		return self._pool.waitForDone(msecs)
	def _on_done(self, token, result):
		if token != self._token or self._callback is None:
			return
		callback, self._callback = self._callback, None
		callback(result)

_POOL = None
_RELAY = None

class _Relay(QObject):
	"""
	Carries results from the worker to the main thread. It has no parent
	and lives until the app exits. So the worker never emits a signal of
	an object that Qt deletes at the same time (when the panel closes).
	"""
	done = Signal(object, int, object) # (weakref to runner, token, result)

def _shared_relay():
	"""Call this in the main thread first, so the relay lives there."""
	global _RELAY
	if _RELAY is None:
		_RELAY = _Relay()
		_RELAY.done.connect(_deliver)
	return _RELAY

def _deliver(runner_ref, token, result):
	runner = runner_ref()
	if runner is None or not shiboken6.isValid(runner):
		return
	try:
		runner._on_done(token, result)
	except RuntimeError:
		# Qt deleted the runner or the preview widget (the panel closed).
		pass

def _shared_pool():
	"""
	One worker thread for all previews. The pool has no parent and lives
	until the app exits. So when Qt deletes a preview widget, it does not
	wait (on the main thread) for a running job.
	"""
	global _POOL
	if _POOL is None:
		_POOL = QThreadPool()
		_POOL.setMaxThreadCount(1)
	return _POOL

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
