#!/usr/bin/env python
# coding: utf-8
#
#       Copyright 2008 Olivier Berten <olivier.berten@gmail.com>
#       
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 3 of the License, or
#       (at your option) any later version.
#       
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#       
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.
#

import os
import sys
from datetime import *
from color import *
from tempfile import mkdtemp
from shutil import rmtree
from cStringIO import StringIO
from PIL import Image,ImageDraw,ImageCms
from math import pi, log, sin, sqrt

VERSION = "0.8"

# from http://code.djangoproject.com/browser/django/trunk/django/utils/datastructures.py
class SortedDict(dict):
	"""
	A dictionary that keeps its keys in the order in which they're inserted.
	"""
	def __new__(cls, *args, **kwargs):
		instance = super(SortedDict, cls).__new__(cls, *args, **kwargs)
		instance.keyOrder = []
		return instance

	def __init__(self, data=None):
		if data is None:
			data = {}
		super(SortedDict, self).__init__(data)
		if isinstance(data, dict):
			self.keyOrder = data.keys()
		else:
			self.keyOrder = []
			for key, value in data:
				if key not in self.keyOrder:
					self.keyOrder.append(key)

	def __deepcopy__(self, memo):
		from copy import deepcopy
		return self.__class__([(key, deepcopy(value, memo))
							   for key, value in self.iteritems()])

	def __setitem__(self, key, value):
		super(SortedDict, self).__setitem__(key, value)
		if key not in self.keyOrder:
			self.keyOrder.append(key)

	def __delitem__(self, key):
		super(SortedDict, self).__delitem__(key)
		self.keyOrder.remove(key)

	def __iter__(self):
		for k in self.keyOrder:
			yield k

	def pop(self, k, *args):
		result = super(SortedDict, self).pop(k, *args)
		try:
			self.keyOrder.remove(k)
		except ValueError:
			# Key wasn't in the dictionary in the first place. No problem.
			pass
		return result

	def popitem(self):
		result = super(SortedDict, self).popitem()
		self.keyOrder.remove(result[0])
		return result

	def items(self):
		return zip(self.keyOrder, self.values())

	def iteritems(self):
		for key in self.keyOrder:
			yield key, super(SortedDict, self).__getitem__(key)

	def keys(self):
		return self.keyOrder[:]

	def iterkeys(self):
		return iter(self.keyOrder)

	def values(self):
		return [super(SortedDict, self).__getitem__(k) for k in self.keyOrder]

	def itervalues(self):
		for key in self.keyOrder:
			yield super(SortedDict, self).__getitem__(key)

	def update(self, dict_):
		for k, v in dict_.items():
			self.__setitem__(k, v)

	def setdefault(self, key, default):
		if key not in self.keyOrder:
			self.keyOrder.append(key)
		return super(SortedDict, self).setdefault(key, default)

	def value_for_index(self, index):
		"""Returns the value of the item at the given zero-based index."""
		return self[self.keyOrder[index]]

	def insert(self, index, key, value):
		"""Inserts the key, value pair before the item with the given index."""
		if key in self.keyOrder:
			n = self.keyOrder.index(key)
			del self.keyOrder[n]
			if n < index:
				index -= 1
		self.keyOrder.insert(index, key)
		super(SortedDict, self).__setitem__(key, value)

	def copy(self):
		"""Returns a copy of this object."""
		# This way of initializing the copy means it works for subclasses, too.
		obj = self.__class__(self)
		obj.keyOrder = self.keyOrder[:]
		return obj

	def __repr__(self):
		"""
		Replaces the normal dict.__repr__ with a version that returns the keys
		in their sorted order.
		"""
		return '{%s}' % ', '.join(['%r: %r' % (k, v) for k, v in self.items()])

	def clear(self):
		super(SortedDict, self).clear()
		self.keyOrder = []

class FileFormatError(Exception):
	pass

class Info(object):
	# Dublin Core (translatable,longtext)
	dc = {'contributor': (True,True),
	      'coverage': (True,False),
	      'creator': (True,False),
	      'description': (True,True),
	      'identifier': (False,False),
	      'language': (False,False),
	      'publisher': (True,False),
	      'relation': (True,False),
	      'rights': (True,True),
	      'source': (True,False),
	      'subject': (True,False),
	      'title': (True,False),
	      # DCMI Metadata Terms
	      'license': (False,False)}

	def __init__(self):
		self.format = 'application/swatchbook'
		self.type = 'http://purl.org/dc/dcmitype/Dataset'
		self.date = False
		for dc in self.dc:
			exec('self.'+dc+' = ""')
			if self.dc[dc][0]:
				exec('self.'+dc+'_l10n = {}')

		self.version = ""

