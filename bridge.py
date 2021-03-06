#!/usr/bin/env python3

import traceback

import irc
import sbs
import decoders

class Bridge:
	def __init__(self, request):
		self.servername = 'smilebasic'
		self.nickname = ''
		self.password = ''
		self.realname = '' # TODO: use for server info
		self.joinedto = []
		self.tojoin = []
		self.channels = {}
		self.connected = False

		self.irc = irc.IRC(self.servername, request)
		self.irc.on_MODE = self.irc_on_MODE
		self.irc.on_WHO  = self.irc_on_WHO
		self.irc.on_PASS = self.irc_on_PASS
		self.irc.on_NICK = self.irc_on_NICK
		self.irc.on_USER = self.irc_on_USER
		self.irc.on_JOIN = self.irc_on_JOIN
		self.irc.on_PART = self.irc_on_PART
		self.irc.on_PRIVMSG = self.irc_on_PRIVMSG

		self.sbs = sbs.SBS()
		self.sbs.debug_traceback = self.debug_traceback
		self.sbs.debug = self.debug
		self.sbs.on_message = self.sbs_on_message
		self.sbs.on_userList = self.sbs_on_userList
		self.sbs.on_response = self.sbs_on_response

	def disconnect(self):
		self.sbs.ws.close()

	def handle(self, line):
		try:
			self.irc.handle(line)
		except:
			self.debug_traceback()

	def debug_traceback(self):
		self.debug(traceback.format_exc())

	def debug(self, data):
		if self.connected:
			self.send_numeric('NOTICE', text=str(data))
		else:
			print(data)

	def send_names(self, channel):
		# TODO: Merge mulitple nicks into same message
		# TODO: properly report user rank for client

		for uid in self.channels[channel]:
			user = self.sbs.users[uid]
			rank = ['', '+'][user['level']] if user['level'] < 2 else '@'
			self.send_numeric(irc.RPL_NAMREPLY, ['=', channel],
				rank + user['username'])
		self.send_numeric(irc.RPL_ENDOFNAMES, [channel],
			'End of /NAMES list')

	def try_update_channels(self):
		if not self.sbs.tags: return
		if not self.sbs.users: return

		# Update the channel list
		old_channels = self.channels
		self.channels = {
			'#'+tag: self.sbs.online_users
			for tag in self.sbs.tags
		}
		self.channels.update({
			'#'+name: users
			for name, users in self.sbs.rooms.items()
		})

		# Spot the differences
		new = set(self.channels).difference(old_channels)
		gone = set(old_channels).difference(self.channels)
		same = set(self.joinedto).intersection(self.channels)

		# Make client part channels that no longer exist
		for channel in gone.intersection(self.joinedto):
			self.joinedto.remove(channel)
			self.send_from_me('PART', [channel])

		# Send client changes in user list for each channel
		for channel in same:
			# Users that exist who didn't before
			for uid in self.channels[channel].difference(old_channels[channel]):
				self.irc.send_cmd(self.fulluser(uid), 'JOIN', [channel])

				# Apply appropriate user mode
				user = self.sbs.users[uid]
				if user['level'] == 1:
					self.send_mode(channel, '+v', user['username'])
				elif user['level'] > 1:
					self.send_mode(channel, '+o', user['username'])

			# Users that don't exist who did before
			for uid in old_channels[channel].difference(self.channels[channel]):
				self.irc.send_cmd(self.fulluser(uid), 'PART', [channel])

		# TODO: only join channels where client is in user list
		# Make client join new channels
		self.tojoin.extend(new)
		self.try_join_client()

	def try_join_client(self):
		if not self.channels: return
		if not self.tojoin: return

		joinedsome = False
		for channel in set(self.tojoin):
			if channel not in self.channels:
				self.send_numeric(irc.ERR_NOSUCHCHANNEL, [channel],
					'No such channel')
				continue

			if channel not in self.joinedto:
				self.joinedto.append(channel)
				joinedsome = True

			# Join the user to the channel and send a user list
			self.send_from_me('JOIN', [channel])
			self.send_topic(channel)
			self.send_names(channel)
		self.tojoin.clear()

		# TODO: find a more appropriate time to call this?
		# In case it hasn't been requested before, request the message list
		if joinedsome:
			self.sbs.ws_send({
				"type": "request",
				"request": "messageList"
			})

	def fulluser(self, userid):
		# TODO: better name for this method
		user = self.sbs.users[userid]
		return '{}!{}@{}'.format(
			user['username'],
			user['uid'],
			self.irc.servername
		)
	def myuser(self):
		return self.fulluser(self.sbs.userid)

	def try_initiate_connection(self):
		if not self.nickname: return
		if not self.password: return
		if not self.realname: return
		if self.connected: return
		self.connected = True

		# Initiate IRC connection
		self.send_numeric(irc.RPL_WELCOME, text='Welcome!')
		self.send_numeric(irc.RPL_ISUPPORT, [
			'CHANTYPES=#',
			'PREFIX=(ov)@+',
#			'NETWORK=' + self.irc.servername
		], 'are supported by this server')
		self.send_numeric(irc.ERR_NOMOTD, text='ERR_NOMOTD')

		# Initiate SBS connection
		self.sbs.login(self.nickname, self.password)
		self.sbs.connect()

	############################
	# Protocol Message Senders #
	############################

	def send_topic(self, channel, topic=''):
		self.send_numeric(irc.RPL_TOPIC, [channel],
			topic or 'https://smilebasicsource.com/chat')
		# self.send_numeric(irc.RPL_TOPICWHOTIME, [channel, self.myuser(), 0])

	def send_mode(self, channel, mode, user):
		self.send_from_me('MODE', [channel, mode, user])

	def send_numeric(self, numeric, params=[], text=None):
		self.irc.send_cmd(self.servername, numeric,
			[self.nickname, *params], text)
	def send_from_me(self, command, params=[], text=None):
		self.irc.send_cmd(self.myuser(), command, params, text)

	#############################
	# Protocol Message Handlers #
	#############################

	def irc_on_MODE(self, message):
		channel = message.params[0]
		self.send_numeric(irc.RPL_CHANNELMODEIS, [channel, '+t'])
		# self.send_numeric(irc.RPL_CREATIONTIME, [channel, 0])

	def irc_on_WHO(self, message):
		channel = message.params[0]
		for uid in self.channels[channel]:
			user = self.sbs.users[uid]
			rank = ['', '+'][user['level']] if user['level'] < 2 else '@'
			self.send_numeric(irc.RPL_WHOREPLY, [
				channel,             # channel
				user['uid'],         # user
				self.irc.servername, # host
				self.irc.servername, # server
				user['username'],    # nick
				('H' if user['active'] else 'G') + rank,
				':0',                # hopcount
				user['username']     # real_name
			])
		self.send_numeric(irc.RPL_ENDOFWHO, [channel],
			'End of /WHO list.')

	def irc_on_PASS(self, message):
		self.password = message.params[0]
		self.try_initiate_connection()
	def irc_on_NICK(self, message):
		self.nickname = message.params[0]
		self.try_initiate_connection()
	def irc_on_USER(self, message):
		self.realname = message.params[0]
		self.try_initiate_connection()

	def irc_on_JOIN(self, message):
		self.tojoin.extend(message.params[0].split(','))
		self.try_join_client()

	def irc_on_PART(self, message):
		for channel in message.params[0].split(','):
			if channel in self.joinedto:
				self.joinedto.remove(channel)
				self.send_from_me('PART', [channel])
			else:
				self.send_numeric(irc.ERR_NOTONCHANNEL, [channel],
					"You're not on that channel")

	def irc_on_PRIVMSG(self, message):
		text = message.text

		# Handle /me
		if text.startswith('\x01') and text.endswith('\x01'):
			split = text[1:-1].split(' ', 1)
			if split[0] == 'ACTION':
				text = '/me ' + split[1]

		# Find the appropriate destination (channel, user, etc)
		target = message.params[0]
		if target in self.channels:
			tag = target[1:] # Trim channel prefix
		else:
			# TODO: more efficient username lookup
			usernames = (user['username'] for user in self.sbs.users.values())
			if target in usernames:
				tag = 'offtopic' # TODO: make this value configurable
				text = '/pm {} {}'.format(target, text)
			else:
				self.debug('ERROR: unrecognized destination:')
				self.debug(message.message)
				return

		self.sbs.ws_send({
			"type": "message",
			"text": text,
			"key": self.sbs.token,
			"tag": tag
		})

	def sbs_on_message(self, data):
		# Attempt to decode
		if hasattr(decoders, 'decode_' + data['encoding']):
			decoder = getattr(decoders, 'decode_' + data['encoding'])
			message = decoder(data['message'])
		else:
			self.debug('Unknown encoding: {}'.format(data['encoding']))
			message = data['message']

		# Call the appropriate handler
		if hasattr(self, 'sbs_msg_' + data['type'] + '_' + data['subtype']):
			handler = getattr(self, 'sbs_msg_' + data['type'] + '_' + data['subtype'])
			handler(data, message)
		else:
			self.debug('Unknown message type:')
			self.debug(data)

	def sbs_msg_message_none(self, data, message):
		# Ignore messages sent by yourself
		if data['sender']['uid'] == self.sbs.userid:
			return

		# Make greentext green
		if message.startswith('>'):
			message = '\x033' + message

		# TODO: handle 'any'
		self.irc.send_cmd(self.fulluser(data['sender']['uid']),
			'PRIVMSG', ['#' + data['tag']], message)

	def sbs_msg_module_none(self, data, message):
		if data['module'] == 'pm':
			# Ignore pms sent by yourself
			# TODO: don't do this for the initial message log?
			if data['sender']['uid'] == self.sbs.userid:
				return

			# Find sender and recipient
			sender = data['sender']['uid']
			data['recipients'].remove(sender)
			if len(data['recipients']) != 1:
				self.debug('ERROR: multiple recipients for PM!')
				self.debug(data)
				return
			recipient = data['recipients'][0]

			# Send the message from the sender to the recipient
			# Skip the first line to ignore the module generated src/dest
			for line in message.splitlines()[1:]:
				self.irc.send_cmd(self.fulluser(sender), 'PRIVMSG',
					[self.sbs.users[recipient]['username']], line)
		elif data['module'] == 'fun':
			# Ignore /me message sent by yourself
			if data['sender']['uid'] == self.sbs.userid:
				return

			# Format the message for /me
			# TODO: make sure user is in channel
			# TODO: handle 'any'
			message = message.split(' ', 1)[1]
			self.irc.send(
				text=message,
				prefix=':{} PRIVMSG #{} :\x01ACTION '.format(
					self.fulluser(data['sender']['uid']),
					data['tag']
				),
				suffix='\x01'
			)
		elif data['module'] == 'global':
			self.irc.send_cmd(self.servername,
				'NOTICE', [self.nickname], message)
		else:
			self.debug('Unkown module message')
			self.debug(data)

	# Ignore system generated join and leave messages
	def sbs_msg_system_join(self, data, message): pass
	def sbs_msg_system_leave(self, data, message): pass
	def sbs_msg_system_none(self, data, message):
		user = data['sender']['username']
		if message in ('{} has entered the chat.'.format(user),
			'{} has left the chat.'.format(user)):
			return

		self.debug('Unknown system message')
		self.debug(data)

	def sbs_msg_system_welcome(self, data, message):
		self.irc.send_cmd(self.servername, 'NOTICE', [self.nickname], message)

	def sbs_on_userList(self, data):
		self.try_update_channels()

	def sbs_on_response(self, data):
		if not data['result']:
			self.debug('sbs_on_response errors encountered:')
			self.debug(data)
			return
		if data['from'] == 'bind':
			self.try_update_channels() # Attempt to update the channel list
