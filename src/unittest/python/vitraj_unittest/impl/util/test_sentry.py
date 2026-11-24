from functools import partial
from sentry_sdk.transport import Transport
from threading import Thread
from vitraj.impl.util.sentry import SentryExceptionHandler
from unittest import TestCase
from unittest.mock import patch

import sentry_sdk
import sys

class SentryExceptionHandlerTest(TestCase):
	def test_init_gives_global_scope_and_calls_callback(self):
		calls = []
		handler = SentryExceptionHandler(
			None, '1.2.3', 'test', callback=lambda: calls.append(handler.scope)
		)
		handler.init()
		self.assertIs(sentry_sdk.get_global_scope(), handler.scope)
		self.assertEqual([handler.scope], calls)
	def test_context_goes_with_events_of_all_threads(self):
		events = []
		handler = self._init_with_stub_transport(events)
		handler.scope.set_extra('os_name', 'Mac')
		handler.scope.set_user({'id': 41})
		exc_info = _get_exc_info()
		worker = Thread(target=handler.handle, args=exc_info)
		worker.start()
		worker.join()
		handler.handle(*exc_info)
		sentry_sdk.flush()
		self.assertEqual(2, len(events))
		for event in events:
			self.assertEqual({'os_name': 'Mac'}, event.get('extra'))
			self.assertEqual({'id': 41}, event.get('user'))
			exc_type = event['exception']['values'][0]['type']
			self.assertEqual('ZeroDivisionError', exc_type)
	def test_user_from_worker_thread_goes_with_main_thread_events(self):
		# vitraj sets the user in the metrics thread.
		events = []
		handler = self._init_with_stub_transport(events)
		worker = Thread(target=handler.scope.set_user, args=({'id': 7},))
		worker.start()
		worker.join()
		handler.handle(*_get_exc_info())
		sentry_sdk.flush()
		self.assertEqual(1, len(events))
		self.assertEqual({'id': 7}, events[0].get('user'))
	def test_handle_is_rate_limited(self):
		handler = SentryExceptionHandler(None, '1.2.3', 'test', rate_limit=2)
		handler.init()
		exc = ValueError('x')
		with patch.object(sentry_sdk, 'capture_exception') as capture:
			for _ in range(3):
				handler.handle(ValueError, exc, None)
		self.assertEqual(2, capture.call_count)
		capture.assert_called_with((ValueError, exc, None))
	def _init_with_stub_transport(self, events):
		transport = _StubTransport(events=events)
		init = partial(sentry_sdk.init, transport=transport)
		handler = SentryExceptionHandler(
			'https://key@example.invalid/1', '1.2.3', 'test'
		)
		with patch.object(sentry_sdk, 'init', init):
			handler.init()
		return handler
	def tearDown(self):
		# The default integrations patch the interpreter for all later tests.
		sentry_sdk.init(None, default_integrations=False)
		sentry_sdk.get_global_scope().clear()
		super().tearDown()

class _StubTransport(Transport):
	def __init__(self, options=None, events=None):
		super().__init__(options)
		self._events = events
	def capture_envelope(self, envelope):
		for item in envelope.items:
			if item.type == 'event':
				self._events.append(item.payload.json)

def _get_exc_info():
	try:
		1 / 0
	except ZeroDivisionError:
		return sys.exc_info()
