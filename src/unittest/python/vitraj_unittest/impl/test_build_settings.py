from vitraj.impl.build_settings import load_settings, load_project_settings, \
	filter_public_settings, get_profiles, expand_placeholders
from tempfile import TemporaryDirectory
from unittest import TestCase

import json
import os

class LoadSettingsTest(TestCase):
	def setUp(self):
		self._tmp = TemporaryDirectory()
		self.addCleanup(self._tmp.cleanup)
	def _json(self, name, data):
		p = os.path.join(self._tmp.name, name)
		with open(p, 'w') as f:
			json.dump(data, f)
		return p
	def test_later_file_overrides(self):
		a = self._json('a.json', {'x': 1, 'y': 1})
		b = self._json('b.json', {'y': 2})
		self.assertEqual({'x': 1, 'y': 2}, load_settings([a, b]))
	def test_lists_are_joined(self):
		a = self._json('a.json', {'l': ['a']})
		b = self._json('b.json', {'l': ['b']})
		self.assertEqual(['a', 'b'], load_settings([a, b])['l'])
	def test_dicts_are_merged(self):
		a = self._json('a.json', {'d': {'x': 1}})
		b = self._json('b.json', {'d': {'y': 2}})
		self.assertEqual({'x': 1, 'y': 2}, load_settings([a, b])['d'])
	def test_placeholders_expand_in_chains(self):
		a = self._json('a.json', {
			'name': 'vitraj', 'dir': 'target/${name}', 'x': '${dir}/x'
		})
		result = load_settings([a])
		self.assertEqual('target/vitraj/x', result['x'])
	def test_type_conflict_raises(self):
		a = self._json('a.json', {'l': ['a']})
		b = self._json('b.json', {'l': 'b'})
		with self.assertRaises(ValueError):
			load_settings([a, b])
	def test_base_is_kept(self):
		a = self._json('a.json', {'x': '${project_dir}/x'})
		self.assertEqual('/p/x', load_settings([a], {'project_dir': '/p'})['x'])

class ProjectSettingsTest(TestCase):
	def test_missing_profiles_are_skipped(self):
		with TemporaryDirectory() as project:
			settings_dir = os.path.join(project, 'src', 'build', 'settings')
			os.makedirs(settings_dir)
			with open(os.path.join(settings_dir, 'base.json'), 'w') as f:
				json.dump({'app_name': 'a'}, f)
			result = load_project_settings(project, ['base', 'secret', 'mac'])
		self.assertEqual('a', result['app_name'])
		self.assertEqual(project, result['project_dir'])
	def test_vitraj_public_settings(self):
		public = filter_public_settings(load_project_settings())
		self.assertEqual(
			{'app_name', 'author', 'version', 'environment', 'server_url'},
			set(public)
		)

class ProfilesTest(TestCase):
	def test_release_is_last(self):
		self.assertEqual('release', get_profiles(release=True)[-1])
		self.assertNotIn('release', get_profiles())
	def test_starts_with_base_and_secret(self):
		self.assertEqual(['base', 'secret'], get_profiles()[:2])

class ExpandPlaceholdersTest(TestCase):
	def test_nested(self):
		self.assertEqual(
			{'a': ['x-1']}, expand_placeholders({'a': ['x-${n}']}, {'n': 1})
		)

class ReleaseProfileTest(TestCase):
	def test_release_keeps_mac_info_plist_extra(self):
		# release.json must not replace the TCC keys of mac.json:
		settings = load_project_settings(
			profiles=['base', 'secret', 'mac', 'release']
		)
		self.assertIn('NSDesktopFolderUsageDescription', settings['info_plist_extra'])
		self.assertEqual('production', settings['environment'])
	def test_release_does_not_use_fman_server(self):
		settings = load_project_settings(
			profiles=['base', 'secret', 'mac', 'release']
		)
		self.assertNotIn('fman.io', settings['server_url'])
