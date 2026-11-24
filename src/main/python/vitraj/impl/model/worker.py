from functools import total_ordering
from queue import PriorityQueue
from threading import Thread, Lock, current_thread

import sys

class Worker:
	def __init__(self):
		self._thread = Thread(target=self._run, daemon=True)
		self._queue = PriorityQueue()
		self._shutdown = False
		self._shutdown_lock = Lock()
	def start(self):
		self._thread.start()
	def submit(self, priority, fn, *args, **kwargs):
		"""
		Lower priority means "run sooner".
		"""
		if priority < 1:
			raise ValueError('priority must be >= 1')
		with self._shutdown_lock:
			if self._shutdown:
				return False
			self._queue.put(WorkItem(priority, fn, *args, *kwargs))
			return True
	def shutdown(self):
		with self._shutdown_lock:
			self._shutdown = True
			# The stop marker sorts after all queued tasks. So they still run
			# (and see that the model shut down). This is necessary because
			# a synchronous @transaction caller waits for its task:
			self._queue.put(_StopMarker())
		# Model#shutdown() calls this from the worker thread itself. A thread
		# cannot join itself. The loop in #_run() ends after the current task:
		if current_thread() is not self._thread:
			self._thread.join()
	def _run(self):
		while True:
			task = self._queue.get()
			if task.is_shutdown():
				break
			task.run()
			self._queue.task_done()

@total_ordering
class WorkItem:
	def __init__(self, priority, fn, *args, **kwargs):
		self._fn = fn
		self._args = args
		self._kwargs = kwargs
		self._priority = priority
	def run(self):
		try:
			self._fn(*self._args, **self._kwargs)
		except BaseException as e:
			sys.excepthook(type(e), e, e.__traceback__)
	def is_shutdown(self):
		return False
	def __lt__(self, other):
		try:
			return self._priority < other._priority
		except AttributeError:
			return NotImplemented
	def __eq__(self, other):
		try:
			return self._fn, self._args, self._kwargs, self._priority == \
				   other._fn, other._args, other._kwargs, other._priority
		except AttributeError:
			return NotImplemented

class _StopMarker(WorkItem):
	def __init__(self):
		super().__init__(sys.maxsize, lambda: None)
	def is_shutdown(self):
		return True
