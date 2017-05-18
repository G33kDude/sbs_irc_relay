#!/usr/bin/env python3

import bridge

import socketserver
import threading

# TODO: emote subsystem http://chat.smilebasicsource.com/emotes.json http://chat.smilebasicsource.com/scripts/emotes.js
# TODO: pm support
# TODO: Support showing admin status for channel operators

socketserver.TCPServer.allow_reuse_address = True

class Server:
	class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
		pass

	class TCPHandler(socketserver.BaseRequestHandler):
		def handle(self):
			"""Handles client connection for server"""
			thebridge = bridge.Bridge(self.request)
			buf = b''
			while True:
				data = self.request.recv(1024)
				if not data: break
				buf += data
				lines = buf.split(b'\r\n')
				buf = lines.pop()
				for line in lines:
					print('<', line)
					thebridge.handle(line.decode('utf-8', 'replace'))
			thebridge.disconnect()

	def serve(self, daemon=False):
		server = self.TCPServer(('0.0.0.0', 6667), self.TCPHandler)
		thread = threading.Thread(target=server.serve_forever)
		thread.daemon = daemon
		thread.start()

		# TODO: close server on exit
		#self.server.shutdown()
		#self.server.server_close()

if __name__ == '__main__':
	print("Serving")
	server = Server()
	server.serve()
