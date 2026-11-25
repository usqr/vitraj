"""
The media player widget. Import this module late: QtMultimedia loads FFmpeg.
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSlider, \
	QToolButton, QVBoxLayout, QWidget

_PLAY = '▶'
_PAUSE = '❚❚'
_MAX_COVER_SIZE = 256


def format_time(ms):
	"""Return `ms` milliseconds as "m:ss", or as "h:mm:ss" from one hour."""
	seconds = max(int(ms), 0) // 1000
	hours, rest = divmod(seconds, 3600)
	minutes, seconds = divmod(rest, 60)
	if hours:
		return '%d:%02d:%02d' % (hours, minutes, seconds)
	return '%d:%02d' % (minutes, seconds)


class MediaView(QWidget):
	"""
	Plays an audio or video file. It does not start playback by itself, and
	it pauses when it becomes hidden (another file, or a closed panel).
	"""
	def __init__(self, path, parent=None):
		super().__init__(parent)
		self._player = QMediaPlayer(self)
		self._player.setAudioOutput(QAudioOutput(self))
		self._video = QVideoWidget()
		self._player.setVideoOutput(self._video)
		self._init_ui()
		self._connect_player()
		self._player.setSource(QUrl.fromLocalFile(path))
		# Load the file and show the first video frame. This plays no sound:
		self._player.pause()

	def toggle_play(self):
		if self._player.playbackState() == QMediaPlayer.PlayingState:
			self._player.pause()
		else:
			self._player.play()

	def seek(self, delta_ms):
		position = self._player.position() + delta_ms
		duration = self._player.duration()
		if duration > 0:
			position = min(position, duration)
		self._player.setPosition(max(position, 0))

	def is_playing(self):
		return self._player.playbackState() == QMediaPlayer.PlayingState

	def hideEvent(self, event):
		self._player.pause()
		super().hideEvent(event)

	def _init_ui(self):
		self._cover = QLabel()
		self._cover.setAlignment(Qt.AlignCenter)
		self._cover.setWordWrap(True)
		self._cover.setStyleSheet('QLabel { padding: 20px; }')
		self._cover.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
		self._video.hide()
		self._play_button = QToolButton()
		self._play_button.setText(_PLAY)
		self._play_button.setToolTip('Play / pause')
		self._play_button.setAutoRaise(True)
		# Keep the keyboard focus in the file pane:
		self._play_button.setFocusPolicy(Qt.NoFocus)
		self._play_button.clicked.connect(self.toggle_play)
		self._slider = QSlider(Qt.Horizontal)
		self._slider.setFocusPolicy(Qt.NoFocus)
		self._slider.sliderMoved.connect(self._player.setPosition)
		self._time = QLabel()
		self._info = QLabel()
		self._info.setAlignment(Qt.AlignCenter)
		self._info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)
		layout.addWidget(self._video, 1)
		layout.addWidget(self._cover, 1)
		layout.addWidget(self._info)
		layout.addLayout(self._controls_layout())
		self.setLayout(layout)

	def _controls_layout(self):
		controls = QHBoxLayout()
		controls.setContentsMargins(4, 2, 8, 2)
		controls.addWidget(self._play_button)
		controls.addWidget(self._slider, 1)
		controls.addWidget(self._time)
		return controls

	def _connect_player(self):
		player = self._player
		player.durationChanged.connect(self._on_duration)
		player.positionChanged.connect(self._on_position)
		player.playbackStateChanged.connect(self._on_state)
		player.hasVideoChanged.connect(self._on_has_video)
		player.metaDataChanged.connect(self._on_metadata)
		player.errorOccurred.connect(self._on_error)

	def _on_duration(self, duration):
		self._slider.setRange(0, max(duration, 0))
		self._update_time()

	def _on_position(self, position):
		if not self._slider.isSliderDown():
			self._slider.setValue(position)
		self._update_time()

	def _update_time(self):
		self._time.setText('%s / %s' % (
			format_time(self._player.position()),
			format_time(self._player.duration())
		))

	def _on_state(self, state):
		playing = state == QMediaPlayer.PlayingState
		self._play_button.setText(_PAUSE if playing else _PLAY)

	def _on_has_video(self, has_video):
		self._video.setVisible(has_video)
		self._cover.setVisible(not has_video)

	def _on_metadata(self):
		if not self._play_button.isEnabled():
			# Keep the error text of #_on_error(...).
			return
		metadata = self._player.metaData()
		resolution = metadata.value(QMediaMetaData.Resolution)
		if self._player.hasVideo() and resolution:
			self._info.setText(
				'%d x %d' % (resolution.width(), resolution.height())
			)
			return
		title = metadata.stringValue(QMediaMetaData.Title)
		artist = metadata.stringValue(QMediaMetaData.ContributingArtist)
		self._info.setText(' – '.join(t for t in (title, artist) if t))
		self._show_cover(metadata)

	def _show_cover(self, metadata):
		image = metadata.value(QMediaMetaData.CoverArtImage)
		if not isinstance(image, QImage) or image.isNull():
			self._cover.setText('♪')
			return
		pixmap = QPixmap.fromImage(image).scaled(
			_MAX_COVER_SIZE, _MAX_COVER_SIZE, Qt.KeepAspectRatio,
			Qt.SmoothTransformation
		)
		self._cover.setPixmap(pixmap)

	def _on_error(self, _error, message):
		self._video.hide()
		self._cover.setPixmap(QPixmap())
		self._cover.setText('Cannot play media: %s' % message)
		self._cover.show()
		self._play_button.setEnabled(False)
		self._slider.setEnabled(False)
