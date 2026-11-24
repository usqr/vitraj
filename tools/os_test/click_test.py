"""
Close the startup popups of vitraj, then click the file lists.

The SortProbe plugin writes the window layout to a JSON file. This script
reads that file to find the click points. Before each click, the script makes
sure that a click at the click point goes to vitraj. After each click, the
script waits for a state that the probe wrote after the click. It then makes
sure that the click had its result and that no pane changed its folder.

Run the app with an isolated HOME. See README.md.

The script needs a macOS Accessibility permission for the terminal. Without
it, the clicks and the hit test do nothing.
"""

from ApplicationServices import (
	AXUIElementCreateSystemWide, AXUIElementCopyElementAtPosition,
	AXUIElementGetPid
)
from Quartz import (
	CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap,
	kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventMouseMoved,
	kCGMouseButtonLeft
)

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

_STEP_TIMEOUT = 20
# The probe writes every 200 ms. A state that the probe wrote this long after
# the click shows the result of the click:
_SETTLE_SECS = 0.6
# Two clicks nearer than this (in points) can make a double-click:
_SAME_POINT = 10
_MAX_POPUPS = 20

class Failed(Exception):
	pass

def default_state_path():
	return os.path.join(tempfile.gettempdir(), 'vitraj-os-test-state.json')

def read_state(path):
	with open(path) as f:
		state = json.load(f)
	if 'error' in state:
		raise Failed('Probe error: ' + state['error'])
	return state

def wait_for_state(path, timeout):
	deadline = time.time() + timeout
	last_error = 'no attempt'
	while time.time() < deadline:
		try:
			state = read_state(path)
		except (OSError, ValueError, Failed) as e:
			last_error = str(e)
		else:
			if time.time() - state.get('time', 0) < 10:
				return state
			last_error = 'the state file is old'
		time.sleep(0.3)
	raise Failed('No state from the probe plugin: ' + last_error)

def wait_after(path, click_time, done, what, timeout=_STEP_TIMEOUT):
	"""
	Wait for a state that the probe wrote at least _SETTLE_SECS after
	click_time and for which done(state) is True.
	"""
	deadline = time.time() + timeout
	state = None
	while time.time() < deadline:
		try:
			state = read_state(path)
		except (OSError, ValueError):
			state = None
		if state and state['time'] >= click_time + _SETTLE_SECS and done(state):
			return state
		time.sleep(0.1)
	raise Failed('After the click on %s, the expected result did not occur.' % what)

