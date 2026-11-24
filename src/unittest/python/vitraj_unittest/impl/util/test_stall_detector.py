from vitraj.impl.util.stall_detector import get_threshold_ms, StallTracker, \
	format_stack, ENV_VAR
from threading import get_ident
from unittest import TestCase

import sys

class GetThresholdMsTest(TestCase):
	def test_off_by_default(self):
		self.assertIsNone(get_threshold_ms({}))
	def test_value(self):
		self.assertEqual(150, get_threshold_ms({ENV_VAR: '150'}))
	def test_invalid_value(self):
		self.assertIsNone(get_threshold_ms({ENV_VAR: 'abc'}))
	def test_zero_is_off(self):
		self.assertIsNone(get_threshold_ms({ENV_VAR: '0'}))

class StallTrackerTest(TestCase):
	def setUp(self):
		self.now = 0.0
		self.tracker = StallTracker(.1, clock=lambda: self.now)
	def test_no_stall(self):
		self.now = .05
		self.assertIsNone(self.tracker.check())
	def test_stall_reported(self):
		self.now = .25
		self.assertAlmostEqual(.25, self.tracker.check())
	def test_stall_reported_once(self):
		self.now = .25
		self.tracker.check()
		self.now = .5
		self.assertIsNone(self.tracker.check())
	def test_new_stall_after_heartbeat(self):
		self.now = .25
		self.tracker.check()
		self.tracker.heartbeat()
		self.now = .4
		self.assertAlmostEqual(.15, self.tracker.check())
	def test_heartbeat_resets(self):
		self.now = .09
		self.tracker.heartbeat()
		self.now = .15
		self.assertIsNone(self.tracker.check())

class FormatStackTest(TestCase):
	def test_current_thread(self):
		stack = format_stack(get_ident(), sys._current_frames())
		self.assertIn('test_current_thread', stack)
	def test_unknown_thread(self):
		self.assertEqual('(no stack available)', format_stack(-1, {}))