class Book(object):
	def __init__(self):
		self.display = {'rows': False,
		                'columns': False}
		self.items = [] # Group,Swatch,Spacer,Break

	def count(self,swatchesonly=False):
		count = len(self.items)
		for e in self.items:
			if isinstance(e,Group):
				count += e.count(swatchesonly)
			if swatchesonly and not isinstance(e,Swatch):
				count -=1
		return count

class SwatchBook(object):
	def __init__(self, file=False,codec=False,websvc=False,webid=False):
		self.tmpdir = mkdtemp()
		self.info = Info()
		self.profiles = {}
		self.materials = {}
		self.book = Book()
		self.codec = False

		if file:
			self.read(file,codec)
		elif websvc:
			self.webread(websvc,webid)

	def __del__(self):
		rmtree(self.tmpdir)

	def test(self,file,codec=False):
		# test 1: codec
		test = False
		if codec:
			try:
				test = eval('codecs.'+codec).test(file)
			except (IOError,SyntaxError,struct.error):
				codec = False
			if test:
				return codec
		# test 2: extension
		ext =  os.path.splitext(os.path.basename(file))[1].lower()[1:]
		if ext in codecs.readexts:
			for codec in codecs.readexts[ext]:
				test = False
				try:
					test = eval('codecs.'+codec).test(file)
				except (IOError,SyntaxError,struct.error):
					pass
				if test:
					return codec
			else:
				codec = False
		# test 3: free
		for codec in codecs.reads:
			test = False
			try:
				test = eval('codecs.'+codec).test(file)
			except (IOError,SyntaxError,struct.error):
				pass
			if test: return codec
		else:
			codec = False
		return codec

	def webread(self,websvc,webid):
		import swatchbook.websvc as web
		svc = eval('web.'+websvc+'()')
		svc.read(self,webid)

	def read(self,file,codec):
		import swatchbook.codecs as codecs
		codec = self.test(file,codec)
		if codec:
			self.codec = codec
			eval('codecs.'+codec).read(self,file)
			if sys.platform == 'win32':
				encoding = "UTF-8"
			else:
				encoding = sys.getfilesystemencoding()
			if encoding == 'UTF-8' and isinstance(file,unicode):
				filename =  os.path.splitext(os.path.basename(file))[0]
			else:
				filename =  os.path.splitext(os.path.basename(file))[0].decode(encoding)
			if self.info.title == '':
				self.info.title = filename.replace('_',' ')
		else:
			raise FileFormatError

	def write(self,format,output=None):
		import swatchbook.codecs as codecs
		if format in codecs.writes:
			codec = eval('codecs.'+format)
			if output == None:
				print codec.write(self)
			else:
				content = codec.write(self)
				# TODO check if writable
				bookfile = open(output, 'wb')
				bookfile.write(content)
				bookfile.close()
		else:
			raise FileFormatError,'unsupported output format'

class Group(object):
	def __init__(self,title="",parent=None):
		self.info = Info()
		self.info.title = title
		self.items = []

	def count(self,swatchesonly=False):
		count = len(self.items)
		for e in self.items:
			if isinstance(e,Group):
				count += e.count(swatchesonly)
			if swatchesonly and not isinstance(e,Swatch):
				count -=1
		return count

class Swatch(object):
	def __init__(self,material,parent=None):
		self.material = material

class Spacer(object):
	def __init__(self,parent=None):
		pass

class Break(object):
	def __init__(self,parent=None):
		pass

class Color(object):
	"""Output values
       sRGB,RGB,HSV,HSL,CMY,CMYK,nCLR: 0 -> 1
       YIQ: Y 0 -> 1 : IQ -0.5 -> 0.5
       Lab: L 0 -> 100 : ab -128 -> 127
       LCH: LC 0 -> 100 : H 0 -> 360
       XYZ: 0 -> ~100 (cfr. ref)
	   XYZ: xy 0 -> 1 : Y 0 -> 100 """

	def __init__(self,swatchbook):
		self.info = Info()
		self.values = SortedDict()
		self.usage = set()
		self.extra = {}
		self.swatchbook = swatchbook

	def toRGB(self,prof_out=False):
		if not prof_out and ('sRGB',False) in self.values:
			return self.values[('sRGB',False)]
		else:
			for key in self.values:
				if key[1]:
					prof_in = self.swatchbook.profiles[key[1]].uri
				else:
					prof_in = False
				if toRGB(key[0],self.values[key],prof_in,prof_out):
					return toRGB(key[0],self.values[key],prof_in,prof_out)
					break
			else:
				return False
			
	def toRGB8(self,prof_out=False):
		if self.toRGB(prof_out):
			R,G,B = self.toRGB(prof_out)
			return (int(round(R*0xFF)),int(round(G*0xFF)),int(round(B*0xFF)))
		else:
			return False

