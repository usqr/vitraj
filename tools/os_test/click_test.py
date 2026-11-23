"""
Close the startup popups of vitraj, then click the file lists.

The SortProbe plugin writes the window layout to a JSON file. This script
reads that file to find the click points. Before each click, the script makes
sure that the window below the click point belongs to vitraj. After each
click, the script makes sure that no pane changed its folder.

Run the app with an isolated HOME. See README.md.

The script needs a macOS Accessibility permission for the terminal.
"""

from Quartz import (
	CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap,
	CGWindowListCopyWindowInfo,
	kCGWindowListOptionOnScreenOnly, kCGWindowListExcludeDesktopElements,
	kCGNullWindowID, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
	kCGEventMouseMoved, kCGMouseButtonLeft
)

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

_POPUP_TIMEOUT = 20
_SETTLE_SECS = 0.6
_STEP_SECS = 0.8

class Failed(Exception):
	pass

def default_state_path():
	return os.path.join(
		tempfile.gettempdir(), 'vitraj-os-test-state.json'
	)

def read_state(path):
	with open(path) as f:
		return json.load(f)

def wait_for_state(path, timeout):
	deadline = time.time() + timeout
	last_error = 'no attempt'
	while time.time() < deadline:
		try:
			state = read_state(path)
		except (OSError, ValueError) as e:
			last_error = str(e)
		else:
			if 'error' in state:
				last_error = 'probe error: ' + state['error']
			elif time.time() - state.get('time', 0) < 10:
				return state
			else:
				last_error = 'the state file is old'
		time.sleep(0.3)
	raise Failed('No state from the probe plugin: ' + last_error)

def wait_for_change(path, previous, timeout=_POPUP_TIMEOUT):
	deadline = time.time() + timeout
	while time.time() < deadline:
		state = read_state(path)
		if (state.get('time'), len(state.get('panes', []))) != previous:
			time.sleep(_SETTLE_SECS)
			return read_state(path)
		time.sleep(0.2)
	raise Failed('The probe did not write a new state.')

def check_process(pid):
	result = subprocess.run(
		['ps', '-p', str(pid), '-o', 'comm='],
		capture_output=True, text=True
	)
	name = result.stdout.strip()
	if not name:
		raise Failed('pid %d is not alive.' % pid)
	# A frozen app runs as 'vitraj'. A source run runs as 'python'.
	if 'vitraj' not in name.lower() and 'python' not in name.lower():
		raise Failed('pid %d is %r, not vitraj.' % (pid, name))
	return name

def window_at(x, y):
	windows = CGWindowListCopyWindowInfo(
		kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
		kCGNullWindowID
	)
	for window in windows:
		if window.get('kCGWindowLayer', 0) != 0:
			continue
		bounds = window.get('kCGWindowBounds')
		if not bounds:
			continue
		left, top = bounds['X'], bounds['Y']
		if left <= x < left + bounds['Width'] and \
				top <= y < top + bounds['Height']:
			return window
	return None

def click(x, y):
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

def click_rect(rect, pid, label, dry_run):
	x, y = center(rect)
	window = window_at(x, y)
	if window is None:
		raise Failed('%s: no window at (%d, %d).' % (label, x, y))
	owner = window.get('kCGWindowOwnerPID')
	if owner != pid:
		raise Failed(
			'%s: the window at (%d, %d) belongs to pid %s, not %s.'
			% (label, x, y, owner, pid)
		)
	if dry_run:
		print('  would click %s at (%d, %d)' % (label, x, y))
	else:
		click(x, y)
		print('  clicked %s at (%d, %d)' % (label, x, y))

def _plain(text):
	return re.sub(r'<[^>]+>', ' ', text or '')

def _button(popup, text):
	for button in popup.get('buttons') or []:
		if button['text'].strip().lower() == text.lower():
			return button
	return None

def _splash_button(popup):
	text = ' '.join(_plain(t) for t in popup.get('texts') or [])
	match = re.search(r'press button ([A-Z])', text, re.IGNORECASE)
	if not match:
		return None
	return _button(popup, match.group(1))

