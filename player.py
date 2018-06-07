#!/usr/bin/env python
from __future__ import with_statement, division, print_function, unicode_literals
import pygame as G
from math import floor
from wbbmath import clip_vel_to_cable, get_rtheta, TAU, sintable, costable, angleunit
from wbbmath import plus_gravity
from rope import draw_rope, Rope
from levels import solidTiles, downSolidTiles
import chipsfx
from shearing import shearblitx, shearblity, angle_to_shearamt

VK_A = 0x80
VK_B = 0x40
VK_SELECT = 0x20
VK_START = 0x10
VK_UP = 0x08
VK_DOWN = 0x04
VK_LEFT = 0x02
VK_RIGHT = 0x01


##arms_in = [(11, 12), (12, 10), (12, 8), (12, 5), (12, 3), (11, 2), (8, 1), (6, 1), (4, 3)]
arms_out = [(4, 2), (2, 3), (1, 7), (1, 9), (3, 12), (5, 14), (6, 14), (9, 14), (11, 14)]
body_in = (9, 10)
##body_out = [(4, 15), (7, 16), (9, 17), (11, 16), (14, 15), (15, 13), (15, 10), (15, 7)]

def accelBrakeLimit(vel, maxVel, accelRate, brakeRate, vk):
    if (vk & VK_RIGHT) and vel >= 0:
        # Case 1: nonnegative velocity, accelerating positive
        vel += accelRate
        return min(vel, maxVel)
    if (vk & VK_LEFT) and vel <= 0:
        # Case 2: nonpositive velocity, accelerating negative
        vel -= accelRate
        return max(vel, -maxVel)
    if vel >= 0:
        # Case 3: velocity >= 0 and brake
        vel -= brakeRate
        return max(vel, 0)
    # Case 4: velocity < 0 and brake
    vel += brakeRate
    return min(vel, 0)