class Tint(object):
	def __init__(self):
		self.info = Info()
		self.color = False
		self.amount = False # 1 = color, 0 = white
		self.usage = [] # for compatibility with colors
		self.extra = {}

	def toRGB(self,prof_out=False):
		R,G,B = self.color.toRGB(prof_out)
		H,S,L = RGB2HSL(R,G,B)
		L = L + (1-L)*(1-self.amount)
		return HSL2RGB(H,S,L)

	def toRGB8(self,prof_out=False):
		if self.toRGB(prof_out):
			R,G,B = self.toRGB(prof_out)
			return (int(round(R*0xFF)),int(round(G*0xFF)),int(round(B*0xFF)))
		else:
			return False

class Shade(object):
	def __init__(self):
		self.info = Info()
		self.color = False
		self.amount = False # 1 = color, 0 = black
		self.usage = [] # for compatibility with colors
		self.extra = {}

	def toRGB(self,prof_out=False):
		R,G,B = self.color.toRGB(prof_out)
		H,S,L = RGB2HSL(R,G,B)
		L = L*(self.amount)
		return HSL2RGB(H,S,L)

	def toRGB8(self,prof_out=False):
		if self.toRGB(prof_out):
			R,G,B = self.toRGB(prof_out)
			return (int(round(R*0xFF)),int(round(G*0xFF)),int(round(B*0xFF)))
		else:
			return False

class Pattern(object):
	def __init__(self,swatchbook):
		self.info = Info()
		self.extra = {}
		self.swatchbook = swatchbook

	def indexed(self):
		if self.image().palette():
			return True
		else:
			return False

	#TODO: SVG support
	def image(self):
		return Image.open(os.path.join(self.swatchbook.tmpdir,"patterns",self.info.identifier))

	def imageRGB(self,prof_out=False):
		image = self.image()
		alpha_band = False
		if image.mode in ('LA','PA','RGBA'):
			image.load()
			bands = image.split()
			alpha_band = bands[-1]
			image = Image.merge(image.mode[:-1],bands[:-1])
		sRGB = ImageCms.createProfile("sRGB")
		if 'icc_profile' in image.info:
			inputProfile = ImageCms.ImageCmsProfile(StringIO(image.info['icc_profile']))
		else:
			if image.mode == "CMYK":
				inputProfile = (dirpath(__file__) or ".")+"/Fogra27L.icm"
			elif image.mode == "LAB":
				inputProfile = ImageCms.createProfile("LAB")
			else:
				image = image.convert('RGB')
				inputProfile = sRGB
		if prof_out:
			outputProfile = prof_out
		else:
			outputProfile = sRGB
		new_image = ImageCms.profileToProfile(image,inputProfile,outputProfile)
		if alpha_band:
			new_image.putalpha(alpha_band)
		return new_image

	# to be called before deleting a pattern from the book
	def deleteFile(self):
		return os.remove(os.path.join(self.swatchbook.tmpdir,"patterns",self.info.identifier))

