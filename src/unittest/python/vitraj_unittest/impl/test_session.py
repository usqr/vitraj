from vitraj.impl.session import SessionManager
from vitraj.impl.util.settings import Settings
from os.path import join
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock

import json

class SessionManagerTest(TestCase):
	def test_on_close_removes_the_old_license_key(self):
		data = self._close_with({'fman_version': '1.7.3', 'is_licensed': False})
		self.assertNotIn('is_licensed', data)
		self.assertEqual('1.7.4', data['fman_version'])
	def test_on_close_without_the_old_license_key(self):
		data = self._close_with({'fman_version': '1.7.3', 'other': 1})
		self.assertNotIn('is_licensed', data)
		self.assertEqual(1, data['other'])
		self.assertEqual('1.7.4', data['fman_version'])
	def setUp(self):
		super().setUp()
		tmp_dir = TemporaryDirectory()
		self.addCleanup(tmp_dir.cleanup)
		self._path = join(tmp_dir.name, 'Session.json')
	def _close_with(self, data):
		with open(self._path, 'w') as f:
			json.dump(data, f)
		manager = SessionManager(
			Settings(self._path), MagicMock(), MagicMock(), '1.7.4'
		)
		manager.on_close(self._main_window())
		with open(self._path, 'r') as f:
			return json.load(f)
	def _main_window(self):
		result = MagicMock()
		result.saveGeometry.return_value = b'geometry'
		result.saveState.return_value = b'state'
		result.get_panes.return_value = []
		return result
