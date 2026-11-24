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
		'kCGEventLeftMouseDown', 'kCGEventLeftMouseUp', 'kCGEventMouseMoved',
		'kCGMouseButtonLeft'
	):
		setattr(quartz, name, 0)
	return quartz

def _stub_application_services():
	result = ModuleType('ApplicationServices')
	for name in (
		'AXUIElementCreateSystemWide', 'AXUIElementCopyElementAtPosition',
		'AXUIElementGetPid'
	):
		setattr(result, name, None)
	return result

_STUBS = {
	'Quartz': _stub_quartz(),
	'ApplicationServices': _stub_application_services()
}
with patch.dict(sys.modules, _STUBS):
	sys.path.insert(0, os.path.dirname(__file__))
	import click_test as ct

def _button(text, rect=(0, 0, 10, 10)):
	return {'text': text, 'rect': list(rect)}

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
	def test_unknown_popup(self):
		popup = {'class': 'QDialog', 'buttons': [_button('OK')]}
		self.assertEqual((None, None), ct.popup_step(popup))

class PidAtTest(TestCase):
	def _hit(self, element_error, pid_error=0, pid=42):
		self.calls = []
		def copy_element(*args):
			self.calls.append(('copy', args))
			return element_error, 'element'
		def get_pid(*args):
			self.calls.append(('pid', args))
			return pid_error, pid
		with patch.object(ct, 'AXUIElementCreateSystemWide', lambda: 'system'), \
				patch.object(ct, 'AXUIElementCopyElementAtPosition', copy_element), \
				patch.object(ct, 'AXUIElementGetPid', get_pid):
			return ct.pid_at(10, 20)
	def test_returns_the_pid_of_the_element(self):
		self.assertEqual(42, self._hit(0))
		self.assertEqual(
			[('copy', ('system', 10, 20, None)), ('pid', ('element', None))],
			self.calls
		)
	def test_fails_if_no_element(self):
		with self.assertRaisesRegex(ct.Failed, 'AXError -25204'):
			self._hit(-25204)
	def test_fails_if_no_pid(self):
		with self.assertRaisesRegex(ct.Failed, 'AXError -25202'):
			self._hit(0, pid_error=-25202)
	def test_names_the_missing_permission(self):
		with self.assertRaisesRegex(ct.Failed, 'no Accessibility permission'):
			self._hit(-25211)

class CheckWindowTest(TestCase):
	def _check(self, owner, name='/System/Dock'):
		clicker = ct.Clicker(7, False, 500, [])
		with patch.object(ct, 'pid_at', owner), \
				patch.object(ct, '_process_name', lambda pid: name):
			clicker._check_window(1, 2, 'button')
	def test_passes_if_vitraj_gets_the_click(self):
		self._check(lambda x, y: 7)
	def test_fails_if_another_app_gets_the_click(self):
		with self.assertRaisesRegex(ct.Failed, 'goes to Dock'):
			self._check(lambda x, y: 99)
	def test_unknown_name_if_the_other_app_exited(self):
		with self.assertRaisesRegex(ct.Failed, r'goes to \? \(pid 99\)'):
			self._check(lambda x, y: 99, name='')
	def test_adds_the_label_if_the_hit_test_fails(self):
		def fail(x, y):
			raise ct.Failed('The hit test failed.')
		with self.assertRaisesRegex(ct.Failed, '^button: The hit test failed'):
			self._check(fail)

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
