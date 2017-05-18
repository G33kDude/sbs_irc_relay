#!/usr/bin/env python3

KEY_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="

def decompressFromBase64(base64):
	def datagen():
		for c in base64:
			if c in KEY_B64:
				yield KEY_B64.index(c)
	return decompress(datagen(), 32)

class Data: pass

def readBits(numBits, data):
	bits = 0
	for i in range(numBits):
		resb = data.val & data.pos
		data.pos >>= 1
		if data.pos == 0:
			data.pos = data.resetValue
			data.val = next(data.gen)
		bits |= (1<<i) if resb else 0
	return bits

def decompress(dataGen, resetValue):
	dictionary = {}
	enlargeIn = 4
	dictSize = 4
	numBits = 3
	entry = ''
	result = []
	errorCout = 0
	data = Data()
	data.gen = dataGen
	data.val = next(data.gen)
	data.resetValue = resetValue
	data.pos = resetValue

	for i in range(3):
		dictionary[i] = i
	bits = readBits(2, data)

	if bits == 0:
		bits = readBits(8, data)
		c = chr(bits)
	elif bits == 1:
		bits = readBits(16, data)
		c = chr(bits)
	elif bits == 2:
		return ''
	else:
		raise Exception('Unkown type thingy')

	dictionary[3] = c
	w = c
	result.append(c)

	while True:
		bits = readBits(numBits, data)
		c = bits
		if c == 0:
			bits = readBits(8, data)
			dictionary[dictSize] = chr(bits)
			c = dictSize
			dictSize += 1
			enlargeIn -= 1
		elif c == 1:
			bits = readBits(16, data)
			dictionary[dictSize] = chr(bits)
			c = dictSize
			dictSize += 1
			enlargeIn -= 1
		elif c == 2:
			return ''.join(result)
		else:
			pass # not an error

		if enlargeIn == 0:
			enlargeIn = 2 ** numBits
			numBits += 1

		if c in dictionary:
			entry = dictionary[c]
		elif c == dictSize:
			entry = w + w[0]
		else:
			return None # TODO: raise exception?
		result.append(entry)
		dictionary[dictSize] = w + entry[0]
		dictSize += 1
		enlargeIn -= 1
		w = entry
		if enlargeIn == 0:
			enlargeIn = 2 ** numBits
			numBits += 1
