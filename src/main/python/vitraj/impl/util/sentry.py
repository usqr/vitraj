from fbs_runtime.excepthook import ExceptionHandler
from fbs_runtime.excepthook._util import RateLimiter

import sentry_sdk

class SentryExceptionHandler(ExceptionHandler):
	"""
	Send stack traces to Sentry. This replaces the handler of fbs_runtime,
	which calls sentry_sdk.configure_scope(). sentry-sdk 3 removed that
	function.

	.scope is the global scope of Sentry. Data that you put in it goes with
	the events of all threads. It is available after .init().
	"""
	def __init__(
		self, dsn, app_version, environment, callback=lambda: None,
		rate_limit=10
	):
		super().__init__()
		self.scope = None
		self._dsn = dsn
		self._app_version = app_version
		self._environment = environment
		self._callback = callback
		self._rate_limiter = RateLimiter(60, rate_limit)
	def init(self):
		sentry_sdk.init(
			self._dsn, release=self._app_version, environment=self._environment,
			attach_stacktrace=True, default_integrations=False
		)
		self.scope = sentry_sdk.get_global_scope()
		self._callback()
	def handle(self, exc_type, exc_value, enriched_tb):
		if self._rate_limiter.please():
			sentry_sdk.capture_exception((exc_type, exc_value, enriched_tb))
