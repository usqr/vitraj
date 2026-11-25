from PySide6.QtCore import QEventLoop, QTimer

def qwait(ms):
	"""
	Process Qt events for `ms` milliseconds. Use this instead of
	QTest.qWait(...): in PySide6, qWait holds the GIL, so worker threads do
	not run while the test waits.
	"""
	loop = QEventLoop()
	QTimer.singleShot(ms, loop.quit)
	loop.exec()
