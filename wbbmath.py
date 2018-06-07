#!/usr/bin/env python
from __future__ import division
from math import pi

TAU = 64
angleunit = TAU / (2 * pi)
nmis = 0

def make_trig_tables():
    from math import sin
    global sintable, costable
    sintable = [round(256.0 * sin(i / angleunit)) / 256.0 for i in range(TAU)]
    costable = [sintable[(i + TAU // 4) % TAU] for i in range(TAU)]

def get_rtheta(balldisp):
    from math import atan2

    # An NES frame must complete in 241*341/3 = 27393 cycles.
    # Mul takes 150 and atan2 takes 380.
    # find length: 2 muls and one atan2
    theta = int(round(atan2(balldisp[1], balldisp[0]) * angleunit)) % TAU

    unit_x = costable[theta]
    unit_y = sintable[theta]
    r = unit_x * balldisp[0] + unit_y * balldisp[1]
    return (r, theta, unit_x, unit_y)

def inc_nmis():
    global nmis
    nmis = (nmis + 1) % 256

def plus_gravity(dy):
    gravity = 17 + (nmis & 1)
    return dy + gravity / 256.0

def clip_vel_to_cable(balldisp, ballvel, cablelen):
    """Clip the distance and velocity of a tethered object.

balldisp and ballvel -- LISTS (not tuples) modified in place
cablelen -- length of cable

Return a tuple (r, theta, [push vector])

"""

    # find r, theta: 2 muls and one atan2
    (r, theta, unitx, unity) = get_rtheta(balldisp)
    # clip displacement: 2 muls
    # clip velocity: 4 muls
    excessdist = r - cablelen
    pushing = None
    if excessdist > 0:
        excessdistx = excessdist * unitx
        excessdisty = excessdist * unity
        # Reduce the distance
        balldisp[0] -= excessdistx
        balldisp[1] -= excessdisty
        r = cablelen
        pushing = [excessdistx, excessdisty]

        # Cap velocity correction at 1 unit/frame^2
        # to make certain things more stable
        if excessdist > 1:
            excessdist = 1
            excessdistx = excessdist * unitx
            excessdisty = excessdist * unity
        # And reduce the velocity
        ballvel[0] -= excessdistx
        ballvel[1] -= excessdisty
    return (r, theta, pushing)

make_trig_tables()
