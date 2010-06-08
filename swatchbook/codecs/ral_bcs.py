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

from swatchbook.codecs import *

class ral_bcs(SBCodec):
	"""RAL"""
	ext = ('bcs',)
	@staticmethod
	def test(file):
		file = open(file,'rb')
		data = file.read(4)
		file.close()
		if struct.unpack('b3s', data)[1].lower() in ('clf','rgb','atl'):
			return True
		else:
			return False

	@staticmethod
	def read(swatchbook,file):
		filesize = os.path.getsize(file)
		file = open(file,'rb')
		offset, sig = struct.unpack('B 3s',file.read(4))
		file.seek(offset+1, 0)
		nbcolors = struct.unpack('<H',file.read(2))[0]
		length = struct.unpack('B',file.read(1))[0]
		name_tmp = struct.unpack(str(length)+'s',file.read(length))[0].split(':')
		swatchbook.info.title = unicode(name_tmp[0].split('English_')[1],'latin1')
		if name_tmp[1].split('German_')[1] != swatchbook.info.title:
			swatchbook.info.title_l10n['de'] = unicode(name_tmp[1].split('German_')[1],'latin1')
		file.seek(1, 1)
		for i in range(nbcolors):
			item = Color(swatchbook)
			id = False
			length = struct.unpack('B',file.read(1))[0]
			if length > 0:
				x = file.tell()
				try:
					id = unicode(struct.unpack(str(length)+'s',file.read(length))[0],'utf-8')
				except UnicodeDecodeError:
					file.seek(x)
					id =  unicode(struct.unpack(str(length)+'s',file.read(length))[0],'latin1')
			item.values[('Lab',False)] = list(struct.unpack('<3f',file.read(12)))
			if sig == 'clf':
				item.usage.append('spot')
			if not id or id == '':
				id = str(item.values[('Lab',False)])
			if id in swatchbook.materials:
				if item.values[('Lab',False)] == swatchbook.materials[id].values[('Lab',False)]:
					swatchbook.book.items.append(Swatch(id))
					continue
				else:
					sys.stderr.write('duplicated id: '+id+'\n')
					item.info.title = id
					id = id+str(item.values[('Lab',False)])
			item.info.identifier = id
			swatchbook.materials[id] = item
			swatchbook.book.items.append(Swatch(id))
			if file.tell() == filesize: break
		file.close()

