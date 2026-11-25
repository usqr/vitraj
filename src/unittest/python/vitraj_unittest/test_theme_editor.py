from os.path import dirname, join
from unittest import TestCase

import re
import sys

_PLUGINS = join(
	dirname(__file__), '..', '..', '..', 'main', 'resources', 'base', 'Plugins'
)
if join(_PLUGINS, 'Theme Editor') not in sys.path:
	sys.path.append(join(_PLUGINS, 'Theme Editor'))

from PySide6.QtCore import QItemSelectionModel # noqa: E402
from PySide6.QtGui import QColor, QStandardItemModel # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QStatusBar, \
	QTableView # noqa: E402
from theme_editor import _BUILTIN_THEMES, _DEFAULTS, _build_override_qss \
	# noqa: E402

_app = QApplication.instance() or QApplication([])

_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

# The coolors.co palette themes and the CLI themes. Each one must be readable.
_READABLE_THEMES = (
	'Abyss', 'Amber Night', 'Bauhaus', 'Bauhaus Light', 'Cotton Candy', 'Ember',
	'Evergreen', 'Harbor', 'Midnight Slate', 'Olive Grove', 'Parchment',
	'Terracotta', 'Ultraviolet',
	'ANSI', 'Amber Terminal', 'Greenbar', 'Phosphor',
)

# (text key, background key, minimum WCAG contrast ratio)
_READABLE_PAIRS = (
	('text_secondary', 'base_bg', 4.5),
	('text_secondary', 'alternate_bg', 4.5),
	('text_dirs', 'base_bg', 4.5),
	('text_dirs', 'alternate_bg', 4.5),
	('selected_color', 'base_bg', 4.5),
	('selected_color', 'alternate_bg', 4.5),
	('text_secondary', 'cursor_bg', 3),
	('text_dirs', 'cursor_bg', 3),
	('selected_color', 'cursor_bg', 3),
	('text_primary', 'cursor_bg', 3),
	('text_primary', 'window_bg', 4.5),
	('text_header', 'header_bg_bottom', 3),
	('text_status', 'status_bar_bg_top', 4.5),
	('text_status', 'status_bar_bg_bottom', 4.5),
	('text_location', 'window_bg', 3),
	('input_text', 'input_bg', 4.5),
	('quicksearch_input_text', 'quicksearch_input_bg', 4.5),
	('text_secondary', 'quicksearch_bg', 3),
	('text_secondary', 'quicksearch_selected', 3),
)


def _luminance(hex_color):
	channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
	r, g, b = [
		c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
		for c in channels
	]
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(color_a, color_b):
	high, low = sorted((_luminance(color_a), _luminance(color_b)), reverse=True)
	return (high + 0.05) / (low + 0.05)


class BuiltinThemesTest(TestCase):
	def test_themes_use_known_keys_and_hex_colors(self):
		for name, colors in _BUILTIN_THEMES.items():
			with self.subTest(theme=name):
				self.assertLessEqual(set(colors), set(_DEFAULTS))
				for value in colors.values():
					self.assertRegex(value, _HEX_COLOR)

	def test_readable_themes_set_all_keys(self):
		for name in _READABLE_THEMES:
			with self.subTest(theme=name):
				self.assertEqual(set(_DEFAULTS), set(_BUILTIN_THEMES[name]))

	def test_readable_themes_have_enough_contrast(self):
		for name in _READABLE_THEMES:
			colors = _BUILTIN_THEMES[name]
			for text, background, minimum in _READABLE_PAIRS:
				with self.subTest(theme=name, text=text, background=background):
					ratio = _contrast(colors[text], colors[background])
					self.assertGreaterEqual(ratio, minimum)


class OverrideQssTest(TestCase):
	def test_status_bar_label_shows_status_bar_color(self):
		colors = dict(_DEFAULTS)
		colors.update(_BUILTIN_THEMES['Bauhaus'])
		status_bar = QStatusBar()
		status_bar.setStyleSheet(_build_override_qss(colors))
		label = QLabel('Selected: 2', status_bar)
		status_bar.addWidget(label)
		status_bar.resize(400, 30)
		pixel = status_bar.grab().toImage().pixelColor(label.x() + 2, 15)
		self.assertNotEqual(QColor(colors['window_bg']).rgb(), pixel.rgb())
		status_bar.deleteLater()

	def test_selected_alternate_row_keeps_alternate_color(self):
		colors = dict(_DEFAULTS)
		colors.update(_BUILTIN_THEMES['Greenbar'])
		model = QStandardItemModel(3, 2)
		view = QTableView()
		view.setModel(model)
		view.setAlternatingRowColors(True)
		view.setStyleSheet(_build_override_qss(colors))
		view.resize(300, 200)
		view.show()
		_app.processEvents()
		view.selectionModel().select(
			model.index(1, 1), QItemSelectionModel.SelectionFlag.Select
		)
		rect = view.visualRect(model.index(1, 1))
		image = view.viewport().grab().toImage()
		pixel = image.pixelColor(rect.center())
		self.assertEqual(QColor(colors['alternate_bg']).rgb(), pixel.rgb())
		view.hide()
		view.deleteLater()


class FileListViewTest(TestCase):
	def test_file_list_shows_alternate_rows(self):
		from vitraj.impl.view import FileListView
		view = FileListView(None, get_context_menu=lambda *_: [])
		self.assertTrue(view.alternatingRowColors())
		view.deleteLater()
