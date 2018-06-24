#!/usr/bin/env python
from __future__ import with_statement, unicode_literals
from array import array
import json
try:
    StandardError
except NameError:
    StandardError = Exception

solidTiles = frozenset([1, 2, 3, 13])
downSolidTiles = frozenset([17])
noGrappleTiles = frozenset([13])
markov = [
    0, 3, 2, 3, 4, 4, 6, 7,
    0, 0, 0, 0, 1, 13, 15, 1,
    16, 16, 16, 20, 1, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0
]

# Screen data format
# 0x0000-0xBFFF: place tile
#   yyyyxxxxtttttttt
#   y: vertical coordinate
#   x: X coordinate
#   c: tile number to place
# 0xC000-0xC00F: continue horizontal strip of last tile
#   110000000000nnnn
#   n: number of additional tiles, that is, strip length - 1

def encode_level(level):
    level = dict(level)  # defensive copy when replacing screens
    screens = level['screens']
    level['screens'] = [len(s) for s in screens]
    level = json.dumps(level, separators=(',', ':')).encode('utf-8')
    screenwords = (b
                   for s in screens
                   for w in s
                   for b in ((w >> 8) & 0xFF, w & 0xFF))
    level = b"%d\n%s%s" % (len(level), level, bytes(screenwords))
    return level

def decode_level(level):
    jsonlen, rest = level.split(b'\n', 1)
    jsonlen = int(jsonlen.decode('ascii'))
    level = json.loads(rest[:jsonlen].decode('utf-8'))
    lbytes = bytearray(rest[jsonlen:])
    lwds = (((lbytes[i] << 8) | lbytes[i + 1]
             for i in range(0, len(lbytes), 2)))
    screens = [array('H', (next(lwds) for i in range(scrlen)))
               for scrlen in level['screens']]
    level['screens'] = screens
    level['start'] = tuple(level['start'])
    return level

def load_level_col(pf, level, x, use_markov=True):
    """

pf -- MetatilePlane.instance to write back to
level -- level data structure
x -- column number

"""
    col = bytearray(12)
    tx = ty = tn = 0
    xinpage = x % 16
    try:
        page = level['screens'][x // 16]
    except IndexError:
        page = []
    for w in page:
        if w < 0xC000:
            ty = w >> 12
            tx = (w >> 8) & 0x0F
            tn = w & 0xFF
            if tx == xinpage:
                col[ty] = tn
        elif w < 0xC010:
            if tx < xinpage <= tx + (w & 0x0F):
                col[ty] = tn
    last_ty = 0
    for y, ty in enumerate(col):
        if use_markov:
            ty = ty or markov[last_ty]
        last_ty = ty
        if pf:
            pf.setcell(x, y, ty)
    return col

def load_level(pf, level):
    for x in range(32):
        load_level_col(pf, level, x)

def load_all_levels(level_filenames):
    all_levels = []
    for filename in level_filenames:
        with open(filename, 'rb') as infp:
            lvldata = infp.read()
        all_levels.append(decode_level(lvldata))
    return all_levels
