#!/usr/bin/env python
from __future__ import division, print_function, unicode_literals
import pygame as G
from wbbmath import get_rtheta, clip_vel_to_cable, TAU, angleunit
from wbbmath import plus_gravity, nmis
from levels import solidTiles, downSolidTiles, noGrappleTiles
import chipsfx

def draw_rope(screen, ropeparts_png, x0, y0, dx, dy):
    """Draw a rope using 8x8 pixel pieces, the same way an NES would."""

    # position connection point marker first
    rects = [(x0 - 2, y0 - 2, 8, 8)]

    # swap to top-to-bottom
    absdx = abs(dx)
    if dy < 0:
        x0 += dx
        y0 += dy
        dx = -dx
        dy = -dy
    if dy < 2:
        screen.blit(ropeparts_png, rects[0][:2], G.rect.Rect(72, 0, 8, 8))
        return rects

    invslope = absdx * 256 // dy

    if invslope >= 288:
        dydt = 2 if invslope >= 768 else 4 if invslope >= 448 else 6
        framex = 5 if invslope >= 768 else 4 if invslope >= 448 else 3
        framey = 1
        dxdy = invslope * dydt
        if dx < 0:
            dxdy = -dxdy
            framex = 5 - framex
            x0 -= 8
    else:
        dydt = 8
        dxdy = invslope * dydt
        frame = (invslope + 16) >> 5
        if frame >= 2:
            frame += 1
        framex = min(4, (frame >> 1)) + 4
        framey = 0
        if dx < 0:
            dxdy = -dxdy
            framex = 8 - framex
            x0 += framex * 2 - 8
    frame = G.rect.Rect(framex << 3, framey << 3, 8, 8)
    nsegs = (dy * 2 - 1) // dydt + 1
    # flicker long ropes
    if abs(dxdy) > 256:
        nsegs -= nmis & 1

    x0 = x0 << 8
    while nsegs > 0:
        screen.blit(ropeparts_png, (x0 >> 8, y0), frame)
        rects.append((x0 >> 8, y0, 8, 8))

        # If odd number of 4-pixel segments, overlap the next
        # piece.  Otherwise, don't overlap.
        if nsegs & 1:
            x0 += dxdy // 2
            y0 += dydt // 2
            nsegs -= 1
        else:
            x0 += dxdy
            y0 += dydt
            nsegs -= 2

    screen.blit(ropeparts_png, rects[0][:2], G.rect.Rect(72, 0, 8, 8))
    return rects

def wraptest_trace(xt1, yt1, xt2, yt2):
    """Find coords of tiles along the highest 8-direction path.

base, other_end: endpoints (2-sequences)
pf: an object supporting mtplane.MetatilePlane interface

Vertical produces vertical coordinates.
Horizontal produces horizontal coordinates.

Each step is taken based on the first rule that applies:
1. Straight up, down, left, or right goes that direction.
2. Diagonally up, with |slope| > 1, goes straight up.
2. Diagonally up, with 0 < |slope| < 1, goes diagonally up.
4. Diagonally down, with |slope| < 1, goes straight out.
5. Go diagonally down.

"""
    out = [(xt1, yt1)]
    while xt1 != xt2 or yt1 != yt2:
        dx = -1 if xt1 > xt2 else 1
        dy = -1 if yt1 > yt2 else 1
        if yt1 > yt2:  # overall upward
            # if more up than sideways, don't move sideways
            if abs(xt1 - xt2) < yt1 - yt2:
                dx = 0
        else:  # overall downward
            # if more sideways than down, don't move down
            if abs(xt1 - xt2) > yt2 - yt1:
                dy = 0
            elif xt1 == xt2:
                dx = 0
        xt1 += dx
        yt1 += dy
        out.append((xt1, yt1))
        if len(out) > 100:
            break
    return out