class Gradient(object):
	def __init__(self,swatchbook):
		self.info = Info()
		self.stops = []
		self.opacitystops = []
		self.extra = {}
		self.swatchbook = swatchbook

	def colorAt(self,pos,prof_out = False):
		if len(self.stops) == 0:
			return False
		left = 0
		right = len(self.stops)-1
		for i,stop in enumerate(self.stops):
			if pos >= stop.position:
				left = i
			else:
				right = i
				break
		if left == right:
			return self.swatchbook.materials[self.stops[left].color].toRGB(prof_out)
		seg_pos = (pos-self.stops[left].position)/(self.stops[right].position-self.stops[left].position)
		
		if "midpoint" in self.stops[left].args:
			midpoint = self.stops[left].args["midpoint"]
		else:
			midpoint = 0.5

		def linear(seg_pos,midpoint):
			if seg_pos <= midpoint:
				return 0.5 * seg_pos / midpoint
			else:
				seg_pos -= midpoint
				midpoint = 1.0 - midpoint
				return 0.5 + 0.5 * seg_pos / midpoint

		if self.stops[left].interpolation == "curved":
			factor = pow(seg_pos, log(0.5) / log(midpoint))
		elif self.stops[left].interpolation == "sine":
			factor = (sin ((-pi / 2.0) + pi * linear(seg_pos,midpoint)) + 1.0) / 2.0
		elif self.stops[left].interpolation == "sphere_increasing":
			factor = sqrt (1.0 - (linear(seg_pos,midpoint)-1.0) * (linear(seg_pos,midpoint)-1.0))
		elif self.stops[left].interpolation == "sphere_decreasing":
			factor = 1.0 - sqrt(1.0 - linear(seg_pos,midpoint) * linear(seg_pos,midpoint))
		else:
			factor = linear(seg_pos,midpoint)
		r1,g1,b1 = self.swatchbook.materials[self.stops[left].color].toRGB(prof_out) or (128,128,128)
		r2,g2,b2 = self.swatchbook.materials[self.stops[right].color].toRGB(prof_out) or (128,128,128)
		if "space" in self.stops[left].args and self.stops[left].args["space"] == 'HSV':
			left_hsv = RGB2HSV(r1,g1,b1)
			right_hsv = RGB2HSV(r2,g2,b2)

			s = left_hsv[1] + (right_hsv[1] - left_hsv[1]) * factor
			v = left_hsv[2] + (right_hsv[2] - left_hsv[2]) * factor

			if "direction" in self.stops[left].args and self.stops[left].args["direction"] == 'CW':
				if right_hsv[0] < left_hsv[0]:
					h = left_hsv[0] - (left_hsv[0] - right_hsv[0]) * factor
				else:
					h = left_hsv[0] - (1.0 - (right_hsv[0] - left_hsv[0])) * factor
				if h < 0.0:
					h += 1.0
			else:
				if left_hsv[0] < right_hsv[0]:
					h = left_hsv[0] + (right_hsv[0] - left_hsv[0]) * factor
				else:
					h = left_hsv[0] + (1.0 - (left_hsv[0] - right_hsv[0])) * factor
				if (h > 1.0):
					h -= 1.0
			r,g,b = HSV2RGB(h,s,v)
		else:
			r = r1 + (r2 - r1) * factor
			g = g1 + (g2 - g1) * factor
			b = b1 + (b2 - b1) * factor

		if "gamma" in self.stops[left].args:
			r = pow(r, self.stops[left].args["gamma"])
			g = pow(g, self.stops[left].args["gamma"])
			b = pow(b, self.stops[left].args["gamma"])

		return (r,g,b)

	def alphaAt(self,pos):
		if len(self.opacitystops) == 0:
			return 1
		left = 0
		right = len(self.opacitystops)-1
		for i,stop in enumerate(self.opacitystops):
			if pos >= stop.position and self.opacitystops[i+1].position > stop.position:
				left = i
			else:
				right = i
				break

		if left == right:
			return self.opacitystops[left].opacity

		seg_pos = (pos-self.opacitystops[left].position)/(self.opacitystops[right].position-self.opacitystops[left].position)
		
		if "midpoint" in self.opacitystops[left].args:
			midpoint = self.opacitystops[left].args["midpoint"]
		else:
			midpoint = 0.5

		def linear(seg_pos,midpoint):
			if seg_pos <= midpoint:
				return 0.5 * seg_pos / midpoint
			else:
				seg_pos -= midpoint
				midpoint = 1.0 - midpoint
				return 0.5 + 0.5 * seg_pos / midpoint

		if self.opacitystops[left].interpolation == "curved":
			factor = pow(seg_pos, log(0.5) / log(midpoint))
		elif self.opacitystops[left].interpolation == "sine":
			factor = (sin ((-pi / 2.0) + pi * linear(seg_pos,midpoint)) + 1.0) / 2.0
		elif self.opacitystops[left].interpolation == "sphere_increasing":
			factor = sqrt (1.0 - (linear(seg_pos,midpoint)-1.0) * (linear(seg_pos,midpoint)-1.0))
		elif self.opacitystops[left].interpolation == "sphere_decreasing":
			factor = 1.0 - sqrt(1.0 - linear(seg_pos,midpoint) * linear(seg_pos,midpoint))
		else:
			factor = linear(seg_pos,midpoint)

		return self.opacitystops[left].opacity + (self.opacitystops[right].opacity - self.opacitystops[left].opacity) * factor

	def imageRGB(self,width,height,prof_out=False):
		# Color
		image = Image.new('RGB', (width,height))
		draw = ImageDraw.Draw(image)
		for i in range(width):
			try:
				r,g,b = self.colorAt(float(i)/width)
			except TypeError:
				r,g,b = (218, 218, 218)
			draw.line((i, 0, i, image.size[1]), fill=(int(round(r*0xFF)),int(round(g*0xFF)),int(round(b*0xFF))))
		del draw
		sRGB = ImageCms.createProfile("sRGB")
		if prof_out:
			outputProfile = prof_out
		else:
			outputProfile = sRGB
		new_image = ImageCms.profileToProfile(image,sRGB,outputProfile)
		# Opacity
		if len(self.opacitystops) > 0:
			alpha = Image.new('L', (width,height))
			draw = ImageDraw.Draw(alpha)
			for i in range(width):
				try:
					a = self.alphaAt(float(i)/width)
				except TypeError:
					a = 1
				draw.line((i, 0, i, image.size[1]), fill=int(round(a*0xFF)))
			del draw
			new_image.putalpha(alpha)
		return new_image

class ColorStop(object):
	def __init__(self):
		self.position = False
		self.color = False
		self.interpolation = False
		self.args = {}

class OpacityStop(object):
	def __init__(self):
		self.position = False
		self.opacity = False
		self.interpolation = False
		self.args = {}
