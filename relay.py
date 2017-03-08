#!/usr/bin/env python3

import hashlib
import html
import json
import re
import socketserver
import sys
import threading
import time
import configparser

import requests
import websocket

socketserver.TCPServer.allow_reuse_address = True

IRCRE = ('^(?::(\S+?)(?:!(\S+?))?(?:@(\S+?))? )?' # Nick!User@Host
+ '(\S+)(?: (?!:)(.+?))?(?: :(.+))?$') # CMD Params Params :Message
IRC_MAX_BYTES = 512
IRC_CHANPREFIX = '#'

# TODO: Better splitting algorithm
def splitbytes(mystr, maxbytes, encoding):
	while mystr:
		target = maxbytes
		while True:
			segment = mystr[:target].encode(encoding)
			if len(segment) <= maxbytes:
				yield segment
				break
			target -= 1
			if target <= 0:
				raise Exception()
		mystr = mystr[target:]

# TODO: Normalize error handling

class TCPHandler(socketserver.BaseRequestHandler):
	'''Handles IRC (TCP) and SBS (WS) connections'''

	# ----- TCP Event Handlers -----

	def handle(self):
		buf = b''
		while True:
			data = self.request.recv(1024)
			if not data: break
			buf += data
			*lines, buf = buf.split(b'\r\n')
			for line in lines:
				print(b'irc<' + line) # log incoming data
				self.irc_handle(line.decode(self.config['encoding'], 'replace'))
		# TODO: better disconnect handling
		self.ws.close()
	def irc_handle(self, line):
		'''Parses a line of IRC protocol and calls the appropriate handler'''
		matched = re.match(IRCRE, line)
		nick, user, host, cmd, params, msg = matched.groups()
		if hasattr(self, 'irc_on' + cmd): # Method lookup
			handler = getattr(self, 'irc_on' + cmd)
			handler(nick, user, host, cmd, (params or '').split(' '), msg)
		else:
			self.irc_sendUNKOWNCOMMAND(self.nick, cmd, 'Unkown Command')
	
	# ----- IRC Send Methods -----

	def irc_send(self, message, prefix='', suffix=''):
		'''Sends a line of IRC protocl, breaking into
		IRC_MAX_BYTES sections as appropriate while
		preserving utf-8 multibyte sequences'''
		output = []
		prefix = prefix.encode(self.config['encoding'])
		suffix = suffix.encode(self.config['encoding'])
		maxbytes = IRC_MAX_BYTES - len(b'\r\n') - len(prefix) - len(suffix)
		for line in message.split('\r\n'):
			for part in splitbytes(line, maxbytes, self.config['encoding']):
				print(b'irc>' + prefix + part + suffix)
				self.request.send(prefix + part + suffix + b'\r\n')
				output.append(part)
		return output
	def irc_sendUNKOWNCOMMAND(self, target, command, reason):
		return self.irc_send(reason, ':{} 421 {} {} :'.format(
			self.config['irc_name'], target, command))
	def irc_sendNOMOTD(self, target, reason):
		return self.irc_send(reason, ':{} 422 {} :'.format(
			self.config['irc_name'], target))
	def irc_sendWELCOME(self, target, message):
		return self.irc_send(message, ':{} 001 {} :'.format(
			self.config['irc_name'], target))
	def irc_sendNOTICE(self, message, target=None):
		return self.irc_send(message, ':{} NOTICE {} :'.format(
			self.config['irc_name'], target or self.nick))
	def irc_sendJOIN(self, nick, channel):
		return self.irc_send(':{} JOIN {}'.format(nick, channel))
	def irc_sendNAMREPLY(self, target, channel, nicks):
		'''Takes a list of names and sends one or more RPL_NAMREPLY messages,
		followed by a RPL_ENDOFNAMES message'''
		prefix = ':{} 353 {} = {} :'.format(
				self.config['irc_name'], target, channel)
		maxbytes = IRC_MAX_BYTES - len(b'\r\n') - \
				len(prefix.encode(self.config['encoding']))
		while nicks:
			for i in range(1, len(nicks)+1):
				line = ' '.join(nicks[:i]).encode(self.config['encoding'])
				if len(line) > maxbytes:
					i -= 1
					break
			line = ' '.join(nicks[:i])
			nicks = nicks[i:]
			self.irc_send(line, prefix)
		self.irc_send('End of NAMES list', ':{} 366 {} {} :'.format(
				self.config['irc_name'], target, channel))
	def irc_sendQUIT(self, source): # TODO: Allow quit message
		return self.irc_send(':{} QUIT'.format(source))
	def irc_sendPRIVMSG(self, source, target, message):
		return self.irc_send(
			message,
			':{} PRIVMSG {} :'.format(source, target)
		)
	def irc_sendACTION(self, source, target, message):
		return self.irc_send(
			message,
			':{} PRIVMSG {} :\x01ACTION '.format(source, target),
			'\x01'
		)

	# ----- IRC Message Handlers -----

	def irc_onPASS(self, nick, user, host, cmd, params, msg):
		self.sbs_pass = params[0]
	def irc_onNICK(self, nick, user, host, cmd, params, msg):
		self.nick = params[0]
	def irc_onCAP(self, nick, user, host, cmd, params, msg):
		pass # TODO: Implement?
	def irc_onUSER(self, nick, user, host, cmd, params, msg):
		'''Initializes the SBS connection'''
		# TODO: use the USER information for something
		# TODO: better error handling
		# TODO: start 30s activity ping
		# TODO: figure out how to trigger initial message wave
		
		# Initiate server-side IRC connection
		# Make sure to join user to channels before the ws
		# tries to send the nick lists for those channels
		self.irc_channels = {}
		self.irc_sendWELCOME(self.nick, 'Welcome {}!'.format(self.nick))
		self.irc_sendNOMOTD(self.nick, 'ERR_NOMOTD')
		
		# Get the user's ID and access token
		r = requests.post(self.config['sbs_query'] + '/usercheck',
			params={'username': self.nick})
		self.sbs_uid = r.json()['result']
		r = requests.post(self.config['sbs_query'] + '/chatauth', data={
			'username': self.nick,
			'password': hashlib.md5(self.sbs_pass.encode('utf-8')).hexdigest()
		})
		self.sbs_token = r.json()['result']
		
		# Initiate the websocket connection to the SBS servers
		self.sbs_used_ids = set()
		self.sbs_nicks = {}
		self.ws = websocket.WebSocketApp(
			'ws://{}:{}/chatserver'.format(
				self.config['sbs_host'], self.config['sbs_port']),
			on_open    = self.ws_open,
			on_message = self.ws_message,
			on_error   = self.ws_error,
			on_close   = self.ws_close
		)
		thread = threading.Thread(target=self.ws.run_forever)
		thread.daemon = True
		thread.start()
	def irc_onJOIN(self, nick, user, host, cmd, params, msg):
		channel = params[0]
		source = self.nick+'!'+str(self.sbs_uid)+'@'+self.config['sbs_host']
		for channel in params[0].split(','):
			if channel not in self.irc_channels:
				self.irc_sendNOTICE(
					'[ERROR] Unkown channel: {}'.format(channel))
				continue
			self.irc_sendJOIN(source, channel)
			self.irc_sendNAMREPLY(
				self.nick, channel, self.irc_channels[channel])
	def irc_onPING(self, nick, user, host, cmd, params, msg):
		self.irc_send('PONG {}'.format(params[0]))
	def irc_onPRIVMSG(self, nick, user, host, cmd, params, msg):
		if msg.startswith('\x01ACTION') and msg.endswith('\x01'):
			msg = '/me ' + msg[len('\x01ACTION'):len('\x01')]
		self.sbs_send({
			'type': 'message',
			'key': self.sbs_token,
			'text': msg,
			'tag': params[0][len(IRC_CHANPREFIX):]
		})
	
	# ----- WS Event Handlers -----
	
	def ws_open(self, ws):
		# Authenticate with the SBS chat server
		self.sbs_send({
			'type': 'bind',
			'uid': self.sbs_uid,
			'key': self.sbs_token
		})
	def ws_message(self, ws, framedata):
		print('sbs<' + framedata)
		frame = json.loads(framedata)
		if hasattr(self, 'sbs_on' + frame['type']):
			handler = getattr(self, 'sbs_on' + frame['type'])
			handler(frame)
		else:
			self.irc_sendNOTICE('[ERROR] Unkown frame:')
			self.irc_sendNOTICE(framedata)
	def ws_error(self, ws, error):
		raise Exception("Websocket Error: {}".format(error))
	def ws_close(self, ws):
		# TODO: Gracefully handle disconnect
		print("CLOSING WEBSOCKET")
	
	# ----- SBS Send Methods -----

	def sbs_send(self, data):
		data = json.dumps(data)
		print('sbs>' + data)
		self.ws.send(data)
	
	# ----- SBS Event Handlers -----

	def sbs_onuserList(self, frame):
		self.sbs_userlist = frame
		# TODO: support rooms properly
		nicks = {user['username']: user for user in frame['users']}
		
		# Diff the nick lists
		newnicks = list(set(nicks) - set(self.sbs_nicks))
		oldnicks = list(set(self.sbs_nicks) - set(nicks))
		
		if self.nick in newnicks: # Initial channel join
			for tag in self.config['tags'].split(','):
				self.irc_channels[IRC_CHANPREFIX + tag] = list(nicks)
				self.irc_onJOIN(None, None, None, # Join user to channel
						'JOIN', [IRC_CHANPREFIX + tag], None)
		else:
			for tag in self.config['tags'].split(','):
				for nick in newnicks:
					self.irc_channels[IRC_CHANPREFIX + tag] = list(nicks)
					self.irc_sendJOIN(self.sbs_getuser(nick, nicklist=nicks),
							IRC_CHANPREFIX + tag)
		
		# Handle absent nicks
		for nick in oldnicks:
			self.irc_sendQUIT(self.sbs_getuser(nick))
		
		# Save new list for later comparison
		self.sbs_nicks = nicks
	def sbs_getuser(self, nick, nicklist=None):
		if nicklist is None:
			nicklist = self.sbs_nicks
		if nick in nicklist:
			uid = nicklist[nick]['uid']
		else:
			uid = 0 # TODO: Better handling
		return '{}!{}@{}'.format(
			nick,
			uid,
			self.config['sbs_host']
		)
	def sbs_onmessageList(self, frame):
		# TODO: Handle case where user is not in userlist
		# TODO: Handle timestamp mismatch (initial scrollback)
		for message in frame['messages']:
			if message['id'] in self.sbs_used_ids:
				continue
			self.sbs_used_ids.add(message['id'])
			if message['username'] == self.nick:
				continue
			for line in message['message'].splitlines():
				if message['encoding'] == 'draw':
					try:
						decoded = image_decode(line)
					except: # TODO: More specific error
						decoded = "[ERROR] Couldn't decode image!"
				else:
					decoded = html.unescape(line)
				channel = IRC_CHANPREFIX + message['tag']
				if channel not in self.irc_channels:
					self.irc_onJOIN(None, None, None, 'JOIN', [channel], None)
				self.irc_sendPRIVMSG(
					self.sbs_getuser(message['username']),
					channel,
					decoded
				)
	def sbs_onmodule(self, frame):
		# TODO: Better /me support
		message = html.unescape(frame['message'])
		if frame['module'] == 'fun':
			split = message.split(' ', 1)
			if split[0] not in self.sbs_nicks: # Not a /me action message
				self.irc_sendNOTICE('[ERROR] Unkown fun module usage:')
				self.irc_sendNOTICE(str(frame))
				return
			if split[0] == self.sbs_nick: # Outgoing message
				return
			self.irc_sendACTION(
				self.sbs_getuser(split[0]),
				IRC_CHANPREFIX + frame['tag'],
				split[1]
			)
		else:
			self.irc_sendNOTICE('[ERROR] Unkown module frame type:')
			self.irc_sendNOTICE(str(frame))
	def sbs_onresponse(self, frame):
		if not frame['result']:
			self.irc_sendNOTICE('[ERROR] Received false response:')
			self.irc_sendNOTICE(str(frame))
			return
		# After initialization completes request initial chat logs
		if frame['from'] == 'bind':
			self.sbs_send({'type': 'request', 'request': 'messageList'})
	def sbs_onsystem(self, frame):
		message = html.unescape(frame['message'])
		if 'subtype' not in frame:
			self.irc_sendNOTICE('[ERROR] System frame missing subytpe:')
			self.irc_sendNOTICE(str(frame))
			return
		if frame['subtype'] in ('join', 'leave'):
			return
		self.irc_sendNOTICE(message)

class IRCRelay():
	class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
		pass
	
	def __init__(self, config_name):
		print('Using config {}'.format(config_name))
		config = configparser.ConfigParser()
		config.read(['default.cfg', 'custom.cfg'], 'utf-8')
		self.config = config[config_name]
		class Handler(TCPHandler):
			config = self.config
		self.handler = Handler
	
	def serve(self, daemon=False):
		self.server = self.TCPServer(
			(self.config['irc_addr'], int(self.config['irc_port'])),
			self.handler)
		print('Serving on {}:{}'.format(
			self.config['irc_addr'], self.config['irc_port']))

		thread = threading.Thread(target=self.server.serve_forever)
		thread.daemon = daemon
		thread.start()
		
		# TODO: close server on exit
		#self.server.shutdown()
		#self.server.server_close()

if __name__ == '__main__':
	if len(sys.argv) > 1:
		config_name = sys.argv[1]
	else:
		config_name = 'DEFAULT'
	irc = IRCRelay(config_name)
	irc.serve()
