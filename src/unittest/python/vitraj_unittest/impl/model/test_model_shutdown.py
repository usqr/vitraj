from vitraj.impl.model.model import Model
from vitraj.fs import Column
from unittest import TestCase

import sys

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
