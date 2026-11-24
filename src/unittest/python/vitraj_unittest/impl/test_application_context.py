from vitraj.impl.application_context import DevelopmentApplicationContext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

class OnMainWindowShownTest(TestCase):
	def test_first_run_starts_the_tour(self):
		context = self._context(is_first_run=True)
		self._call(context)
		context.tutorial_factory.assert_called_once_with('pane')
		context.tour_controller.start.assert_called_once_with('tutorial')
	def test_later_run_shows_nothing(self):
		context = self._context(is_first_run=False)
		self._call(context)
		context.tutorial_factory.assert_not_called()
		context.tour_controller.start.assert_not_called()
	def _context(self, is_first_run):
		return SimpleNamespace(
			updater=None,
			session_manager=SimpleNamespace(is_first_run=is_first_run),
			plugin_support=MagicMock(get_panes=lambda: ['pane']),
			tutorial_factory=MagicMock(return_value='tutorial'),
			tour_controller=MagicMock()
		)
	def _call(self, context):
		with patch('vitraj.impl.application_context.is_mac', return_value=False):
			DevelopmentApplicationContext.on_main_window_shown(context)
