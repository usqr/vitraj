from vitraj.impl.util.sentry import SentryExceptionHandler
from unittest import TestCase
from unittest.mock import patch

import sentry_sdk

class SentryExceptionHandlerTest(TestCase):
	def test_init_gives_global_scope_and_calls_callback(self):
		calls = []
		handler = SentryExceptionHandler(
			None, '1.2.3', 'test', callback=lambda: calls.append(handler.scope)
		)
		handler.init()
		self.assertIs(sentry_sdk.get_global_scope(), handler.scope)
		self.assertEqual([handler.scope], calls)
	def test_scope_accepts_context_of_app(self):
		handler = SentryExceptionHandler(None, '1.2.3', 'test')
		handler.init()
		handler.scope.set_extra('os_name', 'Mac')
		handler.scope.set_user({'id': 41})
	def test_handle_is_rate_limited(self):
		handler = SentryExceptionHandler(None, '1.2.3', 'test', rate_limit=2)
		handler.init()
		exc = ValueError('x')
		with patch.object(sentry_sdk, 'capture_exception') as capture:
			for _ in range(3):
				handler.handle(ValueError, exc, None)
		self.assertEqual(2, capture.call_count)
		capture.assert_called_with((ValueError, exc, None))
	def tearDown(self):
		sentry_sdk.init(None)
		super().tearDown()
