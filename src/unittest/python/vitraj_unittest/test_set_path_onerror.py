from vitraj import _set_path_onerror
from unittest import TestCase

class SetPathOnerrorTest(TestCase):
	def test_missing_dir_goes_to_parent(self):
		self.assertEqual('file:///a', self._call(FileNotFoundError(), 'file:///a/b'))
	def test_root_stops(self):
		# dirname('file:///') is 'file://', and dirname('file://') is itself.
		# So from / the chain ends after one more step, without an error:
		self.assertEqual('file://', self._call(FileNotFoundError(), 'file:///'))
		self.assertIsNone(self._call(FileNotFoundError(), 'file://'))
	def test_other_error_raises(self):
		with self.assertRaises(PermissionError):
			self._call(PermissionError(), 'file:///a')
	def _call(self, e, url):
		try:
			raise e
		except Exception as exc:
			return _set_path_onerror(exc, url)
