#!/usr/bin/env python3

from PIL import Image

def process_bucket(bucket):
	minmap = bucket[0]
	maxmap = bucket[0]
	for pixel in bucket:
		minmap = [min(minmap[i], pixel[i]) for i in range(3)]
		maxmap = [max(maxmap[i], pixel[i]) for i in range(3)]
	rangemap = [maxmap[i]-minmap[i] for i in range(3)]
	color = rangemap.index(max(rangemap))
	bucket = sorted(bucket, key=lambda k:k[color])
	return bucket[:len(bucket)//2], bucket[len(bucket)//2:]

def get_palette(pixels, powah=2):
	pixels = list(set(map(tuple, pixels)))
	buckets = [pixels]
	for i in range(powah):
		newbucks = []
		for bucket in buckets:
			newbucks += process_bucket(bucket)
		buckets = newbucks
	return [[sum(y)//len(y) for y in zip(*bucket)] for bucket in buckets]

def find_closest_color(pixel, palette):
	distances = []
	for color in palette:
		distances.append(sum(abs(pixel[i]-color[i]) for i in range(3)))
	index = distances.index(min(distances))
	return index #palette[index]

def pixels_to_palette(pixels, palette):
	return tuple(map(lambda x: find_closest_color(x, palette), pixels))

def dither_pixels_to_palette(pixels, palette, size):
	paletted = []
	w, h = size
	for y in range(h):
		for x in range(w):
			oldpixel = pixels[(y*w) + x]
			index = find_closest_color(oldpixel, palette)
			newpixel = palette[index]
			diff = [oldpixel[i] - newpixel[i] for i in range(3)]
			paletted.append(index)
			for xo,yo,m in ((1,0,7/16),(-1,1,3/16),(0,1,5/16),(1,1,1/16)):
				if x+xo < 0 or x+xo >= w or y+yo < 0 or y+yo >= h:
					continue
				otherpix = pixels[(y+yo)*w + x+xo]
				otherpix = [max(0,min(255,round(otherpix[i]+diff[i]*m))) for i in range(3)]
				pixels[(y+yo)*w + x+xo] = otherpix
	return paletted


img = Image.open('image_to_dither.png')
img.thumbnail((200, 100))
img = img.convert('RGB')
img.show()
pixels = list(img.getdata()) #tuple(img.tobytes())

#pixels = [data[x:x+3] for x in range(0, len(data), 3)]

palette = get_palette(pixels, 3)
paletted = dither_pixels_to_palette(pixels, palette, img.size)
#data = bytes(channel for pixel in pixels for channel in pixel)
#newimg = Image.frombytes('RGB', img.size, data)
data = bytes(paletted)
newimg = Image.frombytes('P', img.size, data)
newimg.putpalette([channel for color in palette for channel in color])
newimg.show()
