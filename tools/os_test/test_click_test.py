"""
Tests for the pure helpers of click_test.py. They need no GUI and no pyobjc:

    python -m unittest discover -s tools/os_test
"""

from types import ModuleType
from unittest import TestCase
from unittest.mock import patch

import json
import os
import sys
import tempfile
import time

def _stub_quartz():
	quartz = ModuleType('Quartz')
	for name in (
		'CGEventCreateMouseEvent', 'CGEventPost', 'kCGHIDEventTap',
		'CGWindowListCopyWindowInfo', 'kCGWindowListOptionOnScreenOnly',
		'kCGWindowListExcludeDesktopElements', 'kCGNullWindowID',
		'kCGEventLeftMouseDown', 'kCGEventLeftMouseUp', 'kCGEventMouseMoved',
		'kCGMouseButtonLeft'
	):
		setattr(quartz, name, 0)
	return quartz

with patch.dict(sys.modules, {'Quartz': _stub_quartz()}):
	sys.path.insert(0, os.path.dirname(__file__))
	import click_test as ct

def _button(text, rect=(0, 0, 10, 10)):
	return {'text': text, 'rect': list(rect)}

def _window(pid, x, y, width, height, alpha=1):
	return {
		'kCGWindowOwnerPID': pid, 'kCGWindowAlpha': alpha,
		'kCGWindowBounds': {'X': x, 'Y': y, 'Width': width, 'Height': height}
	}

def _row(name, rect=(0, 20, 100, 20)):
	return {'name': name, 'rect': list(rect)}

class PopupStepTest(TestCase):
	def test_overlay_gives_no(self):
		popup = {'class': 'Overlay', 'buttons': [_button('No'), _button('Yes')]}
		self.assertEqual(('overlay', _button('No')), ct.popup_step(popup))
	def test_configuration_alert_gives_cancel_not_ok(self):
		popup = {
			'class': 'QMessageBox', 'message_box': True,
			'texts': ['On macOS, fman requires extra configuration.<br/>'],
			'buttons': [_button('OK'), _button('&Cancel')]
		}
		kind, button = ct.popup_step(popup)
		self.assertEqual('configuration alert', kind)
		self.assertEqual('&Cancel', button['text'])
	def test_splash_screen_gives_the_named_button(self):
		popup = {
			'class': 'SplashScreen',
			'texts': ['<p>To continue, <b>press button B</b>.</p>'],
			'buttons': [_button('A'), _button('B'), _button('C')]
		}
		self.assertEqual(('splash', _button('B')), ct.popup_step(popup))
	def test_unknown_popup(self):
		popup = {'class': 'QDialog', 'buttons': [_button('OK')]}
		self.assertEqual((None, None), ct.popup_step(popup))

class FrontmostWindowAtTest(TestCase):
	def test_returns_the_first_window_that_contains_the_point(self):
		dialog = _window(99, 50, 50, 100, 100)
		main = _window(1, 0, 0, 500, 500)
		self.assertIs(dialog, ct.frontmost_window_at([dialog, main], 60, 60))
		self.assertIs(main, ct.frontmost_window_at([dialog, main], 10, 10))
	def test_ignores_transparent_windows(self):
		invisible = _window(99, 0, 0, 500, 500, alpha=0)
		main = _window(1, 0, 0, 500, 500)
		self.assertIs(main, ct.frontmost_window_at([invisible, main], 10, 10))
	def test_none_outside_of_all_windows(self):
		self.assertIsNone(ct.frontmost_window_at([_window(1, 0, 0, 5, 5)], 9, 9))

class ParentRowTest(TestCase):
	def _pane(self, rows):
		return {'index': 0, 'viewport': [0, 20, 100, 100], 'rows': rows}
	def test_finds_the_parent_row(self):
		row = _row('..')
		self.assertIs(row, ct.parent_row(self._pane([_row('zeta'), row])))
	def test_fails_without_parent_row(self):
		# It must not click 'zeta' in place of '..':
		with self.assertRaises(ct.Failed):
			ct.parent_row(self._pane([_row('zeta')]))
	def test_fails_if_parent_row_is_scrolled_out_of_view(self):
		with self.assertRaises(ct.Failed):
			ct.parent_row(self._pane([_row('..', rect=(0, 0, 100, 20))]))

class HelpersTest(TestCase):
	def test_center(self):
		self.assertEqual((15, 30), ct.center([10, 20, 10, 20]))
	def test_name_header_falls_back_to_first_section(self):
		size = {'text': 'Size', 'rect': [0, 0, 1, 1]}
		self.assertIs(size, ct.name_header({'headers': [size]}))
		name = {'text': 'Name', 'rect': [0, 0, 1, 1]}
		self.assertIs(name, ct.name_header({'headers': [size, name]}))
	def test_check_urls(self):
		state = {'panes': [{'index': 0, 'url': 'file:///a'}]}
		ct.check_urls(state, {0: 'file:///a'})
		with self.assertRaises(ct.Failed):
			ct.check_urls(state, {0: 'file:///b'})

class StateFileTest(TestCase):
	def setUp(self):
		fd, self.path = tempfile.mkstemp(suffix='.json')
		os.close(fd)
	def tearDown(self):
		os.remove(self.path)
	def _write(self, state):
		with open(self.path, 'w') as f:
			json.dump(state, f)
	def test_probe_error_is_a_failure(self):
		self._write({'pid': 1, 'error': 'boom'})
		with self.assertRaises(ct.Failed):
			ct.read_state(self.path)
	def test_wait_after_ignores_states_from_before_the_click(self):
		click_time = time.time()
		self._write({'time': click_time - 1, 'panes': [], 'popups': []})
		with self.assertRaises(ct.Failed):
			ct.wait_after(self.path, click_time, lambda _: True, 'x', timeout=0.3)
	def test_wait_after_returns_a_new_state_with_the_result(self):
		click_time = time.time() - 10
		self._write({'time': time.time(), 'panes': [], 'popups': []})
		state = ct.wait_after(
			self.path, click_time, lambda s: s['popups'] == [], 'x', timeout=1
		)
		self.assertEqual([], state['popups'])

class ClickerTest(TestCase):
	def test_waits_for_the_double_click_time_at_the_same_point(self):
		clicker = ct.Clicker(1, False, 500, [])
		clicker._last = (10, 10, time.time())
		with patch.object(ct.time, 'sleep') as sleep:
			clicker._wait_for_double_click_time(12, 12)
		self.assertGreater(sleep.call_args[0][0], 0.6)
	def test_does_not_wait_at_a_different_point(self):
		clicker = ct.Clicker(1, False, 500, [])
		clicker._last = (10, 10, time.time())
		with patch.object(ct.time, 'sleep') as sleep:
			clicker._wait_for_double_click_time(100, 10)
		sleep.assert_not_called()
