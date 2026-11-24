from vitraj.impl.util.settings import Settings
from os.path import join
from tempfile import TemporaryDirectory
from unittest import TestCase

import json

class SettingsTest(TestCase):
	def test_pop_removes_the_key(self):
		self._write({'a': 1, 'b': 2})
		settings = Settings(self._path)
		self.assertEqual(1, settings.pop('a'))
		settings.flush()
		self.assertEqual({'b': 2}, self._read())
	def test_pop_nonexistent_key(self):
		settings = Settings(self._path)
		self.assertIsNone(settings.pop('a'))
		self.assertEqual(3, settings.pop('a', 3))
	def setUp(self):
		super().setUp()
		tmp_dir = TemporaryDirectory()
		self.addCleanup(tmp_dir.cleanup)
		self._path = join(tmp_dir.name, 'Settings.json')
	def _write(self, data):
		with open(self._path, 'w') as f:
			json.dump(data, f)
	def _read(self):
		with open(self._path, 'r') as f:
			return json.load(f)
