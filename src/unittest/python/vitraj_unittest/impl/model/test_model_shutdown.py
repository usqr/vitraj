from vitraj.impl.model.model import Model
from vitraj.fs import Column
from PyQt5.QtWidgets import QApplication
from unittest import TestCase

from time import sleep

import sys

# is_in_main_thread() needs a QApplication:
_app = QApplication.instance() or QApplication([])

class ModelShutdownTest(TestCase):
	def test_shutdown_clears_cache_of_location(self):
		fs = _SpyFileSystem()
		model = Model(fs, 'stub://dir', [Column()])
		model._worker.start()
		model.shutdown()
		model._worker._thread.join(5)
		self.assertEqual(['stub://dir'], fs.cleared)

class _SpyFileSystem:
	def __init__(self):
		self.cleared = []
	def remove_file_changed_callback(self, url, callback):
		raise ValueError('not registered')
	def clear_cache(self, url):
		self.cleared.append(url)

class ModelShutdownWhenClearCacheFailsTest(TestCase):
	def test_worker_thread_ends(self):
		fs = _SpyFileSystem()
		def clear_cache(url):
			raise FileNotFoundError(url)
		fs.clear_cache = clear_cache
		model = Model(fs, 'stub://dir', [Column()])
		excepthook_before = sys.excepthook
		sys.excepthook = lambda *args: None
		try:
			model._worker.start()
			model.shutdown()
			model._worker._thread.join(5)
		finally:
			sys.excepthook = excepthook_before
		self.assertFalse(model._worker._thread.is_alive())

class ModelShutdownStopsWorkerTest(TestCase):
	def test_worker_thread_ends(self):
		model = Model(_SpyFileSystem(), 'stub://dir', [Column()])
		model._worker.start()
		model.shutdown()
		model._worker._thread.join(5)
		self.assertFalse(model._worker._thread.is_alive())

class WorkerShutdownFromOwnThreadTest(TestCase):
	def test_does_not_raise(self):
		from vitraj.impl.model.worker import Worker
		import sys
		worker = Worker()
		errors = []
		excepthook_before = sys.excepthook
		sys.excepthook = lambda *args: errors.append(args)
		try:
			worker.start()
			worker.submit(1, worker.shutdown)
			worker._thread.join(5)
		finally:
			sys.excepthook = excepthook_before
		self.assertFalse(worker._thread.is_alive())
		self.assertEqual([], errors)

class SynchronousCallDuringShutdownTest(TestCase):
	def test_caller_does_not_wait_forever(self):
		# A file watcher thread calls a synchronous @transaction while the
		# worker is busy. Then the model shuts down. The caller must return.
		from threading import Event, Thread
		fs = _SpyFileSystem()
		model = Model(fs, 'stub://dir', [Column()])
		model._worker.start()
		release = Event()
		model._worker.submit(1, release.wait)
		caller = Thread(
			target=model.notify_file_added, args=('stub://dir/x',), daemon=True
		)
		caller.start()
		# Wait until the caller's task is in the queue (the worker is busy):
		for _ in range(500):
			if model._worker._queue.qsize():
				break
			sleep(.01)
		model.shutdown()
		release.set()
		caller.join(5)
		self.assertFalse(caller.is_alive())

class SynchronousTaskErrorTest(TestCase):
	def test_caller_returns_when_task_raises(self):
		from threading import Thread
		fs = _SpyFileSystem()
		def clear_cache(url):
			raise FileNotFoundError(url)
		fs.clear_cache = clear_cache
		model = Model(fs, 'stub://dir', [Column()])
		model._worker.start()
		excepthook_before = sys.excepthook
		sys.excepthook = lambda *args: None
		try:
			caller = Thread(
				target=model.notify_file_removed, args=('stub://dir/x',),
				daemon=True
			)
			caller.start()
			caller.join(5)
		finally:
			sys.excepthook = excepthook_before
		self.assertFalse(caller.is_alive())
		fs.clear_cache = lambda url: None
		model.shutdown()

class ShutdownOrderTest(TestCase):
	def test_queued_tasks_run_before_cache_clear(self):
		from threading import Event
		order = []
		fs = _SpyFileSystem()
		fs.clear_cache = lambda url: order.append('clear')
		model = Model(fs, 'stub://dir', [Column()])
		model._worker.start()
		release = Event()
		model._worker.submit(1, release.wait)
		model._worker.submit(5, lambda: order.append('task'))
		model.shutdown()
		release.set()
		model._worker._thread.join(5)
		self.assertEqual(['task', 'clear'], order)

class WorkerKwargsTest(TestCase):
	def test_kwargs_reach_function(self):
		from vitraj.impl.model.worker import Worker
		got = []
		worker = Worker()
		worker.start()
		worker.submit(1, lambda a, b=None: got.append((a, b)), 1, b=2)
		worker.shutdown()
		self.assertEqual([(1, 2)], got)

class TransactionAfterShutdownTest(TestCase):
	def test_queued_transaction_does_not_run_after_shutdown(self):
		# A transaction passed the caller-side check, then the model shut
		# down before the worker ran it. It must not touch the fs any more.
		from threading import Event
		cleared = []
		fs = _SpyFileSystem()
		fs.clear_cache = cleared.append
		model = Model(fs, 'stub://dir', [Column()])
		model._worker.start()
		release = Event()
		model._worker.submit(1, release.wait)
		model.reload()
		model._shutdown = True
		release.set()
		sleep(.2)
		self.assertEqual([], cleared)
		model._worker.submit(1, model._worker.shutdown)