def _process_name(pid):
	result = subprocess.run(
		['ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True
	)
	return result.stdout.strip()

def check_process(pid):
	name = _process_name(pid)
	if not name:
		raise Failed('pid %d is not alive.' % pid)
	# A frozen app runs as 'vitraj'. A source run runs as 'python'.
	if 'vitraj' not in name.lower() and 'python' not in name.lower():
		raise Failed('pid %d is %r, not vitraj.' % (pid, name))
	return name

def pid_at(x, y):
	"""
	Return the pid of the app that gets a click at (x, y), or None.

	Use the Accessibility hit test, not the list of windows. The list of
	windows also contains overlays that do not take clicks, for example the
	full-screen Dock window of macOS 26.
	"""
	error, element = AXUIElementCopyElementAtPosition(
		AXUIElementCreateSystemWide(), x, y, None
	)
	if error:
		return None
	error, pid = AXUIElementGetPid(element, None)
	return None if error else pid

def _post_click(x, y):
	for event_type in (
		kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp
	):
		event = CGEventCreateMouseEvent(
			None, event_type, (x, y), kCGMouseButtonLeft
		)
		CGEventPost(kCGHIDEventTap, event)
		time.sleep(0.04)

def center(rect):
	x, y, width, height = rect
	return x + width // 2, y + height // 2

def contains(outer, rect):
	ox, oy, ow, oh = outer
	x, y, w, h = rect
	return ox <= x and oy <= y and x + w <= ox + ow and y + h <= oy + oh

class Clicker:
	def __init__(self, pid, dry_run, double_click_ms, log):
		self._pid = pid
		self.dry_run = dry_run
		# Wait 1.5 times the double-click time between clicks near one point:
		self._double_click_secs = 1.5 * double_click_ms / 1000
		self._log = log
		self._last = None
	def click(self, rect, label):
		"""Return the time of the click."""
		x, y = center(rect)
		self._check_window(x, y, label)
		if self.dry_run:
			print('  would click %s at (%d, %d)' % (label, x, y))
			return time.time()
		self._wait_for_double_click_time(x, y)
		click_time = time.time()
		_post_click(x, y)
		self._last = (x, y, click_time)
		self._log.append({'click': label, 'x': x, 'y': y, 'time': click_time})
		print('  clicked %s at (%d, %d)' % (label, x, y))
		return click_time
	def _check_window(self, x, y, label):
		owner = pid_at(x, y)
		if owner is None:
			raise Failed('%s: no app gets a click at (%d, %d).' % (label, x, y))
		if owner != self._pid:
			name = os.path.basename(_process_name(owner)) or '?'
			raise Failed(
				'%s: a click at (%d, %d) goes to %s (pid %d), not vitraj.'
				% (label, x, y, name, owner)
			)
	def _wait_for_double_click_time(self, x, y):
		if self._last is None:
			return
		last_x, last_y, last_time = self._last
		if abs(x - last_x) > _SAME_POINT or abs(y - last_y) > _SAME_POINT:
			return
		remaining = last_time + self._double_click_secs - time.time()
		if remaining > 0:
			time.sleep(remaining)

def _plain(text):
	return re.sub(r'<[^>]+>', ' ', text or '')

def _text(popup):
	return ' '.join(_plain(t) for t in popup.get('texts') or [])

def _button(popup, text):
	for button in popup.get('buttons') or []:
		if button['text'].replace('&', '').strip().lower() == text.lower():
			return button
	return None

def _splash_button(popup):
	match = re.search(r'press button ([A-Z])', _text(popup), re.IGNORECASE)
	if not match:
		return None
	return _button(popup, match.group(1))

def popup_step(popup):
	"""Return (kind, button) for a known popup, or (None, None)."""
	name = popup.get('class')
	if name == 'SplashScreen':
		button = _splash_button(popup)
		if button:
			return 'splash', button
	if name == 'Overlay' and _button(popup, 'No'):
		return 'overlay', _button(popup, 'No')
	if popup.get('message_box') and 'extra configuration' in _text(popup):
		button = _button(popup, 'Cancel')
		if button:
			return 'configuration alert', button
	return None, None

def popup_key(popup):
	return popup.get('class'), popup.get('title'), tuple(popup.get('texts') or [])

def drain_popups(path, clicker, state):
	for _ in range(_MAX_POPUPS):
		if not state['popups']:
			return state
		popup = state['popups'][0]
		kind, button = popup_step(popup)
		if kind is None:
			raise Failed(
				'Unknown popup: %s %r %r'
				% (popup.get('class'), popup.get('title'), popup.get('texts'))
			)
		if button['text'].replace('&', '').strip().lower() == 'ok':
			# OK opens a browser on the configuration alert. Never click it.
			raise Failed('The script must not click OK.')
		print('Close popup: %s' % kind)
		label = 'button ' + button['text']
		click_time = clicker.click(button['rect'], label)
		if clicker.dry_run:
			return state
		key = popup_key(popup)
		state = wait_after(
			path, click_time,
			lambda s: key not in map(popup_key, s['popups']), label
		)
	raise Failed('Too many popups.')

def name_header(pane):
	for header in pane['headers']:
		if header['text'].strip().lower() == 'name':
			return header
	return pane['headers'][0] if pane['headers'] else None

def find_pane(state, index):
	for pane in state['panes']:
		if pane['index'] == index:
			return pane
	raise Failed('Pane %d is not in the state file.' % index)

def names(pane):
	return tuple(row['name'] for row in pane['rows'])

def check_urls(state, urls):
	for pane in state['panes']:
		if pane['url'] != urls[pane['index']]:
			raise Failed(
				'Pane %d changed from %r to %r.'
				% (pane['index'], urls[pane['index']], pane['url'])
			)

def parent_row(pane):
	for row in pane['rows']:
		if row['name'] == '..':
			if not contains(pane['viewport'], row['rect']):
				raise Failed('Pane %d: ".." is not visible.' % pane['index'])
			return row
	# Do not click another row: it can be a folder.
	raise Failed('Pane %d has no ".." entry.' % pane['index'])

def sort_pane(path, clicker, state, index, clicks, urls, steps):
	for i in range(clicks):
		pane = find_pane(state, index)
		header = name_header(pane)
		if header is None:
			raise Failed('Pane %d has no header.' % index)
		print('Sort pane %d, click %d' % (index, i + 1))
		before = names(pane)
		click_time = clicker.click(header['rect'], 'header')
		step = {'click': 'header', 'pane': index}
		steps.append(step)
		if clicker.dry_run:
			continue
		state = wait_after(path, click_time, lambda _: True, 'header')
		check_urls(state, urls)
		step['rows_changed'] = names(find_pane(state, index)) != before
		if not step['rows_changed']:
			print('  WARNING: the row order did not change.')
	return state

def click_parent_row(path, clicker, state, index, urls, steps):
	row = parent_row(find_pane(state, index))
	print('Click the ".." entry in pane %d' % index)
	click_time = clicker.click(row['rect'], 'row ..')
	steps.append({'click': 'row ..', 'pane': index})
	if clicker.dry_run:
		return state
	def has_cursor(s):
		rows = find_pane(s, index)['rows']
		return any(r['name'] == '..' and r['current'] for r in rows)
	state = wait_after(path, click_time, has_cursor, 'row ..')
	check_urls(state, urls)
	return state

def run(args, report):
	state = wait_for_state(args.state, args.wait)
	pid = state['pid']
	report['double_click_ms'] = state['double_click_ms']
	print('vitraj: pid %d (%s)' % (pid, check_process(pid)))
	clicker = Clicker(pid, args.dry_run, state['double_click_ms'], report['clicks'])
	state = drain_popups(args.state, clicker, state)
	if not state['panes']:
		raise Failed('No panes in the state file.')
	urls = {pane['index']: pane['url'] for pane in state['panes']}
	indices = sorted(urls)
	for index in indices:
		state = sort_pane(
			args.state, clicker, state, index, args.clicks, urls, report['steps']
		)
	for index in indices:
		state = click_parent_row(
			args.state, clicker, state, index, urls, report['steps']
		)

def parse_args(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--state', default=default_state_path())
	parser.add_argument(
		'--wait', type=int, default=120,
		help='Seconds to wait for the probe plugin.'
	)
	parser.add_argument(
		'--clicks', type=int, default=3, help='Clicks on each Name header.'
	)
	parser.add_argument('--dry-run', action='store_true')
	parser.add_argument('--report', default='os-test-report.json')
	return parser.parse_args(argv)

def main():
	args = parse_args()
	report = {'steps': [], 'clicks': [], 'ok': False}
	try:
		run(args, report)
		report['ok'] = True
		print('All steps passed.')
	except Failed as e:
		report['error'] = str(e)
		print('FAILED: %s' % e)
	finally:
		with open(args.report, 'w') as f:
			json.dump(report, f, indent=2)
	return 0 if report['ok'] else 1

if __name__ == '__main__':
	sys.exit(main())
