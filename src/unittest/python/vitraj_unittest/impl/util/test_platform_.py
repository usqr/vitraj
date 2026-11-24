from vitraj.impl.util import platform_
from unittest import TestCase

class NameTest(TestCase):
	def test_windows(self):
		self.assertEqual('Windows', platform_.name('win32'))
		self.assertEqual('Windows', platform_.name('cygwin'))
	def test_mac(self):
		self.assertEqual('Mac', platform_.name('darwin'))
	def test_linux(self):
		self.assertEqual('Linux', platform_.name('linux'))
	def test_unknown_raises(self):
		with self.assertRaises(RuntimeError):
			platform_.name('sunos5')
	def test_current_platform_is_known(self):
		self.assertIn(platform_.name(), ('Windows', 'Mac', 'Linux'))

class DesktopTest(TestCase):
	def test_gnome(self):
		self.assertTrue(platform_.is_gnome_based({'XDG_CURRENT_DESKTOP': 'GNOME'}))
		self.assertTrue(platform_.is_gnome_based({'XDG_CURRENT_DESKTOP': 'X-Cinnamon'}))
		self.assertFalse(platform_.is_gnome_based({}))
	def test_kde(self):
		self.assertTrue(platform_.is_kde_based({'XDG_CURRENT_DESKTOP': 'KDE'}))
		self.assertTrue(platform_.is_kde_based({'GDMSESSION': 'kde-plasma'}))
		self.assertFalse(platform_.is_kde_based({'XDG_CURRENT_DESKTOP': 'GNOME'}))
