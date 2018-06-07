#!/usr/bin/env python
from __future__ import with_statement, division, print_function, unicode_literals
import pygame as G
from wbbmath import TAU

def angle_to_shearamt(angle, anglediff, flip):
    if anglediff < 0:
        anglediff += 1
    angle = angle * 8 // TAU
    if angle == 0:
        angle = 8
    if angle > 4:
        angle -= 4
##    global helptxt
##    helptxt = "a=%2d  f=%s" % (angle, 'T' if flip else 'F')
    if flip:
        anglediff = -anglediff
    if angle < 3:
        return (-anglediff, 0)
    else:
        return (0, anglediff)

def shearblitx(dst, source, dest, xoffs, stripht, area=None, special_flags=0):
    """Blits a horizontal strip at a time.

dst -- destination surface
source -- source surface
dest -- (left, top) corresponding to top left of area
xoffs -- X offset between strips
stripht -- strip height
area -- source area rectangle

"""
    area = area or (0, 0, source.get_width(), source.get_height())
    num_strips = (area[3] - 1) // stripht + 1
    x, y = dest[:2]
    strip_origins = [(i * xoffs, i * stripht) for i in range(num_strips)]
    args = [((x + sx, y + sy),
             (area[0], area[1] + sy, area[2], min(area[3] - sy, stripht)))
            for (sx, sy) in strip_origins]
    for (sdest, sarea) in args:
        dst.blit(source, sdest, sarea, special_flags)
    affected_l = dest[0] + min(0, strip_origins[-1][0])
    affected_w = area[2] + abs(strip_origins[-1][0])
    affected = G.Rect(affected_l, dest[1], affected_w, area[3])
    return affected

def shearblity(dst, source, dest, yoffs, stripwid, area=None, special_flags=0):
    """Blits a vertical strip at a time.

dst -- destination surface
source -- source surface
dest -- (left, top) corresponding to top left of area
yoffs -- Y offset between strips
stripwid -- strip width
area -- source area rectangle

"""
    area = area or (0, 0, source.get_width(), source.get_height())
    num_strips = (area[2] - 1) // stripwid + 1
    x, y = dest[:2]
    strip_origins = [(i * stripwid, i * yoffs) for i in range(num_strips)]
    args = [((x + sx, y + sy),
             (area[0] + sx, area[1], min(area[2] - sx, stripwid), area[3]))
            for (sx, sy) in strip_origins]
    for (sdest, sarea) in args:
        dst.blit(source, sdest, sarea, special_flags)
    affected_t = dest[1] + min(0, strip_origins[-1][1])
    affected_h = area[3] + abs(strip_origins[-1][1])
    affected = G.Rect(dest[0], affected_t, area[2], affected_h)
    return affected