class Rope(object):
    MIN_CABLELEN = 0

    def __init__(self, maxlen, pos, getcell, vel=None):
        self.length = self.maxlen = maxlen
        self.pos = list(pos)
        self.vel = vel or [0, 0]
        self.getcell = getcell

        # wrapkey is created from bits 5 and 4 of the horizontal and
        # vertical position of both ends of the rope.
        # Rope wrap testing is skipped when it doesn't change.
        self.wrapkey = self.get_wrapkey(pos)

    def get_wrapkey(self, ballpos):
        return ((int(ballpos[0] // 16) & 0x03) << 6
                | (int(ballpos[1] // 16) & 0x03) << 4
                | (int(self.pos[0] // 16) & 0x03) << 2
                | (int(self.pos[1] // 16) & 0x03))

    def move(self, ballpos):
        if not self.vel:
            return
        displ = [self.pos[0] - ballpos[0],
                 self.pos[1] - ballpos[1]]
        r, theta, pull = clip_vel_to_cable(displ, self.vel, self.length)
        self.vel[1] = plus_gravity(self.vel[1])
        self.pos = [displ[0] + ballpos[0] + self.vel[0],
                    displ[1] + ballpos[1] + self.vel[1]]
        if self.pos[0] < 0:
            # if hit top of play area
            self.pos[0] = 0
            self.vel[0] = 0
        if self.pos[1] >= 192 and self.vel[1] > 0:
            # if falling below
            self.pos = self.vel = self.length = None
            return

        halftilex = int(self.pos[0]) // 8
        halftiley = int(self.pos[1]) // 8
        anchortile = (halftilex // 2, halftiley // 2)
        balltile = (int(ballpos[0] // 16), int(ballpos[1] // 16))
        wraptest_near = 1 if self.pos[0] > ballpos[0] else 15
        t = (0 if halftiley < 0
             else 1 if halftiley >= 24
             else self.getcell(*anchortile))

        # hack to wrap around #5 (pole top) if anchor is to the right
        # of and above player
        wrap_include_last = (anchortile[1] < balltile[1]
                             and anchortile[0] > balltile[0]
                             and t == 5)
        rhalfTiles = (6, )
        lhalfTiles = (5, 7)
        grabTiles = set((5, 6 if displ[0] > 0 else 7))
        grabTiles.update(solidTiles)
        if self.vel[1] > 0 and self.pos[1] % 16 < 3:
            grabTiles.update(downSolidTiles)
        bhalfTiles = (5, )
        if ((t in rhalfTiles and not (halftilex & 1))
            or (t in lhalfTiles and (halftilex & 1))
            or (t in bhalfTiles and not (halftiley & 1))):
            t = 0
        if t in noGrappleTiles:
            self.vel = self.pos = None
            return
        if t in grabTiles:
            self.vel = None
##            print("latch here at (%d, %d)" % (self.pos[0], self.pos[1]))
            self.length = max(self.MIN_CABLELEN, r)

            # if hit top of near block, latch to the near corner
            upsolid = (0 <= anchortile[1] < 12
                       and self.getcell(anchortile[0], anchortile[1] - 1)
                           in solidTiles)
            facing_left = self.pos[0] < ballpos[0]
            nearsolidx = anchortile[0] + (1 if facing_left else -1)
            neartile = (self.getcell(nearsolidx, anchortile[1])
                        if 0 < anchortile[1] < 12 and 0 <= nearsolidx
                        else 0)
            nearsolid = neartile in solidTiles
            if (t in solidTiles and self.pos[1] % 16 < 3
                and not nearsolid and not upsolid):
                self.pos[0] = anchortile[0] * 16 + wraptest_near
            chipsfx.fxq('anchor')

        # test whether rope has wrapped around a block
        wrapkey = self.get_wrapkey(ballpos)
        if self.vel and wrapkey != self.wrapkey:
            self.wrapkey = wrapkey
            coords = [(x, y,
                       self.getcell(x, y) if 0 <= x and 0 <= y < 12 else None)
                      for (x, y)
                      in wraptest_trace(balltile[0], balltile[1],
                                        anchortile[0], anchortile[1])]
        else:
            coords = []
        
        if anchortile[1] > anchortile[0]:
            grabTiles.update(downSolidTiles)
        coords = [row for row in coords
                  if row[2] in grabTiles
                  and (wrap_include_last or row[0:2] != anchortile)
                  and row[0:2] != balltile]
        if coords and coords[0][2] in noGrappleTiles:
            self.pos = self.vel = 0
            return
        coords = [(16 * x
                   + max(min(wraptest_near, 7 if t in lhalfTiles else 15),
                         8 if t in rhalfTiles else 0),
                   16 * y + (8 if t in bhalfTiles else 0))
                  for (x, y, t) in coords]
        if coords:
##            print("latch wrap at %s" % repr(coords[0]))
            self.vel = None
            self.length = r - 8
            self.pos = coords[0]
            chipsfx.fxq('anchor')