def popup_step(popup):
	name = popup.get('class')
	text = ' '.join(_plain(t) for t in popup.get('texts') or [])
	if name == 'SplashScreen':
		button = _splash_button(popup)
		if button:
			return 'splash', button
	if name == 'Overlay' and _button(popup, 'No'):
		return 'overlay', _button(popup, 'No')
	if popup.get('message_box') and 'extra configuration' in text:
		button = _button(popup, 'Cancel')
		if button:
			return 'configuration alert', button
	return None, None

def drain_popups(path, pid, dry_run):
	state = read_state(path)
	seen = 0
	while state.get('popups'):
		popup = state['popups'][0]
		kind, button = popup_step(popup)
		if kind is None:
			raise Failed(
				'Unknown popup: %s %r %r'
				% (popup.get('class'), popup.get('title'), popup.get('texts'))
			)
		if button['text'].strip().lower() == 'ok':
			# OK opens a browser on the configuration alert. Never click it.
			raise Failed('The script must not click OK.')
		print('Close popup: %s' % kind)
		click_rect(button['rect'], pid, 'button ' + button['text'], dry_run)
		if dry_run:
			return state
		seen += 1
		state = wait_for_change(path, (state.get('time'), len(state['panes'])))
		if seen > 20:
			raise Failed('Too many popups.')
	return state

def name_header(pane):
	for header in pane['headers']:
		if header['text'].strip().lower() == 'name':
			return header
	return pane['headers'][0] if pane['headers'] else None

def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--state', default=default_state_path())
	parser.add_argument(
		'--wait', type=int, default=120,
		help='Seconds to wait for the probe plugin.'
	)
	parser.add_argument(
		'--clicks', type=int, default=3,
		help='Clicks on each Name header.'
	)
	parser.add_argument('--dry-run', action='store_true')
	parser.add_argument('--report', default='os-test-report.json')
	args = parser.parse_args()

	report = {'steps': [], 'ok': False}
	try:
		state = wait_for_state(args.state, args.wait)
		pid = state['pid']
		print('vitraj: pid %d (%s)' % (pid, check_process(pid)))
		state = drain_popups(args.state, pid, args.dry_run)
		if not state['panes']:
			raise Failed('No panes in the state file.')
		urls = {pane['index']: pane['url'] for pane in state['panes']}
		for pane in state['panes']:
			header = name_header(pane)
			if header is None:
				raise Failed('Pane %d has no header.' % pane['index'])
			names = _names(pane)
			for i in range(args.clicks):
				print('Sort pane %d, click %d' % (pane['index'], i + 1))
				click_rect(header['rect'], pid, 'header', args.dry_run)
				step = {'click': 'header', 'pane': pane['index'], 'ok': True}
				report['steps'].append(step)
				if args.dry_run:
					continue
				state = wait_for_change(
					args.state, (state.get('time'), len(state['panes']))
				)
				_check_urls(state, urls)
				pane = _pane(state, pane['index'])
				new_names = _names(pane)
				step['rows_changed'] = names != new_names
				if not step['rows_changed']:
					print('  WARNING: the row order did not change.')
				names = new_names
				header = name_header(pane)
		for pane in state['panes']:
			rows = [r for r in pane['rows'] if r['name'] == '..']
			rows = rows or pane['rows'][:1]
			if not rows:
				continue
			print('Click the ".." entry in pane %d' % pane['index'])
			click_rect(rows[0]['rect'], pid, 'row', args.dry_run)
			report['steps'].append(
				{'click': 'row', 'pane': pane['index'], 'ok': True}
			)
			if args.dry_run:
				continue
			state = wait_for_change(
				args.state, (state.get('time'), len(state['panes']))
			)
			_check_urls(state, urls)
		report['ok'] = True
		print('All steps passed.')
	except Failed as e:
		report['error'] = str(e)
		print('FAILED: %s' % e)
	finally:
		with open(args.report, 'w') as f:
			json.dump(report, f, indent=2)
	return 0 if report['ok'] else 1

def _pane(state, index):
	for pane in state['panes']:
		if pane['index'] == index:
			return pane
	raise Failed('Pane %d is not in the state file.' % index)

def _names(pane):
	return tuple(row['name'] for row in pane['rows'])

def _check_urls(state, urls):
	for pane in state['panes']:
		if pane['url'] != urls[pane['index']]:
			raise Failed(
				'Pane %d changed from %r to %r.'
				% (pane['index'], urls[pane['index']], pane['url'])
			)

if __name__ == '__main__':
	sys.exit(main())
