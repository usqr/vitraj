"""
Logs a stack trace of the main thread when its event loop is blocked for
longer than a threshold. It is off by default. To turn it on, set the
environment variable VITRAJ_STALL_MS, for example VITRAJ_STALL_MS=100.
"""
from PySide6.QtCore import QTimer
from threading import Thread, get_ident
from time import monotonic, sleep

import logging
import os
import sys
import traceback

_LOG = logging.getLogger(__name__)

ENV_VAR = 'VITRAJ_STALL_MS'

def get_threshold_ms(environ=None):
	"""Return the threshold in ms, or None when the detector is off."""
	value = (os.environ if environ is None else environ).get(ENV_VAR, '')
	try:
		result = int(value)
	except ValueError:
		return None
	return result if result > 0 else None

class StallTracker:
	"""
	The logic of the detector, without threads or Qt. The main thread calls
	#heartbeat(). The watchdog calls #check(). #check() returns the stall
	duration once for each stall, and None at all other times.
	"""
	def __init__(self, threshold_s, clock=monotonic):
		self._threshold_s = threshold_s
		self._clock = clock
		self._last_beat = clock()
		self._reported_beat = None
	def heartbeat(self):
		self._last_beat = self._clock()
	def check(self):
		last_beat = self._last_beat
		duration = self._clock() - last_beat
		if duration < self._threshold_s or self._reported_beat == last_beat:
			return None
		self._reported_beat = last_beat
		return duration

def format_stack(thread_id, frames=None):
	if frames is None:
		frames = sys._current_frames()
	frame = frames.get(thread_id)
	if frame is None:
		return '(no stack available)'
	return ''.join(traceback.format_stack(frame))

class StallDetector:
	def __init__(self, threshold_ms, log=_LOG):
		self._tracker = StallTracker(threshold_ms / 1000)
		self._interval_s = threshold_ms / 4000
		self._log = log
		self._main_thread_id = get_ident()
		self._timer = None
	def start(self):
		"""Call this from the main thread, after the QApplication exists."""
		self._timer = QTimer()
		self._timer.timeout.connect(self._tracker.heartbeat)
		self._timer.start(max(1, int(self._interval_s * 1000)))
		Thread(target=self._watch, daemon=True, name='StallDetector').start()
	def _watch(self):
		while True:
			sleep(self._interval_s)
			duration = self._tracker.check()
			if duration is not None:
				self._log.warning(
					'Main thread blocked for %d ms:\n%s', duration * 1000,
					format_stack(self._main_thread_id)
				)

def start_if_enabled():
	threshold_ms = get_threshold_ms()
	if threshold_ms is None:
		return None
	result = StallDetector(threshold_ms)
	result.start()
	_LOG.warning('Stall detector is on (threshold: %d ms)', threshold_ms)
	return result
