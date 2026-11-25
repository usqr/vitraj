from vitraj.fs import Column
from vitraj.impl.model import Model, Cell
from vitraj.impl.model.model import File, _NOT_LOADED
from vitraj.impl.util.qt.thread import Executor
from vitraj.url import splitscheme
from vitraj_unittest.impl.model import StubFileSystem
from PySide6.QtCore import QObject, Qt, Signal
from random import shuffle
from unittest import TestCase

import random

class ModelRecordFilesTest(TestCase):
	def test_load_file(self):
		f_not_loaded = f('s://a', [c('')], False)
		self._model._record_files([f_not_loaded])
		self._expect_data([('',)])
		f_loaded = f('s://a', [c('a')])
		self._model._record_files([f_loaded])
		self._expect_data([('a',)])
	def test_remove_file(self):
		self._model._record_files([f('s://a', [c('a')])])
		self._expect_data([('a',)])
		self._model._record_files([], ['s://a'])
		self._expect_data([])
	def test_remove_two_files(self):
		self._model._record_files([
			f('s://a', [c('a', 0)]),
			f('s://b', [c('b', 1)])
		])
		self._expect_data([('a',), ('b',)])
		self._model._record_files([], ['s://a', 's://b'])
		self._expect_data([])
	def test_remove_files_gap(self):
		self._model._record_files([
			f('s://a', [c('a', 0)]),
			f('s://b', [c('b', 1)]),
			f('s://c', [c('c', 2)]),
			f('s://d', [c('d', 3)]),
		])
		self._expect_data([('a',), ('b',), ('c',), ('d',)])
		self._model._record_files([], ['s://b', 's://d'])
		self._expect_data([('a',), ('c',)])
	def test_remove_files_out_of_order(self):
		self._model._record_files([
			f('s://a', [c('a', 0)]),
			f('s://b', [c('b', 1)]),
			f('s://c', [c('c', 2)])
		])
		self._expect_data([('a',), ('b',), ('c',)])
		self._model._record_files([], ['s://c', 's://b'])
		self._expect_data([('a',)])
	def test_complex(self):
		e = f('s://e', [c('e', 4)])
		self._model._record_files([
			f('s://a', [c('a', 0)]),
			f('s://b', [c('b', 1)]),
			f('s://d', [c('d', 2)]),
			e
		])
		self._expect_data([('a',), ('b',), ('d',), ('e',)])
		# Simulate e having fallen out of the filter:
		self._model._filters.append(lambda url: url != e.url)
		self._model._record_files([
			f('s://c', [c('c', 3)]),
			f('s://a', [c('a', 5)]),
			e
		], ['s://d'])
		self._expect_data([('b',), ('c',), ('a',)])
	def test_many_moves(self):
		files = [f('s://%d' % i, [c(str(i), i)]) for i in range(5)]
		self._model._record_files(files)
		self._expect_data([(str(i),) for i in range(5)])
		order_after = [4, 0, 3, 2, 1]
		self._model._record_files(
			[f('s://%d' % j, [c(str(j), i)]) for i, j in enumerate(order_after)]
		)
		self._expect_data([(str(i),) for i in order_after])
	def test_reverse(self, num=3):
		files = [f('s://%d' % i, [c(str(i), i)]) for i in range(num)]
		self._model._record_files(files)
		self._expect_data([(str(i),) for i in range(num)])
		new_files = [
			f('s://%d' % i, [c(str(i), j)])
			for j, i in enumerate(reversed(range(num)))
		]
		self._model._record_files(new_files)
		self._expect_data([(str(i),) for i in reversed(range(num))])
	def test_move_last(self):
		files = [f('s://%d' % i, [c(str(i), i)]) for i in range(3)]
		self._model._record_files(files)
		self._expect_data([(str(i),) for i in range(3)])
		order_after = [2, 0, 1]
		self._model._record_files(
			[f('s://%d' % j, [c(str(j), i)]) for i, j in enumerate(order_after)]
		)
		self._expect_data([(str(i),) for i in order_after])
	def test_file_disappeared(self):
		files = [f('s://%d' % i, [c(str(i), i)]) for i in range(4)]
		self._model._record_files(files)
		self._expect_data([(str(i),) for i in range(4)])
		new_files = [
			f('s://3', [c('3', 0)]),
			f('s://0', [c('0', 1)]),
			f('s://2', [c('2', 2)])
		]
		self._model._record_files(new_files, disappeared=['s://1'])
		self._expect_data([('3',), ('0',), ('2',)])
	def test_parent_dir_first_ascending(self):
		self._model._record_files([
			f('s://d/a', [c('a', 0)]),
			f('s://d/..', [c('..', 1)]),
			f('s://d/b', [c('b', 2)])
		])
		self._expect_data([('..',), ('a',), ('b',)])
	def test_parent_dir_inserted_later_ascending(self):
		self._model._record_files([
			f('s://d/a', [c('a', 0)]),
			f('s://d/b', [c('b', 2)])
		])
		self._model._record_files([f('s://d/..', [c('..', 1)])])
		self._expect_data([('..',), ('a',), ('b',)])
	def test_parent_dir_first_descending(self):
		self._set_descending()
		self._model._record_files([
			f('s://d/a', [c_desc('a', 2)]),
			f('s://d/..', [c_desc('..', 1)]),
			f('s://d/b', [c_desc('b', 0)])
		])
		self._expect_data([('..',), ('a',), ('b',)])
	def test_parent_dir_inserted_later_descending(self):
		self._set_descending()
		self._model._record_files([
			f('s://d/a', [c_desc('a', 2)]),
			f('s://d/b', [c_desc('b', 0)])
		])
		self._model._record_files([f('s://d/..', [c_desc('..', 1)])])
		self._expect_data([('..',), ('a',), ('b',)])
	def test_parent_dir_first_when_sort_values_tie(self):
		for descending in (False, True):
			if descending:
				self._set_descending()
			cell = c_desc if descending else c
			self._model._record_files([
				f('s://d/a', [cell('a', 0)]),
				f('s://d/..', [cell('..', 0)]),
				f('s://d/b', [cell('b', 0)])
			])
			# The order of a and b is not defined because their values tie:
			m = self._model
			names = [m.data(m.index(i, 0)) for i in range(m.rowCount())]
			self.assertEqual('..', names[0])
			self.assertEqual({'a', 'b'}, set(names[1:]))
	def test_insert_descending(self):
		self._set_descending()
		self._model._record_files([
			f('s://d/a', [c_desc('a', 2)]),
			f('s://d/c', [c_desc('c', 0)])
		])
		self._model._record_files([f('s://d/b', [c_desc('b', 1)])])
		self._expect_data([('a',), ('b',), ('c',)])
	def test_move_descending(self):
		self._set_descending()
		self._model._record_files([
			f('s://d/a', [c_desc('a', 2)]),
			f('s://d/b', [c_desc('b', 1)]),
			f('s://d/c', [c_desc('c', 0)])
		])
		self._model._record_files([f('s://d/c', [c_desc('c', 3)])])
		self._expect_data([('c',), ('a',), ('b',)])
	def test_parent_dir_first_after_sort_change(self):
		self._model._record_files([
			f('s://d/a', [Cell('a', 0, 2)]),
			f('s://d/..', [Cell('..', 1, 1)]),
			f('s://d/b', [Cell('b', 2, 0)])
		])
		self._expect_data([('..',), ('a',), ('b',)])
		self._model.sort(0, Qt.DescendingOrder)
		self._expect_data([('..',), ('a',), ('b',)])
		self._model.sort(0, Qt.AscendingOrder)
		self._expect_data([('..',), ('a',), ('b',)])
	def test_random(self):
		for num in list(range(6)) + [100]:
			self._test_random(num)
			self.tearDown()
			self.setUp()
	def test_random_descending(self):
		for num in list(range(6)) + [100]:
			self._set_descending()
			self._test_random(num, ascending=False)
			self.tearDown()
			self.setUp()
	def _test_random(self, num=3, ascending=True):
		to_url = lambda i: 's://%d' % i
		from_url = lambda url: int(splitscheme(url)[1])
		# In descending mode, negate the sort value so the rows keep the same
		# expected order as in ascending mode:
		cell = c if ascending else (lambda s, v: c_desc(s, -v))
		files = [f(to_url(i), [cell(str(i), i)]) for i in range(num)]
		self._model._record_files(files)
		self._expect_data([(str(i),) for i in range(num)])
		random_state = random.getstate()
		order = list(range(num))
		shuffle(order)
		filtered_out = {i for i in order if random.random() < .2}
		filter_ = lambda url: from_url(url) not in filtered_out
		disappeared = []
		for index in range(len(order) - 1, -1, -1):
			i = order[index]
			if i not in filtered_out and random.random() < .1:
				order.pop(index)
				disappeared.append(to_url(i))
		new_files = [
			f(to_url(j), [cell(str(j), i)]) for i, j in enumerate(order)
		]
		self._model._filters.append(filter_)
		self._model._record_files(new_files, disappeared)
		message = 'num was %d, random.getstate() was %r' % (num, random_state)
		self._expect_data([
			(str(i),) for i in order if i not in filtered_out
		], message)
	def _set_descending(self):
		self._model = Model(self._fs, 'null://', [Column()], ascending=False)
	def setUp(self):
		super().setUp()
		self._app = StubApp()
		self._executor_before = Executor._INSTANCE # Typically None
		Executor._INSTANCE = Executor(self._app)
		self._fs = StubFileSystem({})
		self._model = Model(self._fs, 'null://', [Column()])
		self.maxDiff = None
	def tearDown(self):
		self._app.aboutToQuit.emit()
		Executor._INSTANCE = self._executor_before
		super().tearDown()
	def _expect_data(self, expected, message=None):
		m = self._model
		actual = [
			tuple(m.data(m.index(i, j)) for j in range(m.columnCount()))
			for i in range(m.rowCount())
		]
		self.assertEqual(expected, actual, message)

def f(url, cells, is_loaded=False, is_dir=False):
	return File(url, None, is_dir, cells, is_loaded)

def c(str_, sort_value_asc=0, sort_value_desc=_NOT_LOADED):
	return Cell(str_, sort_value_asc, sort_value_desc)

def c_desc(str_, sort_value_desc):
	return Cell(str_, _NOT_LOADED, sort_value_desc)

class StubApp(QObject):
	aboutToQuit = Signal()