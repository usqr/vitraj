from socket import socketpair, SOCK_DGRAM

import signal

class SignalWakeupHandler:
	"""
	Quit the app cleanly when the user pushes Ctrl+C in the console. Python
	only runs signal handlers when the Qt event loop gives control back. A
	socket pair wakes the event loop, so the handler runs at once. This
	replaces fbs_runtime's class of the same name. See:
	https://stackoverflow.com/a/37229299/1839209
	"""
	def __init__(self, app, QAbstractSocket):
		self._app = app
		self.old_fd = None
		self.wsock, self.rsock = socketpair(type=SOCK_DGRAM)
		self.socket = QAbstractSocket(QAbstractSocket.UdpSocket, app)
		self.socket.setSocketDescriptor(self.rsock.fileno())
		self.wsock.setblocking(False)
		self.old_fd = signal.set_wakeup_fd(self.wsock.fileno())
		# The first Python code that runs gets any exception from the signal
		# handler. So connect a dummy handler first:
		self.socket.readyRead.connect(lambda: None)
		self.socket.readyRead.connect(self._read_signal)
	def install(self):
		signal.signal(signal.SIGINT, lambda *_: self._app.exit(130))
	def __del__(self):
		if self.old_fd is not None and signal and signal.set_wakeup_fd:
			signal.set_wakeup_fd(self.old_fd)
	def _read_signal(self):
		# readyRead does not occur again until readData() runs:
		self.socket.readData(1)
