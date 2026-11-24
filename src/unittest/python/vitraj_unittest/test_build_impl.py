from os.path import dirname, join
from tempfile import TemporaryDirectory
from unittest import TestCase

import json
import os
import stat
import sys

_BUILD_PYTHON = join(dirname(__file__), '..', '..', '..', 'build', 'python')
if _BUILD_PYTHON not in sys.path:
	sys.path.append(_BUILD_PYTHON)

from build_impl import freeze, settings # noqa: E402
from build_impl.settings import SETTINGS # noqa: E402

class _SettingsTestCase(TestCase):
	def setUp(self):
		self._before = dict(SETTINGS)
		self.addCleanup(self._restore)
	def _restore(self):
		SETTINGS.clear()
		SETTINGS.update(self._before)

class PathTest(_SettingsTestCase):
	def test_expands_placeholders(self):
		settings.init()
		self.assertTrue(settings.path('${freeze_dir}').endswith(
			join('target', 'vitraj.app' if sys.platform == 'darwin' else 'vitraj')
		))

class AbsolutePathTest(_SettingsTestCase):
	def test_absolute_path_stays(self):
		with TemporaryDirectory() as tmp:
			self.assertEqual(os.path.normpath(tmp), settings.path(tmp))

class CopyWithFilteringTest(_SettingsTestCase):
	def test_filters_only_listed_files_and_keeps_mode(self):
		with TemporaryDirectory() as src, TemporaryDirectory() as dest:
			listed = join(src, 'bin', 'launcher')
			os.makedirs(dirname(listed))
			with open(listed, 'w') as f:
				f.write('exec ${app_name}')
			os.chmod(listed, 0o755)
			other = join(src, 'other.txt')
			with open(other, 'w') as f:
				f.write('${app_name}')
			os.makedirs(join(src, '__pycache__'))
			open(join(src, '__pycache__', 'x.pyc'), 'w').close()
			SETTINGS.clear()
			SETTINGS.update({'app_name': 'vitraj', 'files_to_filter': [listed]})
			freeze.copy_with_filtering(src, dest)
			with open(join(dest, 'bin', 'launcher')) as f:
				self.assertEqual('exec vitraj', f.read())
			with open(join(dest, 'other.txt')) as f:
				self.assertEqual('${app_name}', f.read())
			mode = os.stat(join(dest, 'bin', 'launcher')).st_mode
			self.assertTrue(mode & stat.S_IXUSR)
			self.assertFalse(os.path.exists(join(dest, '__pycache__')))
	def test_missing_source_does_nothing(self):
		with TemporaryDirectory() as dest:
			freeze.copy_with_filtering(join(dest, 'nope'), dest)
			self.assertEqual([], os.listdir(dest))

class WriteBuildSettingsTest(_SettingsTestCase):
	def test_writes_only_public_settings(self):
		SETTINGS.clear()
		SETTINGS.update({
			'version': '1.0', 'secret': 'x', 'public_settings': ['version']
		})
		with TemporaryDirectory() as dest:
			freeze.write_build_settings(dest)
			with open(join(dest, 'build_settings.json')) as f:
				self.assertEqual({'version': '1.0'}, json.load(f))

class CommandsTest(TestCase):
	def test_has_the_workflow_commands(self):
		from build_impl.commands import get_commands
		names = set(get_commands())
		self.assertLessEqual({'run', 'test', 'clean', 'freeze', 'release'}, names)
		if sys.platform == 'darwin':
			self.assertLessEqual({'sign', 'sign_installer'}, names)

class MacIconsTest(_SettingsTestCase):
	def test_mac_icons_override_base(self):
		if sys.platform != 'darwin':
			self.skipTest('macOS only')
		from build_impl.mac import _get_icons
		settings.init()
		icons = _get_icons()
		self.assertIn((1024, 1), icons)
		self.assertIn((16, 1), icons)
		self.assertIn(join('icons', 'mac'), icons[(128, 1)])
