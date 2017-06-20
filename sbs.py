#!/usr/bin/env python3

import hashlib
import json
import threading

import requests
import websocket

import traceback

class SBS:
	def __init__(self):
		self.query_endpoint = 'https://development.smilebasicsource.com/query'
		self.chat_host = 'direct.smilebasicsource.com'
		self.chat_port = 45697

		self.users = {}
		self.online_users = []
		self.rooms = {}

		self.message_ids = []
		self.tags = []


	def login(self, username, password):
		"""Logs into the web server and saves a session ID"""

		# Due to some security updates a session ID is required to log in.
		# A session ID is generated for any visited page, so send a GET request
		# to this page even though it doesn't exist so we can use the cookie
		r = requests.get(self.query_endpoint)
		self.session = r.cookies['PHPSESSID']

		# Authenticate
		r = requests.post(self.query_endpoint + '/submit/login',
			params={
				'session': self.session
			},
			data={
				'username': username,
				'password': hashlib.md5(password.encode('utf-8')).hexdigest(),
			}
		)

		# Save the resulting userid and username for later use
		result = r.json()
		self.userid = result['requester']['uid']
		self.username = result['requester']['username']

	def connect(self):
		"""Requests a chat token and connects to the chat server"""
		if not self.session:
			raise Exception() # TODO: better exception
		r = requests.post(self.query_endpoint + '/request/chatauth',
			params={
				'session': self.session
			}
		)
		self.token = r.json()['result']

		self.ws = websocket.WebSocketApp(
			'ws://{}:{}/chatserver'.format(self.chat_host, self.chat_port),
			on_message=self.ws_message,
			on_open=self.ws_open,
			# on_error=debug,
			# on_close=debug
		) # TODO: handle ws disconnect

		thread = threading.Thread(target=self.ws.run_forever)
		thread.daemon = True
		thread.start()

	def ws_open(self, ws):
		print("Opening websocket")
		self.ws_send({
			'type': 'bind',
			'uid': self.userid,
			'lessData': True,
			'key': self.token
		})
	def ws_message(self, ws, text):
		try:
			print('<', text)
			data = json.loads(text)
			if hasattr(self, '_on_' + data['type']):
				getattr(self, '_on_' + data['type'])(data)
				if hasattr(self, 'on_' + data['type']):
					getattr(self, 'on_' + data['type'])(data)
			else:
				raise Exception("ERROR: UNKNOWN data: {}".format(data['type']))
		except:
			self.debug_traceback()
	def ws_send(self, data):
		data = json.dumps(data)
		print('>', data)
		self.ws.send(data)

	def _on_userList(self, data):
		self.online_users = {user['uid'] for user in data['users']}
		self.users.update({user['uid']: user for user in data['users']})
		for room in data['rooms']:
			self.users.update({user['uid']: user for user in room['users']})
		self.rooms = {
			room['name']: {user['uid'] for user in room['users']}
			for room in data['rooms']
		}

	def _on_messageList(self, data):
		# TODO: max remembered ids

		for message in data['messages']:
			if message['id'] in self.message_ids:
				continue
			# Only do this if the user has joined the channel (somehow)
			self.message_ids.append(message['id'])
			self.users[message['sender']['uid']] = message['sender']
			self.on_message(message)

	def _on_response(self, data):
		if not data['result']:
			return
		if data['from'] == 'bind':
			self.tags = data['extras']['basicTags']
