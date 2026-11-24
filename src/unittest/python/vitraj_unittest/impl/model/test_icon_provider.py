from vitraj.impl.model.icon_provider import IconProvider
from tempfile import TemporaryDirectory
from unittest import TestCase

class LocalIconCacheTest(TestCase):
	def setUp(self):
		self._tmp = TemporaryDirectory()
		self.qt = _StubQtIconProvider()
		self.fs = _StubFs(dirs={'file:///d/folder'})
		self.provider = IconProvider(self.qt, self.fs, self._tmp.name)
		self.qt.requested.clear()
	def tearDown(self):
		self._tmp.cleanup()
	def test_same_extension_shares_icon(self):
		a = self.provider.get_icon('file:///d/a.txt')
		b = self.provider.get_icon('file:///d/b.TXT')
		self.assertIs(a, b)
		self.assertEqual(['/d/a.txt'], self.qt.requested)
	def test_different_extensions_do_not_share(self):
		self.provider.get_icon('file:///d/a.txt')
		self.provider.get_icon('file:///d/a.pdf')
		self.assertEqual(['/d/a.txt', '/d/a.pdf'], self.qt.requested)
	def test_folder_gets_own_icon(self):
		self.provider.get_icon('file:///d/folder')
		self.provider.get_icon('file:///d/folder')
		self.assertEqual(['/d/folder'] * 2, self.qt.requested)
	def test_no_extension_gets_own_icon(self):
		self.provider.get_icon('file:///d/run')
		self.provider.get_icon('file:///d/run')
		self.assertEqual(2, len(self.qt.requested))
	def test_exe_gets_own_icon(self):
		self.provider.get_icon('file:///d/a.exe')
		self.provider.get_icon('file:///d/b.exe')
		self.assertEqual(['/d/a.exe', '/d/b.exe'], self.qt.requested)
	def test_missing_file_raises(self):
		self.fs.missing.add('file:///d/gone.txt')
		with self.assertRaises(FileNotFoundError):
			self.provider.get_icon('file:///d/gone.txt')

class _StubQtIconProvider:
	def __init__(self):
		self.requested = []
	def icon(self, file_info):
		self.requested.append(file_info.filePath())
		return object()

class _StubFs:
	def __init__(self, dirs):
		self._dirs = dirs
		self.missing = set()
	def is_dir(self, url):
		if url in self.missing:
			raise FileNotFoundError(url)
		return url in self._dirs
