"""
Benchmark: load a large directory into the real model and table view, then
scroll through it. Prints the times and, with --profile, the top functions.

Usage (from the repo root):

	venv/bin/python tools/bench/dir_load.py [--files 5000] [--profile]
"""
from argparse import ArgumentParser
from os.path import abspath, dirname, join, realpath
from tempfile import mkdtemp
from time import perf_counter

import cProfile
import os
import pstats
import shutil
import sys

_REPO = dirname(dirname(dirname(abspath(__file__))))
sys.path[:0] = [
	join(_REPO, 'src', 'main', 'python'),
	join(_REPO, 'src', 'main', 'resources', 'base', 'Plugins', 'Core')
]

from PyQt5.QtCore import QTimer # noqa: E402 (needs the sys.path above)
from PyQt5.QtWidgets import QApplication, QFileIconProvider, QTableView # noqa: E402

_EXTENSIONS = ('txt', 'py', 'jpg', 'pdf', 'md', 'json', 'png', 'zip', 'html')
_TIMEOUT_MS = 60000

def make_tree(root, num_files, num_dirs):
	target = join(root, 'files')
	os.makedirs(target, exist_ok=True)
	for i in range(num_files):
		ext = _EXTENSIONS[i % len(_EXTENSIONS)]
		with open(join(target, 'f%05d.%s' % (i, ext)), 'w') as f:
			f.write('x')
	for i in range(num_dirs):
		os.makedirs(join(target, 'dir%03d' % i), exist_ok=True)
	return target

def make_fs(icon_cache_dir):
	from vitraj.impl.model.icon_provider import IconProvider
	from vitraj.impl.plugins.mother_fs import MotherFileSystem
	from core.fs.local import LocalFileSystem
	import core
	import vitraj.fs
	fs = MotherFileSystem(None)
	fs._icon_provider = IconProvider(QFileIconProvider(), fs, icon_cache_dir)
	vitraj.fs._get_mother_fs = lambda: fs
	fs.add_child('file://', LocalFileSystem())
	for column in (core.Name, core.Size, core.Modified):
		fs.register_column(column.get_qualified_name(), column())
	return fs

class Benchmark:
	def __init__(self, app, fs, target, profiler):
		from vitraj.impl.model import SortedFileSystemModel
		self._app = app
		self._target = target
		self._profiler = profiler
		self._model = SortedFileSystemModel(None, fs, 'file://' + dirname(target))
		self._view = QTableView()
		self._view.setModel(self._model)
		self._view.resize(900, 1200)
		self._view.show()
		self.marks = {}
		self._start = 0
		self._poll_timer = QTimer()
		self._poll_timer.timeout.connect(self._poll)
	def start(self):
		self._poll_timer.start(20)
		self._start = perf_counter()
		if self._profiler:
			self._profiler.enable()
		self._model.set_location('file://' + self._target, callback=self._on_init)
	def _on_init(self):
		self.marks.setdefault('first rows', perf_counter() - self._start)
	def _poll(self):
		model = self._model.sourceModel()
		if model is None or model.get_location() != 'file://' + self._target:
			return
		rows = list(model._rows)
		if not rows or not all(row.is_loaded for row in rows):
			return
		self._poll_timer.stop()
		self.marks['all rows'] = perf_counter() - self._start
		self._scroll(len(rows))
		if self._profiler:
			self._profiler.disable()
		self._app.quit()
	def _scroll(self, num_rows):
		start = perf_counter()
		for i in range(0, num_rows, 40):
			self._view.scrollTo(self._model.index(i, 0))
			self._view.viewport().repaint()
		self.marks['scroll + repaint'] = perf_counter() - start

def main():
	parser = ArgumentParser(description='Benchmark a large directory load.')
	parser.add_argument('--files', type=int, default=5000)
	parser.add_argument('--dirs', type=int, default=200)
	parser.add_argument('--profile', action='store_true')
	args = parser.parse_args()
	root = realpath(mkdtemp(prefix='vitraj-bench-'))
	target = make_tree(root, args.files, args.dirs)
	app = QApplication(sys.argv)
	fs = make_fs(join(root, 'icons'))
	profiler = cProfile.Profile() if args.profile else None
	bench = Benchmark(app, fs, target, profiler)
	QTimer.singleShot(200, bench.start)
	QTimer.singleShot(_TIMEOUT_MS, app.quit)
	app.exec_()
	shutil.rmtree(root, ignore_errors=True)
	for name, seconds in bench.marks.items():
		print('%-18s %6.0f ms' % (name, seconds * 1000))
	if profiler:
		pstats.Stats(profiler).sort_stats('cumulative').print_stats(25)

if __name__ == '__main__':
	main()
