#!/usr/bin/env python3

import re

MESSAGE_MAX_LEN = 512

RPL_WELCOME       = '001'
RPL_ISUPPORT      = '005'
RPL_ENDOFWHO      = '315'
RPL_CHANNELMODEIS = '324'
RPL_CREATIONTIME  = '329'
RPL_TOPIC         = '332'
RPL_TOPICWHOTIME  = '333'
RPL_WHOREPLY      = '352'
RPL_NAMREPLY      = '353'
RPL_ENDOFNAMES    = '366'

ERR_NOSUCHCHANNEL = '403'
ERR_NOMOTD        = '422'
ERR_NOTONCHANNEL  = '442'

# http://stackoverflow.com/a/6043797
def split_utf8(s, n):
	"""Split UTF-8 s into chunks of maximum length n."""
	while len(s) > n:
		k = n
		while (ord(s[k]) & 0xc0) == 0x80:
			k -= 1
		yield s[:k]
		s = s[k:]
	yield s

class IRCMessage:
	ircre = ('^(?::(\S+?)(?:!(\S+?))?(?:@(\S+?))? )?' # Nick!User@Host
	+ '(\S+)(?: (?!:)(.+?))?(?: :(.+))?$') # CMD Params Params :Message

	def __init__(self, message):
		self.message = message
		matched = re.match(self.ircre, self.message).groups()
		self.nick = matched[0]
		self.user = matched[1]
		self.host = matched[2]
		self.cmd = matched[3]
		self.params = (matched[4] or '').split(' ')
		self.text = matched[5]

class IRC:
	def __init__(self, servername, request):
		self.servername = servername
		self.request = request

	def handle(self, line):
		"""Handles a single line sent by a client"""
		message = IRCMessage(line)
		method = '_on_' + message.cmd
		if hasattr(self, method):
			if getattr(self, method)(message):
				return
		method = 'on_' + message.cmd
		if hasattr(self, method):
			getattr(self, method)(message)

	def send(self, text, prefix='', suffix=''):
		"""Sends a message to the client"""
		messages = []
		max_size = (
			MESSAGE_MAX_LEN -
			len(prefix.encode('utf-8')) -
			len(suffix.encode('utf-8')) -
			len('/r/n')
		)

		for line in text.splitlines():
			for split in split_utf8(line, max_size):
				message = (prefix + split + suffix + '\r\n').encode('utf-8')
				messages.append(message)
				print('>', message)
				self.request.send(message)

		return messages

	def send_cmd(self, source, command, params=[], text=''):
		text = str(text)
		message = []
		if source:
			message.append(':' + str(source))
		message.append(command)
		message.extend(params)
		if text:
			message.append(':')
			self.send(text, ' '.join(map(str, message)))
		else:
			self.send(' '.join(map(str, message)))

	def _on_PING(self, message):
		if len(message.params) > 0:
			self.send(message.params[0], 'PONG ')
