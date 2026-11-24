from vitraj.impl.session import SessionManager
from vitraj.url import as_url
from pathlib import Path
from unittest import TestCase

import sys

class StartOnerrorTest(TestCase):
	def setUp(self):
		self.reported = []
		manager = SessionManager.__new__(SessionManager)
		manager._report_load_error = lambda cmdline, url: \
			self.reported.append(url)
		self.onerror = manager._get_start_onerror(
			None, 'file:///saved', 'file:///home'
		)
		self.root = as_url(Path(sys.executable).anchor)
	def test_saved_location_fails_goes_home_and_reports(self):
		self.assertEqual(
			'file:///home', self.onerror(PermissionError(), 'file:///saved')
		)
		self.assertEqual(['file:///saved'], self.reported)
	def test_home_fails_goes_to_root(self):
		self.assertEqual(
			self.root, self.onerror(FileNotFoundError(), 'file:///home')
		)
	def test_root_fails_stops(self):
		with self.assertLogs('vitraj.impl.session', 'ERROR'):
			self.assertIsNone(self.onerror(OSError(), self.root))
	def test_failing_home_as_start_location_is_reported(self):
		self.onerror(FileNotFoundError(), 'file:///home')
		self.assertEqual(['file:///saved'], self.reported)
	def test_error_is_reported_once(self):
		self.onerror(PermissionError(), 'file:///saved')
		self.onerror(FileNotFoundError(), 'file:///home')
		self.assertEqual(1, len(self.reported))
	def test_already_reported_error_is_not_reported_again(self):
		manager = SessionManager.__new__(SessionManager)
		manager._report_load_error = lambda cmdline, url: \
			self.reported.append(url)
		onerror = manager._get_start_onerror(
			None, 'file:///saved', 'file:///home', already_reported=True
		)
		onerror(FileNotFoundError(), 'file:///home')
		self.assertEqual([], self.reported)
