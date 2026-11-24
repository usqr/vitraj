from vitraj.impl import app_context_base
from vitraj.impl.app_context_base import ApplicationContext, cached_property
from os.path import realpath
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import os
import sys

class CachedPropertyTest(TestCase):
	def test_computes_once(self):
		calls = []
		class Ctx:
			@cached_property
			def value(self):
				calls.append(1)
				return 42
		ctx = Ctx()
		self.assertEqual(42, ctx.value)
		self.assertEqual(42, ctx.value)
		self.assertEqual([1], calls)

class GetResourceTest(TestCase):
	def test_first_dir_that_has_the_file_wins(self):
		with TemporaryDirectory() as a, TemporaryDirectory() as b:
			open(os.path.join(b, 'x.txt'), 'w').close()
			open(os.path.join(a, 'y.txt'), 'w').close()
			open(os.path.join(b, 'y.txt'), 'w').close()
			ctx = _ctx_with_dirs([a, b])
			self.assertEqual(realpath(os.path.join(b, 'x.txt')), ctx.get_resource('x.txt'))
			self.assertEqual(realpath(os.path.join(a, 'y.txt')), ctx.get_resource('y.txt'))
	def test_missing_raises(self):
		with TemporaryDirectory() as a:
			with self.assertRaises(FileNotFoundError):
				_ctx_with_dirs([a]).get_resource('nope')

class GetApplicationContextTest(TestCase):
	def setUp(self):
		self._before = app_context_base._APPLICATION_CONTEXT
		app_context_base._APPLICATION_CONTEXT = None
	def tearDown(self):
		app_context_base._APPLICATION_CONTEXT = self._before
	def test_source_uses_development_class(self):
		result = app_context_base.get_application_context(_Dev, _Frozen)
		self.assertIsInstance(result, _Dev)
		self.assertNotIsInstance(result, _Frozen)
	def test_frozen_uses_frozen_class(self):
		with patch.object(sys, 'frozen', True, create=True):
			result = app_context_base.get_application_context(_Dev, _Frozen)
		self.assertIsInstance(result, _Frozen)
	def test_returns_same_instance(self):
		first = app_context_base.get_application_context(_Dev)
		self.assertIs(first, app_context_base.get_application_context(_Dev))

class FbsBuildAdapterTest(TestCase):
	def test_source_settings_have_version_and_app_name(self):
		from vitraj.impl.fbs_build import load_build_settings
		settings = load_build_settings()
		self.assertIn('version', settings)
		self.assertEqual('vitraj', settings['app_name'])
	def test_source_resource_dirs_start_with_base(self):
		from vitraj.impl.fbs_build import get_source_resource_dirs
		dirs = get_source_resource_dirs()
		self.assertTrue(dirs[0].endswith(os.path.join('resources', 'base')))

class _Dev:
	pass

class _Frozen(_Dev):
	pass

def _ctx_with_dirs(dirs):
	# Do not call __init__: it would make a QApplication.
	class Ctx(ApplicationContext):
		_resource_dirs = dirs
	return Ctx.__new__(Ctx)