class TumblingBlock(object):
    DIR_LEFT = 0
    DIR_RIGHT = 1
    DIR_DOWN = 2
    
    def __init__(self, x, y, direction):
        self.x = x
        self.y = y
        self.direction = direction
        self.progress = 0

    def done(self):
        return self.direction is None

    def move(self):
        if self.direction in (self.DIR_RIGHT, self.DIR_LEFT):
            self.progress += 5
            if self.progress >= 256:
                self.x += 16 if self.direction == self.DIR_RIGHT else -16
                self.progress = 0
                self.direction = self.DIR_DOWN
        elif self.direction == self.DIR_DOWN:
            is_first_fall_frame = self.progress == 0
            self.progress = min(plus_gravity(self.progress), 8)
            self.y += self.progress
            yt = int(self.y // 16)
            tbelow = self.pf.getcell(self.x // 16, yt + 1) if yt < 11 else 0
            if yt >= 12:
                self.direction = None
            elif tbelow in solidTiles or tbelow in downSolidTiles:
                chipsfx.fxq('land')
                self.pf.setcell(self.x // 16, yt, 2)
                self.direction = None
            elif is_first_fall_frame:
                chipsfx.fxq('blockfall')

    def hitbox(self):
        if self.direction == self.DIR_RIGHT:
            x = self.x + self.progress // 16
        elif self.direction == self.DIR_LEFT:
            x = self.x - self.progress // 16
        elif self.direction == self.DIR_DOWN:
            x = self.x
        else:
            return None
        return (x, self.y, 16, 16)

    def draw(self, screen, camx):
        if self.direction is None:
            return []
        x = self.x - camx
        if self.direction in (self.DIR_RIGHT, self.DIR_LEFT):
            frame = self.progress
            if self.direction == self.DIR_LEFT:
                frame = 256 - frame
                x -= 16
            frame = frame * 3 // 64 + 1
            subframe = (frame % 3) - 1
            frame = frame // 3
            dstpos = (x - 2 + frame * 4, self.y - 4)
            shear = (0 if frame in (0, 4) else -subframe,
                     subframe if frame in (0, 4) else 0)
        elif self.direction == self.DIR_DOWN:
            frame = 0
            dstpos = (x - 2, int(self.y // 1) - 4)
            shear = (0, 0)
        else:
            raise NotImplementedError

        srcarea = G.rect.Rect(frame % 4 * 20, 0, 20, 20)
        if shear[1]:
            dstpos = (dstpos[0] + 2, dstpos[1] - max(0, shear[1]))
            srcarea = G.rect.Rect(srcarea[0] + 2, 0, 16, 20)
            r = shearblity(screen, self.sheet, dstpos, shear[1], 8, srcarea)
        else:
            dstpos = (dstpos[0] - shear[0] * 2, dstpos[1])
            # 7 because 7,7,6 in Python resembles 6,8,6 in NES
            r = shearblitx(screen, self.sheet, dstpos, shear[0], 7, srcarea)
        return [r]


def four_corner_collide(pf, x, y, r, with_downsolid=True):
    tlx = int((x - 8) // 16)
    tly = int((y - 8) // 16)
    dx = x - (tlx + 1) * 16
    dy = y - (tly + 1) * 16
    if dy >= 0:  # already below centerline
        with_downsolid = False

    # 1 2
    # 4 8
    coords = enumerate((tlx + x1, tly + y1)
                       for y1 in (0, 1) for x1 in (0, 1))
    blks = [(i, pf.getcell(x1, min(y1, 11)) if 0 <= x1 and 0 <= y1 else 0)
            for (i, (x1, y1)) in coords]
    blks = sum(1 << i
               if (t in solidTiles
                   or (i >= 2 and with_downsolid and t in downSolidTiles))
               else 0
               for (i, t) in blks)
    if not blks:
        return

    if blks == 0x0F:
        # F: all four blocks occupied; push all the way out
        # through the closest edge
        if dx < dy:
            return (-16, 0) if dx < -dy else (0, 16)
        else:
            return (0, -16) if dx < -dy else (16, 0)

    # If the object's center isn't already embedded in a cell, and
    # its bounding box doesn't straddle a cell boundary, copy the
    # cells in the row or column where it is to the row or column
    # where it isn't.  This way, blks represents only the contour
    # within the object's bounding box.  insideblk is as follows:
    # 0 1
    # 2 3
    insideblk = (1 if dx >= 0 else 0) | (2 if dy >= 0 else 0)
    embedded = (1 << insideblk) & blks
    if not embedded:
        if dx <= -r:
            blks = (blks & 0x05)
            blks |= (blks << 1)
        elif dx >= r:
            blks = (blks & 0x0A)
            blks |= (blks >> 1)
        if dy <= -r:
            blks = (blks & 0x03)
            blks |= (blks << 2)
        elif dy >= r:
            blks = (blks & 0x0C)
            blks |= (blks >> 2)
        if not blks:
            return

    # If there's only one block, and it's the opposite corner from
    # the insideblk, push out of the corner
    if blks == (8 >> insideblk):
        if dx * dx + dy * dy > r * r:
            return
        return (1 if dx > 0 else -1,
                1 if dy > 0 else -1)

    # Handle 1-corner and checkerboard configurations by
    # placing a block in the opposite corner.
    if blks in (1, 8, 9):
        # Find opposite corner across \ from top left to bottom right
        blks |= 4 if dx > dy else 2
    elif blks in (2, 4, 6):
        # Find opposite corner across / from top right to bottom left
        blks |= 1 if dx > -dy else 8
    assert blks not in (0, 1, 2, 4, 6, 8, 9, 15)

    # remain:
    # 3, 7, B: push down
    # 5, 7, D: push right
    # A, B, E: push left
    # C, D, E: push up
    pushx, pushy = 0, 0
    if (blks & 0x05) == 0x05:
        pushx = r - dx  # Right
    elif (blks & 0x0A) == 0x0A:
        pushx = -r - dx  # Left
    if (blks & 0x03) == 0x03:
        pushy = r - dy  # Down
    elif (blks & 0x0C) == 0x0C:
        pushy = -r - dy  # Up
    assert pushx or pushy
    return pushx, pushy

class Player(object):
    ST_WALKING = 0  # walking or falling from walking or shooting
    ST_BLOCK_MANIP = 1  # holding A for block manipulation
    ST_PREPULLING = 2
    ST_FALLING = 3  # falling or hanging from rope
    ST_ON_SWINGBAR = 4  # hanging from fixed bar
    ST_PUSHING = 5
    ST_PULLING = 6
    ST_LADDER_SIDE = 7
    ST_LADDER_BACK = 8
    ST_CLIMBING = 9 # climbing up 1 block
    ST_ENTERING_DOOR = 10
    ST_FALLING_ROT_TEST = 32

    WALK_SPD = 106  # speed limit in 1/256 px/frame
    BACK_SPD = 64
    WALK_ACCEL = 4  # movement acceleration in 1/256 px/frame^2
    WALK_BRAKE = 8  # stopping acceleration in 1/256 px/frame^2

    MAX_CABLELEN = 48
    # until the introduction of INCLUDED_LEN, there were severe
    # numerical problems with cablelen below 8

    OUTSTRETCHED_LEN = 20  # length of outstretched arm
    INCLUDED_LEN = 12  # length of rope included in ballpos

    def __init__(self):
        self.ballpos = [40, 170]
        self.ballvel = [0, 0]
        self.rope = None
        self.theta = self.armangle = 0
        self.state = self.ST_WALKING
        self.facing_left = False
        self.walking_frame = 0
        self.has_rope = False
        self.downsolid_y = 0  # Ignore down-solid tiles above this (0-11)

##        self.ballpos = [128, 64]
##        self.state = self.ST_FALLING_ROT_TEST

    def get_hanging_hotspot_chain(self):
        # 0: facing up; TAU/2: facing forward; TAU: facing down
        theta = ((TAU * 3 // 2) - self.theta if self.facing_left else self.theta) % TAU

        armangle = (int(self.armangle // 4) + theta) % TAU
        bodyangle = (theta - int(self.armangle)) % TAU
        armangle16 = (armangle * 16 + TAU // 2) // TAU
        bodyangle16 = (bodyangle * 16 + TAU // 2) // TAU
        arm_frame = (10 - armangle16) % 16
        body_frame = (6 - bodyangle16) % 16

        # shear the body for maximum smoothness
        bodyshear = angle_to_shearamt(bodyangle, bodyangle - bodyangle16 * 4, self.facing_left)
        armshear = angle_to_shearamt(armangle, armangle - armangle16 * 4, self.facing_left)

        # find arm joints
        out = arms_out[arm_frame % 8]
        if arm_frame >= 8:
            out = (15 - out[0], 15 - out[1])
        truearmangle = (armangle + TAU // 32) % TAU
##        truearmangle = armangle % TAU
        in_ = (out[0] - int(round(11 * costable[truearmangle])),
               out[1] - int(round(13 * sintable[truearmangle])))
        
        # find body joints
        in2 = body_in
        if body_frame >= 8:
            in2 = (19 - in2[0], 21 - in2[1])
        out2 = (in2[0] + int(round(6 * costable[bodyangle])),
                in2[1] + int(round(7 * sintable[bodyangle])))

        if self.facing_left:
            in_ = (15 - in_[0], in_[1])
            out = (15 - out[0], out[1])
            in2 = (19 - in2[0], in2[1])
            out2 = (19 - out2[0], out2[1])

        # Our nemesis is the roughly 8 pixel steps between
        # total_offset values from one frame to the next.
        # I solved this in part with INCLUDED_LEN, which puts
        # ballpos closer to the center of mass.
        thetawrap = self.theta % TAU
        in_ = (in_[0] + costable[thetawrap] * self.INCLUDED_LEN,
               in_[1] + sintable[thetawrap] * self.INCLUDED_LEN)

        total_offset = (out2[0] - in2[0] + out[0] - in_[0],
                        out2[1] - in2[1] + out[1] - in_[1])
        return (arm_frame, body_frame, in_, out, in2, out2, armshear, bodyshear, total_offset)

    def bash_block(self, buttpos):
        """Bash a block forward.

buttpos -- (x, y) position of hammer in pixels

"""
        fwd = 1 if self.ballvel[0] > 0 else -1
        xt = int(buttpos[0] // 16) + fwd
        yt = int(buttpos[1] // 16)
        if (self.rope and not self.rope.vel and self.rope.pos
            and xt == int(self.rope.pos[0] // 16)
            and yt == int(self.rope.pos[1] // 16)):
            print("deanchoring from bashed block")
            self.rope = None
        self.spawn_tumbling_block(xt, yt, fwd < 0)

    def four_corner_collision(self):
        hhsc = self.get_hanging_hotspot_chain()
        total_offset = hhsc[-1]
        buttpos = (self.ballpos[0] + total_offset[0],
                   self.ballpos[1] + total_offset[1])
        with_downsolid = (buttpos[1] + 4 >= self.downsolid_y * 16
                          and self.ballvel[1] >= 0)
        colr = four_corner_collide(self.pf, buttpos[0], buttpos[1], 5, with_downsolid)

        if colr:
            (dirx, diry) = colr
            if dirx:  # hit block to left or right
                if abs(self.ballvel[0]) > .5:
                    chipsfx.fxq('land')
                if ((self.ballvel[0] > 1 and dirx < 0)
                    or (self.ballvel[0] < -1 and dirx > 0)):
                    self.bash_block((buttpos[0] + dirx, buttpos[1] + 2))
                self.ballpos[0] += dirx
                self.ballvel[0] = (min(0, self.ballvel[0])
                                   if dirx < 0
                                   else max(0, self.ballvel[0]))
                self.ballvel[1] -= self.ballvel[1] / 8  # drag
            if diry:  # hit block up or down
                self.downsolid_y = 0
                if abs(self.ballvel[1]) > .5:
                    chipsfx.fxq('land')
                self.ballpos[1] += diry
                self.ballvel[1] = (min(0, self.ballvel[1])
                                   if diry < 0
                                   else max(0, self.ballvel[1]))
                self.ballvel[0] -= self.ballvel[0] / 8
        buttpos = (self.ballpos[0] + total_offset[0],
                   self.ballpos[1] + total_offset[1])
        return (colr, buttpos)

    def falling_to_walking(self):
        # and proceed to walking state
        hhsc = self.get_hanging_hotspot_chain()
        total_offset = hhsc[-1]
        self.ballpos[0] += total_offset[0]
        self.ballpos[1] += total_offset[1]
        self.state = self.ST_WALKING
        bodyangle = int(self.armangle) + (self.theta if self.facing_left else TAU // 2 - self.theta)
        bodyangle = bodyangle * 32 // TAU
        if bodyangle >= 24:
            bodyangle -= 32
        bodyangle = max(min(bodyangle - 8, 2), -2)
        bodyangle = (6 - bodyangle) % 6
        self.walking_frame = 256 * bodyangle

    def move_swinging(self, vkeys, new_vkeys):
        balldisp = [self.ballpos[0] - self.rope.pos[0],
                    self.ballpos[1] - self.rope.pos[1]]
        restrict_len = self.rope.maxlen if vkeys & VK_DOWN else self.rope.length
        r, theta, pullamt = clip_vel_to_cable(balldisp, self.ballvel,
                                              restrict_len + self.INCLUDED_LEN)
        r -= self.INCLUDED_LEN

        # If at end of rope, rotate
        if r >= self.rope.length - 1:
            thetadiff = ((theta - self.theta) + (TAU // 2)) % TAU - TAU // 2
            thetadiff = max(-TAU // 32, min(TAU // 32, thetadiff))
            self.theta = (self.theta + thetadiff) % TAU

        self.ballpos = [balldisp[0] + self.rope.pos[0],
                        balldisp[1] + self.rope.pos[1]]

        # 2012-12-10: This part held up development for months while
        # I waited for good weather to make a reference video for how
        # the hand's position should respond to armangle movement.
        # armangle_delta is in units 1/TAU turns per frame, or
        # 1/angleunit radians per frame.
        armangle_max = TAU * 3.0 / 16.0
        if vkeys & (VK_LEFT if self.facing_left else VK_RIGHT):
            armangle_delta = TAU * 3.0 / 512.0
        else:
            armangle_delta = -TAU * 3.0 / 256.0
        armangle_delta = min(armangle_delta, armangle_max - self.armangle)
        armangle_delta = max(armangle_delta, -self.armangle)
        com_dir = self.armangle + .5 * armangle_delta + (TAU // 4)
        # here: com_dir is the forward direction of the center of mass
        # relative to the facing direction
        self.armangle += armangle_delta

        com_dir = self.theta + (com_dir if self.facing_left else -com_dir)
        com_dir = int(round(com_dir)) % TAU
        # here: com_dir is the forward direction of the center of mass
        # relative to the ground
        move_amt = -armangle_delta * 6 / angleunit
        self.ballpos[0] += move_amt * costable[com_dir]
        self.ballpos[1] += move_amt * sintable[com_dir]

        # Ground clearance
        if self.walking_frame > 0:
            self.walking_frame -= 1
            vkeys |= VK_UP

        if (new_vkeys & VK_UP) and r <= self.rope.MIN_CABLELEN + 1:
            if self.move_swinging_press_up():
                return
        elif vkeys & VK_UP:

            self.rope.length = max(self.rope.MIN_CABLELEN, r - 0.25)
        if (new_vkeys & VK_DOWN) and self.rope.length >= self.MAX_CABLELEN:
            # down at maximum length: let go
            self.rope = None
        elif vkeys & VK_DOWN:
            self.rope.length = max(self.rope.MIN_CABLELEN, min(self.MAX_CABLELEN, r + 1))
        if new_vkeys & VK_A:
            # A: let go
            self.rope = None
        if self.rope is None:
            self.state = self.ST_FALLING
        self.ballvel[1] = plus_gravity(self.ballvel[1])
        self.ballpos[0] += self.ballvel[0]
        self.ballpos[1] += self.ballvel[1]

        # terrain collision
        colr, buttpos = self.four_corner_collision()
        if self.ballvel[1] < 0:
            self.downsolid_y = min(self.downsolid_y, 1 + int((buttpos[1] + 5) // 16))

        # when in contact with floor, snap to sideways
        if colr and colr[1] < 0:
            if vkeys & VK_DOWN:
                xt = int(buttpos[0] // 16)
                yt = int(buttpos[1] // 16) + 1
                is_downsolid = (0 <= yt < 12 and 0 <= xt
                                and self.pf.getcell(xt, yt) in downSolidTiles)
                if is_downsolid:
                    # Down while anchored and resting on down-solid
                    # tile: drop through
                    self.downsolid_y = yt + 1
                elif new_vkeys & VK_DOWN:
                    self.falling_to_walking()
            if self.theta > TAU // 2:
                # Snap to horizontal, and compensate for movement
                # in the hitbox caused by snapping to horizontal
                self.ballpos[1] += 4 * sintable[self.theta]
                self.theta = TAU // 2 if self.theta < 3 * TAU // 4 else 0

        # relieve cable tension so that player is not snapped through
        # a wall should the rope pass in front of one
        if self.rope and colr and pullamt:
            tensions1 = max(abs(colr[0] + pullamt[0]), abs(colr[1] + pullamt[1]))
            if tensions1 >= 4:
                self.rope.length += tensions1 // 2
                if self.rope.length > self.MAX_CABLELEN:
                    print("snapped!")
                    self.rope = None

    def move_falling(self, vkeys, new_vkeys):
        if self.rope and not self.rope.vel:
            return self.move_swinging(vkeys, new_vkeys)
            
        if self.armangle > 2:
            self.armangle -= 2
            self.theta += 1 if self.facing_left else -1

        self.ballvel[1] = plus_gravity(self.ballvel[1])
        self.ballpos[0] += self.ballvel[0]
        self.ballpos[1] += self.ballvel[1]
        if self.ballpos[0] < 0:
            self.ballpos[0] = self.ballvel[0] = 0

        oldxvel = self.ballvel[0]
        colr, buttpos = self.four_corner_collision()
        if colr:
            if colr[1] < 0:
                self.falling_to_walking()
            elif colr[0] and 0 < self.theta < TAU // 2:
                dtheta = (TAU // 4 - self.theta)
                self.theta += dtheta // 2

        if (0 < self.ballpos[1] < 192
            and (vkeys & (VK_UP | VK_DOWN))):
            tox = int(self.ballpos[0] // 16)
            toy = int(self.ballpos[1] // 16)
            totile = self.pf.getcell(tox, toy)
            toxhalf = int(self.ballpos[0] // 8) % 2
            if (totile == (7 if self.facing_left else 6)
                and toxhalf == (0 if self.facing_left else 1)):
                self.get_onto_ladder()
                return

        if (new_vkeys & VK_A) and self.has_rope and not self.rope:
            self.shoot_rope(vkeys)

    def move_falling_rot_test(self, vkeys, new_vkeys):
        vkeysdir = vkeys & (VK_UP | VK_DOWN | VK_LEFT | VK_RIGHT)
        self.walking_frame = (self.walking_frame + 1
                              if vkeys & vkeysdir
                              else 0)
        if self.walking_frame >= 14:
            self.walking_frame = 12
        if self.walking_frame in (1, 13):
            if vkeys & VK_UP:
                self.armangle = min(TAU // 4, self.armangle + 0.5)
            if vkeys & VK_DOWN:
                self.armangle = max(0, self.armangle - 0.5)
            if vkeys & VK_LEFT:
                self.theta -= 1
            if vkeys & VK_RIGHT:
                self.theta += 1
        if new_vkeys & VK_A:
            self.facing_left = not self.facing_left

    def spawn_tumbling_block(self, xcell, ycell, to_left):
        from levels import markov

        if not (0 <= xcell and 0 <= ycell < 12):
            print("no tumble if out of bounds")
            return False
        tilehere = self.pf.getcell(xcell, ycell)
        if tilehere != 2:
            if tilehere in solidTiles or tilehere in downSolidTiles:
                print("tile %d does not tumble" % tilehere)
            else:  # must've hit the air above the tile
                print("hit the corner")
            return False
        blockingTiles = solidTiles | frozenset([5, 12, 14, 15])
        tile_above = self.pf.getcell(xcell, ycell - 1) if ycell > 0 else 0
        if tile_above in blockingTiles:
            print("no tumble if something is on top")
            return False
        xdst = xcell + (-1 if to_left else 1)
        tile_dst = self.pf.getcell(xdst, ycell)
        if xdst < 0 or tile_dst in blockingTiles:
            print("no tumble if destination blocked")
            return False
        tile_fabove = self.pf.getcell(xdst, ycell - 1) if xdst >= 0 and ycell > 0 else 0
        tile_pred = markov[tile_fabove] if tile_fabove < len(markov) else 0
        if tile_dst != tile_pred:
            print("no tumble if prediction mismatch: %d != expected %d below %d"
                  % (tile_dst, tile_pred, tile_fabove))
            return False

        tumble_dir = TumblingBlock.DIR_LEFT if to_left else TumblingBlock.DIR_RIGHT
        t = TumblingBlock(xcell * 16, ycell * 16, tumble_dir)
        t.pf = self.pf
        self.pf.setcell(xcell, ycell, markov[tile_above] if tile_above < len(markov) else 0)
        self.pf.tumble.append(t)
        return True

    def shoot_rope(self, vkeys=0):
        if self.state == self.ST_LADDER_SIDE:
            pos = [self.ballpos[0], self.ballpos[1] - 8]
            vel = [2.75 if self.facing_left else -2.75, -2.75]
        elif self.state == self.ST_WALKING:
            vkey_fwd = VK_LEFT if self.facing_left else VK_RIGHT
            shoot_dir = vkeys & (VK_UP | VK_DOWN | vkey_fwd)
            if shoot_dir & VK_DOWN:
                vel = [4, 0]
            elif shoot_dir == VK_UP:
                vel = [0, -4]
            elif shoot_dir & VK_UP:
                vel = [2, -3.5]
            else:
                vel = [2.75, -2.75]
            if self.facing_left:
                vel[0] = -vel[0]
            pos = [self.ballpos[0], self.ballpos[1] - 8]
        else:
            vk_ud = vkeys & (VK_UP | VK_DOWN)
            vk_lr = vkeys & (VK_LEFT | VK_RIGHT)
            if not (vk_ud or vk_lr):
                vk_ud = VK_UP
                vk_lr = VK_LEFT if self.facing_left else VK_RIGHT
            amt = 2.75 if vk_ud and vk_lr else 4
            vel = [self.ballvel[0]
                   + (amt if vk_lr & VK_RIGHT else -amt if vk_lr else 0),
                   self.ballvel[1]
                   + (amt if vk_ud & VK_DOWN else -amt if vk_ud else 0)]
            pos = [self.ballpos[0], self.ballpos[1]]
        self.rope = Rope(self.MAX_CABLELEN, pos, self.pf.getcell, vel)
        chipsfx.fxq('launch')

    def pushing_neighborhood(self):
        # Find pixel associated with front of character
        fwd = -1 if self.facing_left else 1
        x = int(floor(self.ballpos[0])) + 4 * fwd
        xt = x // 16
        if xt + fwd < 0:  # fail if off map edge
            print("tile in front is off map edge")
            return None
        dist_fwd = x % 16
        if not self.facing_left:
            dist_fwd = 16 - dist_fwd
        y = int(floor(self.ballpos[1]))
        yt = y // 16
        getcell = self.pf.getcell
        tile_f = getcell(xt + fwd, yt)
        if tile_f != 2:
            print("tile in front is not a crate")
            return None
        tile_fu = (0 if yt == 0 else getcell(xt + fwd, yt - 1))
        if tile_fu in solidTiles:
            print("tile above crate is solid")
            return None
        xt_front_back = [xt + 2 * fwd, xt - fwd]
        dest_open = [(xtd >= 0 and getcell(xtd, yt) not in solidTiles)
                     for xtd in xt_front_back]

        return (xt, yt, dist_fwd, dest_open)

    def move_walking_press_A(self, vkeys):
        if self.rope:
            # A: withdraw rope
            self.rope = None
            return

        neighborhood = self.pushing_neighborhood()
        if neighborhood:
            xt, yt, dist_fwd, dest_open = neighborhood
            dest_open = dest_open[1 if vkeys & VK_DOWN else 0]
            can_reach_crate = dist_fwd < 6
            want_pushpull = vkeys & VK_DOWN or can_reach_crate
        else:
            want_pushpull = 0

        # A: pushing a block
        if want_pushpull:
            if vkeys & VK_DOWN:
                return self.try_pushing(True, neighborhood)
            chipsfx.fxq('steplift')
            self.state = self.ST_BLOCK_MANIP
            self.walking_frame = 0
        elif self.state == self.ST_PREPULLING:
            self.state = self.ST_WALKING
        elif self.has_rope and not self.rope:
            self.shoot_rope(vkeys)

    def try_pushing(self, is_pull=False, neighborhood=None):
        neighborhood = neighborhood or self.pushing_neighborhood()
        if not neighborhood:
            return
        xt, yt, dist_fwd, dest_open = neighborhood
        if not any(dest_open):
            return
        fwd = -1 if self.facing_left else 1
        if is_pull:
            if not dest_open[1]:
                return
            # Don't pull block if no solid ground behind player
            below_dest_tile = (self.pf.getcell(xt - fwd, yt + 1)
                               if yt < 11 and xt - fwd >= 0
                               else 0)
            below_dest_solid = (below_dest_tile in solidTiles
                                or below_dest_tile in downSolidTiles)
            if not below_dest_solid:
                print("not backing onto nonsolid tile %d at (%d, %d)"
                      % (below_dest_tile, xt - fwd, yt + 1))
                return
            if dist_fwd < 12:
                self.state = self.ST_PREPULLING
            elif self.spawn_tumbling_block(xt + fwd, yt, not self.facing_left):
                self.state = self.ST_PULLING
                self.rope = None
                self.walking_frame = 0
                self.ballpos[0] -= (16 - dist_fwd) * fwd
                chipsfx.fxq('climb')
            return
        if dest_open[0] and self.spawn_tumbling_block(xt + fwd, yt, self.facing_left):
            self.state = self.ST_PUSHING
            self.rope = None
            self.walking_frame = 0
            self.ballpos[0] += dist_fwd * fwd
            chipsfx.fxq('climb')

    def move_walking_press_down(self):

        # Down: tug on a rope to pull a block
        if self.ballvel[1] != 0 or not self.rope or self.rope.vel:
            return  # requires standstill and an anchored rope
        dx = self.ballpos[0] - self.rope.pos[0]
        if abs(dx) < 24:  # too close
            return
        xt = int(self.rope.pos[0] // 16)
        yt = int(self.rope.pos[1] // 16)

        if self.spawn_tumbling_block(xt, yt, dx < 0):
            self.rope = None
            facing_away = self.facing_left if dx < 0 else not self.facing_left
            self.state = self.ST_PUSHING if facing_away else self.ST_PULLING
            chipsfx.fxq('climb')
            self.walking_frame = 0

    def get_onto_ladder(self):
        self.state = self.ST_LADDER_SIDE
        self.ballvel = [0, 0]
        self.walking_frame = 0
        self.rope = None
        self.ballpos = [self.ballpos[0] // 16 * 16 + 8, self.ballpos[1] // 8 * 8 + 3]

    def move_walking_press_up(self, vkeys, bothwalltile=None):
        if bothwalltile == 15:
            chipsfx.fxq('steplift')
            self.state = self.ST_ENTERING_DOOR
            self.walking_frame = 0
            return
        if bothwalltile == (7 if self.facing_left else 6):
            self.get_onto_ladder()
            return
        fwd = -1 if self.facing_left else 1
        x = int(floor(self.ballpos[0])) + 4 * fwd
        y = int(floor(self.ballpos[1]))
        xt = x // 16
        yt = y // 16
        dist_fwd = (x if self.facing_left else 15 - x) % 16

        if xt + fwd < 0 or yt < 1:
            return

        getcell = self.pf.getcell
        tile_f = getcell(xt + fwd, yt)
        tile_u = getcell(xt, yt - 1)
        tile_fu = getcell(xt + fwd, yt - 1)

        # up: climb
        if (dist_fwd < 6
            and (tile_f in solidTiles or tile_f in downSolidTiles)
            and tile_u not in solidTiles and tile_fu not in solidTiles):
            self.begin_climbing(self.ballpos[0] // 16, self.ballpos[1] // 16)

    def move_swinging_press_up(self):
        if not self.rope:
            return False
        total_offset = self.get_hanging_hotspot_chain()[-1]
        buttx = (self.ballpos[0] + total_offset[0])
        butty = (self.ballpos[1] + total_offset[1])
        del total_offset

        fromx = int(buttx // 16)
        fromy = int(butty // 16)
        tox = int(self.rope.pos[0] // 16)
        toy = int(self.rope.pos[1] // 16)
        if not (0 <= tox and 0 <= toy < 12):
            print("climb: coords out of bounds")
            return False
        totile = self.pf.getcell(tox, toy)
        toxhalf = int(self.rope.pos[0] // 8) % 2
        if (totile == (7 if self.facing_left else 6)
            and toxhalf == (0 if self.facing_left else 1)):
            self.ballpos = [tox * 16 + 8, int(butty // 8) * 8 + 3]
            self.get_onto_ladder()
            return True
        elif totile == 5:
            print("latched at top of pole:", self.rope.pos)
            self.walking_frame = 0
            ropepos = self.rope.pos if self.rope else [self.ballpos[0], self.ballpos[1] - self.INCLUDED_LEN]
            ropepos = [c // 8 * 8 + 2 for c in ropepos]
            self.ballpos = [ropepos[0] + costable[self.theta] * self.INCLUDED_LEN,
                            ropepos[1] + sintable[self.theta] * self.INCLUDED_LEN]
            self.rope = Rope(0, ropepos, self.pf.getcell)
            self.rope.vel = None
            self.state = self.ST_ON_SWINGBAR
            return False
        elif totile not in solidTiles and totile not in downSolidTiles:
            print("climb: not solid")
            return False
        snap_to_side = True
        if fromx == tox and fromy == toy + 1:
            if totile in downSolidTiles:
                print("climb onto down-solid tile")
                snap_to_side = False
            else:
                print("from a tile to the same tile %d" % totile)
                return False
        if self.rope.pos[1] - toy * 16 >= 4:
            print("climb: anchor not at top of tile")
            return False

        print("want to climb to %d, %d" % (tox, toy))
        dx = 1 if self.rope.pos[0] // 16 * 16 + 8 > buttx else -1
        if snap_to_side and dx != (-1 if self.facing_left else 1):
            print("climb: facing wrong way")
            return False
        if fromx == tox:
            fromx -= dx
        coords = [(fromx, y) for y in range(max(fromy, toy), toy - 1, -1)]
        coords.extend((x, toy - 1) for x in range(fromx, tox + dx, dx))
        if any(self.pf.getcell(x, y) in solidTiles
               for (x, y) in coords
               if 0 <= x and 0 <= y < 12):
            print("climb: tiles in way")
            return False
        self.rope = None
        self.begin_climbing(tox - dx, toy, snap_to_side)
        return True

    def move_pushing(self):
        self.walking_frame += 20
        if self.walking_frame >= 4*256:
            self.walking_frame = 128
            self.state = self.ST_WALKING
            self.ballvel[0] = 0

    def move_pulling(self):
        self.walking_frame += 15
        if self.walking_frame >= 3*256:
            self.walking_frame = 128
            self.state = self.ST_WALKING
            self.ballvel[0] = 0

    def move_block_manip(self, vkeys, new_vkeys):
        if new_vkeys & VK_RIGHT:
            return self.try_pushing(self.facing_left)
        if new_vkeys & VK_LEFT:
            return self.try_pushing(not self.facing_left)
        if new_vkeys & VK_DOWN:
            self.state = self.ST_WALKING
            return
        if not vkeys & VK_A:
            self.state = self.ST_WALKING
            self.try_pushing(False)

    def move_entering_door(self):
        self.walking_frame = min(self.walking_frame + 32, 1024)

    def move_climbing(self):
        fwd = -1 if self.facing_left else 1
        if self.walking_frame < 2*256:
            self.walking_frame += 64
            if self.walking_frame >= 2*256:
                chipsfx.fxq('climb')
        else:
            self.walking_frame += 32
        if self.walking_frame >= 7*256:
            self.ballpos[0] += 5 * fwd
            self.ballpos[1] -= 16
            self.ballvel = [self.WALK_SPD * fwd / 256.0, 0]
            self.state = self.ST_WALKING
            self.walking_frame = 3*256
            chipsfx.fxq('steplift')

    def begin_climbing(self, xt, yt, snap_to_side=True):
        x = (xt * 16 + (5 if self.facing_left else 11)
             if snap_to_side
             else self.ballpos[0] + (4 if self.facing_left else -4))
        self.ballpos = [x, yt * 16 + 11]
        self.state = self.ST_CLIMBING
        self.walking_frame = 0

    def move_on_ladder_side(self, vkeys, new_vkeys):
        fwd = -1 if self.facing_left else 1

        if self.ballvel[1] == 0 and (vkeys or new_vkeys):
            getcell = self.pf.getcell
            xt = int(self.ballpos[0] // 16)
            if vkeys & VK_UP:
                yt = int((self.ballpos[1] - 16) // 16)
                tile_u = getcell(xt, yt) if yt >= 0 else 0
                tile_fu = getcell(xt + fwd, yt) if yt >= 0 else 0
                tile_f = getcell(xt + fwd, min(11, yt + 1))
                if tile_u in (6, 7):
                    self.ballvel = [0, -3/16]
                elif (tile_u not in solidTiles and tile_fu not in solidTiles
                      and (tile_f in solidTiles or tile_f in downSolidTiles)):
                    self.begin_climbing(xt, yt + 1)
                    return
            elif vkeys & VK_DOWN:
                yt = int((self.ballpos[1] + 8) // 16)
                tile_d = getcell(xt, yt) if yt < 12 else 0
                if tile_d in (6, 7):
                    self.ballvel = [0, 3/16]
                elif tile_d in solidTiles or tile_d in downSolidTiles:
                    self.state = self.ST_WALKING
            elif new_vkeys & VK_A:
                if self.rope:
                    self.rope = None
                elif self.has_rope:
                    self.shoot_rope()
            elif (new_vkeys & (VK_RIGHT if self.facing_left else VK_LEFT)
                  and self.rope and not self.rope.vel):
                self.change_walking_to_swinging()
                return

        self.ballpos[1] += self.ballvel[1]
        self.walking_frame += int(128 * abs(self.ballvel[1]))
        if self.walking_frame >= 1024:
            self.walking_frame = 0
            self.ballvel = [0, 0]
            self.ballpos[1] = self.ballpos[1] // 8 * 8 + 3

    def change_walking_to_swinging(self):
        if not self.rope:
            return False

        adjust_len = self.OUTSTRETCHED_LEN - self.INCLUDED_LEN
        balldisp = [self.ballpos[0] - self.rope.pos[0],
                    self.ballpos[1] - self.rope.pos[1] - adjust_len]
        (r, theta, unitx, unity) = get_rtheta(balldisp)
        r -= self.INCLUDED_LEN

        # If already near the top of the rope, and player is facing
        # anchor, and player isn't backing away from anchor, climb
        at_top = r < self.rope.MIN_CABLELEN / 2
        facing_anchor = (balldisp[0] if self.facing_left else -balldisp[0]) > 0
        not_backing = (-self.ballvel[0] if self.facing_left else self.ballvel[0]) >= 0
        if at_top and facing_anchor and not_backing:
            print("autoclimb")
            if self.move_swinging_press_up():
                return True
##        self.theta = theta
        self.theta = TAU // 4

        # 2013-02-08: jero32 suggested giving a little ground
        # clearance when scooting off a cliff toward the anchor
        if ((balldisp[0] >= 16 and self.ballvel[0] < 0)
            or (balldisp[0] <= -16 and self.ballvel[0] > 0)):
            self.armangle = TAU * 3 // 32
            self.walking_frame = 16  # reduce r by four pixels
            self.rope.length = r + adjust_len
        elif self.state == self.ST_LADDER_SIDE:
            self.rope.length = r
        else:
            self.armangle = self.walking_frame = 0
            self.rope.length = self.MAX_CABLELEN
        unitx, unity = 0, 1
        self.ballpos[1] -= unity * adjust_len
        self.ballpos[0] -= unitx * adjust_len
        self.state = self.ST_FALLING
        chipsfx.fxq('steplift')
        return True

    def do_pickup(self, x, y):
        t = self.pf.getcell(x, y)
        if t == 12:
            self.has_rope = True
            self.pf.setcell(x, y, 0)
            chipsfx.fxq('item')

    def move(self, vkeys, new_vkeys):
        if self.rope:
            self.rope.move(self.ballpos)
            if not self.rope.pos:
                self.rope = None

        if self.state == self.ST_FALLING_ROT_TEST:
            return self.move_falling_rot_test(vkeys, new_vkeys)
        if self.state == self.ST_ON_SWINGBAR:
            return self.move_swinging(vkeys, new_vkeys)
        if self.state == self.ST_FALLING:
            return self.move_falling(vkeys, new_vkeys)
        if self.state == self.ST_BLOCK_MANIP:
            return self.move_block_manip(vkeys, new_vkeys)
        if self.state == self.ST_PUSHING:
            return self.move_pushing()
        if self.state == self.ST_PULLING:
            return self.move_pushing()
        if self.state == self.ST_CLIMBING:
            return self.move_climbing()
        if self.state == self.ST_LADDER_SIDE:
            return self.move_on_ladder_side(vkeys, new_vkeys)
        if self.state == self.ST_ENTERING_DOOR:
            return self.move_entering_door()

        # 2012-06-10, suggested by tpw_rules and hcs on #nesdev:
        # Automatically back up if request to pull a block is issued
        # while too close to the block
        if self.state == self.ST_PREPULLING:
            fwd = -1 if self.facing_left else 1
            x = int(floor(self.ballpos[0])) + 4 * fwd
            dist_fwd = x % 16
            if not self.facing_left:
                dist_fwd = 16 - dist_fwd
            vkeys = VK_DOWN
            if dist_fwd < 12:
                vkeys |= VK_RIGHT if self.facing_left else VK_LEFT
            else:
                new_vkeys |= VK_A

        # don't allow walking farther than MAX_CABLELEN while the
        # rope is anchored
        if self.rope and not self.rope.vel:
            balldisp = [self.ballpos[0] - self.rope.pos[0],
                        self.ballpos[1] - self.rope.pos[1]]
            (r, theta, unitx, unity) = get_rtheta(balldisp)
            if r >= self.MAX_CABLELEN:
                if self.state == self.ST_PREPULLING:
                    self.state = self.ST_WALKING
                vkeys = VK_LEFT if balldisp[0] > 0 else VK_RIGHT

        # to turn around, you have to press a direction while stopped
        walking_backward = False
        was_stopped = self.ballvel[0] == 0 and self.ballvel[1] == 0
        vk_forward = VK_LEFT if self.facing_left else VK_RIGHT
        vk_backward = VK_RIGHT if self.facing_left else VK_LEFT
        if self.ballvel[1] == 0:
            vel = int(round(256 * self.ballvel[0]))
            if vel == 0:
                if vkeys & VK_DOWN:
                    walking_backward = vkeys & vk_backward
                elif new_vkeys & VK_LEFT:
                    self.facing_left = True
                elif new_vkeys & VK_RIGHT:
                    self.facing_left = False
            elif vel < 0 and not self.facing_left:
                walking_backward = True
            elif vel > 0 and self.facing_left:
                walking_backward = True
            topspd = self.BACK_SPD if walking_backward else self.WALK_SPD
            vel = accelBrakeLimit(vel, topspd, self.WALK_ACCEL, self.WALK_BRAKE, vkeys)
            self.ballvel[0] = vel / 256
            del vel

        self.ballpos[0] += self.ballvel[0]
        if self.ballpos[0] < 5:
            self.ballpos[0] = 5
            self.ballvel[0] = 0
        self.ballvel[1] = plus_gravity(self.ballvel[1])
        self.ballpos[1] += self.ballvel[1]
        if self.ballpos[1] < 15:
            self.ballpos[1] = 15
            self.ballvel[1] = 0

        # wall collision
        getcell = self.pf.getcell
        colltl = (int(floor(self.ballpos[0])) - 4, int(floor(self.ballpos[1])) - 11)
        collbr = (colltl[0] + 8, colltl[1] + 16)

        if 0 <= colltl[1] < 192:
            lwalltile = getcell(colltl[0] // 16, colltl[1] >> 4)
            rwalltile = getcell(collbr[0] // 16, colltl[1] // 16)
        else:
            lwalltile = rwalltile = 0
        if lwalltile == 12:
            self.do_pickup(colltl[0] // 16, colltl[1] // 16)
        elif rwalltile == 12:
            self.do_pickup(collbr[0] // 16, colltl[1] // 16)

        # in frames of the walking animation where the hands bear
        # weight, move the point of floor contact under the hands
        fwd = -1 if self.facing_left else 1
        floor_x = [0, 0, 0, 3, 0, -3, 0][min(self.walking_frame // 256, 5)]
        eff_x = (collbr[0] + colltl[0]) // 2 + floor_x * fwd
        floortile = (getcell(eff_x // 16, collbr[1] >> 4)
                     if 0 <= eff_x and 0 <= collbr[1] < 192
                     else 0)
        if rwalltile in solidTiles:
            ejectAmt = max(1, self.ballvel[0])
            self.ballpos[0] -= ejectAmt
            self.ballvel[0] = min(self.ballvel[0], 0)
            if self.state == self.ST_PREPULLING:
                self.state = self.ST_WALKING
        elif lwalltile in solidTiles:
            ejectAmt = min(-1, self.ballvel[0])
            self.ballpos[0] -= ejectAmt
            self.ballvel[0] = max(self.ballvel[0], 0)
            if self.state == self.ST_PREPULLING:
                self.state = self.ST_WALKING

        solidfloor = floortile in solidTiles or floortile in downSolidTiles
        want_swing = (self.rope and not self.rope.vel
                      and (new_vkeys & VK_UP
                           or (self.ballpos[1] > self.rope.pos[1] + 16
                               and not solidfloor)))
        if solidfloor:
            self.ballpos[1] = (collbr[1] & 0xFFF0) - 5
            if self.ballvel[1] > 0.5:
                chipsfx.fxq('land')
            self.ballvel[1] = 0
        else:
            # check for climbing ladder
            if ((lwalltile if self.facing_left else rwalltile)
                == (7 if self.facing_left else 6)
                and int(eff_x // 8) % 2 == (0 if self.facing_left else 1)):
                self.get_onto_ladder()
            
            lsolid = (getcell(colltl[0] // 16, collbr[1] >> 4) in solidTiles
                      if 0 <= collbr[1] < 192
                      else False)
            rsolid = (getcell(collbr[0] // 16, collbr[1] >> 4) in solidTiles
                      if 0 <= collbr[1] < 192
                      else False)
            # Push to side
            if lsolid:
                if self.ballvel[0] < 3./16:
                    self.ballvel[0] += 1./16
            elif rsolid:
                if self.ballvel[0] > -3./16:
                    self.ballvel[0] -= 1./16
        if want_swing and self.change_walking_to_swinging():
            self.downsolid_y = 0
            return

        # Press A to lift
        if new_vkeys & VK_A:
            if self.ballvel[1] == 0:
                self.move_walking_press_A(vkeys)
            elif self.has_rope and not self.rope:
                self.shoot_rope(vkeys)
        if self.ballvel[1] == 0 and (new_vkeys & VK_UP):
            bothwalltile = lwalltile if lwalltile == rwalltile else None
            self.move_walking_press_up(vkeys, bothwalltile)
        if self.ballvel[1] == 0 and (new_vkeys & VK_DOWN):
            self.move_walking_press_down()

        oldup = self.walking_frame // 256 in (2, 3, 4, 5)
        if self.ballvel[1] > 0:
            pass  # falling from walk
        elif self.ballvel[0] == 0:
            self.walking_frame = 128
        else:
            fvel = int(round(abs(self.ballvel[0]) * 80))
            self.walking_frame += -fvel if walking_backward else fvel
        if (not walking_backward
            and self.walking_frame // 256 == 1
            and abs(self.ballvel[0]) * 384 < self.WALK_SPD):
            self.walking_frame += 256
        newup = (self.walking_frame // 256 in (3, 4, 5)
                 or (not was_stopped) and self.walking_frame // 256 == 2)
        if oldup and not newup:
            chipsfx.fxq('step')
        elif newup and not oldup:
            chipsfx.fxq('steplift')

        # Collision with tumbling blocks
        hbxs = [_f for _f in (t.hitbox() for t in self.pf.tumble if t) if _f]
        for (hbl, hbt, hbw, hbh) in hbxs:
            hbr = hbl + hbw
            hbb = hbt + hbh
            if (hbl - 5 < self.ballpos[0] < hbr + 5
                and hbt < self.ballpos[1] < hbb):
                if self.ballpos[0] < hbl + hbw // 2:
                    self.ballpos[0] -= 1
                else:
                    self.ballpos[0] += 1

    def draw_walking(self, screen, camx=0):
        if self.walking_frame >= 7 * 256:
            self.walking_frame -= 7 * 256
        elif self.walking_frame < 0:
            chipsfx.fxq('steplift')
            self.walking_frame += 5 * 256
        f = self.walking_frame >> 8
        if f == 0 and self.ballvel[0] == 0:
            f = 8

        # skip farthest forward phase if backing up
        backing = self.ballvel[0]
        backing = (-backing if self.facing_left else backing) < 0
        if backing and 1 <= f < 6:
            f += 1
        dstx = int(self.ballpos[0]) - 8 - camx
        if f == 1:
            dstx += -2 if self.facing_left else 2
        srcarea = G.rect.Rect(f * 16, 40, 16, 24)
        dstpos = (dstx, int(self.ballpos[1] - 19))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        rects = [screen.blit(srcpic, dstpos, srcarea)]
        return rects

    def draw_climbing(self, screen, camx=0):
        fwd = -1 if self.facing_left else 1
        frame = self.walking_frame // 256
        if frame >= 7:
            frame = 0
        x = frame * 16 if frame < 6 else 32
        y = 88 if frame < 6 else 40
        dstx = int(self.ballpos[0]) - 8 + 3 * fwd - camx
        srcarea = G.rect.Rect(x, y, 16, 24)
        yoffs = (max(2, frame) - 2) * 4
        dstpos = (dstx, int(self.ballpos[1] - 19 - yoffs))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        screen.blit(srcpic, dstpos, srcarea)
        return [dstpos + (srcarea.w, srcarea.h)]

    def draw_on_ladder_side(self, screen, camx=0):
        # 2 (still), 3, 4, 1
        fwd = -1 if self.facing_left else 1
        frame = self.walking_frame // 256
        if self.ballvel[1] > 0:
            frame = 3 - frame
        yoffs = [19, 20, 21, 19][frame]
        xoffs = [0, -2, -2, 0][frame] * fwd
        frame = [2, 3, 4, 1][frame]
        x = frame * 16 if frame < 6 else 16
        y = 88 if frame < 6 else 40
        dstx = int(self.ballpos[0]) - 8 + 3 * fwd - camx + xoffs
        srcarea = G.rect.Rect(x, y, 16, 24)
        dstpos = (dstx, int(self.ballpos[1] - yoffs))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        screen.blit(srcpic, dstpos, srcarea)
        return [dstpos + (srcarea.w, srcarea.h)]

    def draw_entering_door(self, screen, camx=0):
        frame = min(2, self.walking_frame // 256)
        x = frame * 16 + 64
        y = 64
        dstx = int(self.ballpos[0] // 16) * 16 - camx
        srcarea = G.rect.Rect(x, y, 16, 24)
        dstpos = (dstx, int(self.ballpos[1] - 19))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        screen.blit(srcpic, dstpos, srcarea)
        return [dstpos + (srcarea.w, srcarea.h)]

    def draw_pushing(self, screen, camx=0):
        fwd = -1 if self.facing_left else 1
        frame = self.walking_frame // 256
        if frame >= 3:
            frame = 0
        srcarea = G.rect.Rect(frame * 16, 64, 20 if frame >= 2 else 16, 24)
        dstpos = (int(self.ballpos[0]) - 8 + (frame + 2) * 2 * fwd - camx,
                  int(self.ballpos[1] - 19))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        screen.blit(srcpic, dstpos, srcarea)
        return [dstpos + (srcarea.w, srcarea.h)]

    def draw_pulling(self, screen, camx=0):
        fwd = -1 if self.facing_left else 1
        frame = min(2, 3 - self.walking_frame // 256)
        srcarea = G.rect.Rect(frame * 16, 64, 20 if frame >= 2 else 16, 24)
        dstpos = (int(self.ballpos[0]) - 8 + (frame + 2) * 2 * fwd - camx,
                  int(self.ballpos[1] - 19))
        srcpic = self.swinging_png[1 if self.facing_left else 0]
        if self.facing_left:
            srcarea.left = srcpic.get_width() - srcarea.w - srcarea.left
        screen.blit(srcpic, dstpos, srcarea)
        return [dstpos + (srcarea.w, srcarea.h)]

    def draw(self, screen, camx=0):
        # draw rope
        if self.rope and self.rope.pos and self.rope.maxlen:
            ropeend = [self.ballpos[0], self.ballpos[1]]
            if self.state == self.ST_FALLING:
                ropeend[0] -= self.INCLUDED_LEN * costable[self.theta]
                ropeend[1] -= self.INCLUDED_LEN * sintable[self.theta]
            rects = draw_rope(screen, self.ropeparts_png,
                              int(self.rope.pos[0]) - camx,
                              int(self.rope.pos[1]),
                              int(ropeend[0] - self.rope.pos[0]),
                              int(ropeend[1] - self.rope.pos[1]))
        else:
            rects = []
        if self.state == self.ST_LADDER_SIDE:
            rects.extend(self.draw_on_ladder_side(screen, camx))
            return rects
        if self.state in (self.ST_WALKING, self.ST_PREPULLING):
            rects.extend(self.draw_walking(screen, camx))
            return rects
        if self.state in (self.ST_PUSHING, self.ST_BLOCK_MANIP):
            rects.extend(self.draw_pushing(screen, camx))
            return rects
        if self.state == self.ST_PULLING:
            rects.extend(self.draw_pulling(screen, camx))
            return rects
        if self.state == self.ST_CLIMBING:
            rects.extend(self.draw_climbing(screen, camx))
            return rects
        if self.state == self.ST_ENTERING_DOOR:
            rects.extend(self.draw_entering_door(screen, camx))
            return rects

        # draw player in swinging phase
        hhsc = self.get_hanging_hotspot_chain()
        (arm_frame, body_frame, in_, out, in2, out2, armshear, bodyshear, total_offset)\
                    = hhsc
        dstpos2 = (self.ballpos[0] - in_[0] - camx, self.ballpos[1] - in_[1])
        dstpos = (dstpos2[0] + out[0] - in2[0], dstpos2[1] + out[1] - in2[1])
        armarea = G.rect.Rect(arm_frame % 8 * 16, 24, 16, 16)
        srcarea = G.rect.Rect(body_frame % 8 * 20, 0, 20, 22)

        # select the VH flip
        hflip = 1 if self.facing_left else 0
        armflip = hflip ^ (3 if arm_frame >= 8 else 0)
        bodyflip = hflip ^ (3 if body_frame >= 8 else 0)
        armpic = self.swinging_png[armflip]
        bodypic = self.swinging_png[bodyflip]
        if armflip & 1:
            armarea.left = armpic.get_width() - (armarea.left + armarea.w)
        if armflip & 2:
            armarea.top = armpic.get_height() - (armarea.top + armarea.h)
        if bodyflip & 1:
            srcarea.left = bodypic.get_width() - (srcarea.left + srcarea.w)
        if bodyflip & 2:
            srcarea.top = bodypic.get_height() - (srcarea.top + srcarea.h)
        if bodyshear[1]:
            dstposi = (int(dstpos[0]), int(dstpos[1] - bodyshear[1]))
            r = shearblity(screen, bodypic, dstposi, bodyshear[1], 8, srcarea)
        else:
            dstposi = (int(dstpos[0] - bodyshear[0]), int(dstpos[1]))
            r = shearblitx(screen, bodypic, dstposi, bodyshear[0], 8, srcarea)
        rects.append(r)

        if armshear[1]:
            shearadj = armshear[1] if in_[0] > out[0] else 0
            dstposi = (int(dstpos2[0]), int(dstpos2[1] - shearadj))
            r = shearblity(screen, armpic, dstposi, armshear[1], 8, armarea)
        else:
            shearadj = armshear[0] if in_[1] < out[1] else 0
            dstposi = (int(dstpos2[0] - shearadj), int(dstpos2[1]))
            r = shearblitx(screen, armpic, dstposi, armshear[0], 8, armarea)
##        r = screen.blit(armpic, dstposi, armarea)
        rects.append(r)
        return rects

