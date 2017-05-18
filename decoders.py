#!/usr/bin/env python3

from PIL import Image
import hashlib
import html

import lzstr

def decode_text(text):
	return html.unescape(text)

def decode_markdown(text):
	# TODO: parse markdown into IRC codes
	return html.unescape(text)

def decode_image(text):
	return html.unescape(text)

def decode_raw(text):
	return text

def decode_code(text):
	# TODO: syntax highlighting? Pastebin?
	return html.unescape(text)

def decode_draw(text):
	IMAGE_WIDTH = 200
	IMAGE_HEIGHT = 100
	BYTES = IMAGE_WIDTH*IMAGE_HEIGHT // 4
	palette = [
			255, 255, 255,
			0,   0,   0,
			255, 0,   0,
			0,   0,   255
	]

	data = list(map(ord, lzstr.decompressFromBase64(text)))
	hexdigest = hashlib.sha1(bytes(data)).hexdigest()
	if len(data) > BYTES:
		palette = data[-data.pop()*3:]
	data += [0] * (BYTES-len(data))

	imgdata = b''
	for byte in data:
		imgdata += bytes((byte>>2*i) & 3 for i in range(4))

	img = Image.frombytes('P', (IMAGE_WIDTH, IMAGE_HEIGHT), imgdata)
	img.putpalette(palette)
	img.show()
	# return 'drawing'
#	img.save('/var/www/html/sbs/' + hexdigest + '.png')
#	return 'http://me.my.domain/sbs/' + hexdigest + '.png'
