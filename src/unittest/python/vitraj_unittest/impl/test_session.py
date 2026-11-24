from vitraj.impl.session import SessionManager
from vitraj.impl.util.settings import Settings
from os.path import join
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock

import json

class SessionManagerTest(TestCase):
	def test_on_close_removes_the_old_license_key(self):
		with open(self._path, 'w') as f:
			json.dump({'fman_version': '1.7.3', 'is_licensed': False}, f)
		manager = SessionManager(
			Settings(self._path), MagicMock(), MagicMock(), '1.7.4'
		)
		manager.on_close(self._main_window())
		with open(self._path, 'r') as f:
			data = json.load(f)
		self.assertNotIn('is_licensed', data)
		self.assertEqual('1.7.4', data['fman_version'])
	def setUp(self):
		super().setUp()
		self._tmp_dir = TemporaryDirectory()
		self._path = join(self._tmp_dir.name, 'Session.json')
	def tearDown(self):
		self._tmp_dir.cleanup()
		super().tearDown()
	def _main_window(self):
		result = MagicMock()
		result.saveGeometry.return_value = b'geometry'
		result.saveState.return_value = b'state'
		result.get_panes.return_value = []
		return result
