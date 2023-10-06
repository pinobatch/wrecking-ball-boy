#!/usr/bin/env python3
assert str is not bytes
import pygame as G
import joycfg
from player import VK_A, VK_START, VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT
import chipsfx

# True to skip what's new and controls
skipNotices = False

# False (no video output), True (raw RGB24 frames to vtee.raw),
# or 'pipe' (through vidcap_pipe_cmd)
with_vidcap = False

# Scale video to be visible on modern monitors
# recommend 1, 2, 3, or 4
gfx_scale = 2

with_music = True

# set to something other than None to play a recorded demo
movie_filename = None
movierec_filename = 'tasrec.txt'

keybindings_filename = "wbb.kyb"
mixer_freq = 44100

# ffmpeg or avconv command line through which to pipe
# raw RGB24 pixels if with_vidcap == 'pipe'
# On my netbook, AVI with video codec "png" is a good choice for a
# lossless intermediate, as it's fairly quick to encode and not
# excessively large.
# I'm not using avconv to choose a side in the Libav/FFmpeg war;
# it's just that my development machine runs a Debian derivative and
# the maintainer of Debian's "ffmpeg" package is a Libav developer.
vidcap_pipe_cmd = r"""avconv -f rawvideo -r 30 -pix_fmt rgb24 -s "256x208" -y -an -i - -c:v png wbb.avi"""

coprNotice = """
Wrecking Ball Boy (WIP)
Copr. 2013 Damian Yerrick

New:
* No-grapple tile
* Hold A and press \x1b/\x1a to
  move a block (thx Sean)
* Enlarged key config

Planned:
* Some excuse for floors
  above floors
* Fix jam when backing up off
  cube below a ladder
  (discovered by kevtris)

Press a key"""

belowBindingsNotice = """
Ctrl+R: reset; Esc: quit

Press a key"""

controlsNotice = """
While on ground:
\x1b\x1a: scoot
A: push block  \x19+A: pull
\x18: climb block or ladder;
   enter door

With rope powerup:
A, \x18+A: shoot/drop rope
\x19: tug on rope
\x18: start swinging
\x1b\x1a on ladder: start swinging

While swinging:
\x19\x18: change rope length
\x1b\x1a: swing  A: let go
\x18 at top of rope near ladder
or top of block: climb

Press a key, then head for
the right side of the screen."""



# g = 9.80665 m/s^2 * 25 px/m * 1 s/60 f * 1 s/60 f
# which is close to 35/512 px/f
# but now using plus_gravity() in wbb_math, it's exactly 35/512

default_bindings = [
    G.K_UP, G.K_DOWN, G.K_LEFT, G.K_RIGHT,
    G.K_x, # G.K_z, G.K_TAB, G.K_RETURN
]
action_names = [
    'Up', 'Down', 'Left', 'Right',
    'A', # 'B', 'Select', 'Start'
]

VK_EOM = 0x100

last_vkeys = ~0
moviedata = None
tasrecdata = bytearray()
def read_pads():
    global last_vkeys

    # Most of the engine handles vkeys in NES order
    if moviedata:
        try:
            vkeys = next(moviedata)
        except StopIteration:
            vkeys = VK_EOM
    else:
        newbindings = (bindings[4:] + [None, None, None][:8 - len(bindings)]
                       + bindings[:4])
        vkeys = joycfg.read_pad(newbindings)
        tasrecdata.append(vkeys)
    new_vkeys = vkeys & ~last_vkeys
    last_vkeys = vkeys
    return (vkeys, new_vkeys)

def list_fields(p):
    from collections import Callable
    pd = [(n, getattr(p, n))
          for n in dir(p)
          if (not n.startswith('__')
              and n != n.upper())]
    pd = [(n, v) for (n, v) in pd if not isinstance(v, Callable)]
    print("\n".join(repr(row) for row in pd))

def runonce(enl, font, level):
    from mtplane import MetatilePlane
    from player import Player, TumblingBlock
    from levels import load_level, load_level_col
    from wbbmath import inc_nmis
    global helptxt

    p = Player()
    p.ropeparts_png = G.image.load('tilesets/ropeparts.png').convert_alpha()
    swinging2_png = G.image.load('tilesets/swinging2.png').convert_alpha()
    p.swinging_png = [swinging2_png,
                      G.transform.flip(swinging2_png, True, False),
                      G.transform.flip(swinging2_png, False, True),
                      G.transform.flip(swinging2_png, True, True)]
    del swinging2_png
    pf = MetatilePlane()
    pf.sheet = G.image.load('tilesets/bgtiles.png').convert()
    TumblingBlock.sheet = G.image.load('tilesets/tumbling_box.png').convert()
    load_level(pf, level)
    startpos = level['start']
    p.ballpos = [startpos[0] * 16 + 8, startpos[1] * 16 + 11]
    p.pf = pf
    screen = enl.get_surface()
    pfdst = screen.subsurface((0, 16, 256, 192))
    
    status_bgc = (89, 167, 255)
    clk = G.time.Clock()
    done = False
    retrying = False

    pf.tumble = []
    helptxt = ("\x1b\x1a\x19\x18:move  A:push  \x19A: pull"
               if level == first_level
               else "")

    soln = None
    last_camx = 0
    pf.win_x = 0
    while not done:
        for event in G.event.get():
            if event.type == G.KEYDOWN:
                if event.key == G.K_ESCAPE:  # escape
                    done = True
                if (event.key == G.K_F5
                    or (event.key == G.K_r and (event.mod & G.KMOD_CTRL))):
                    done = True
                    retrying = True
                if (event.key == G.K_p and (event.mod & G.KMOD_CTRL)):
                    G.image.save(pfdst, "wbb_snap.png")
            if event.type == G.QUIT:
                done = True
        (vkeys, new_vkeys) = read_pads()
        if new_vkeys & VK_EOM:
            done = True
        p.move(vkeys, new_vkeys)
        p.ballpos[0] = max(pf.win_x * 16 + 4, p.ballpos[0])
        if p.state == p.ST_ENTERING_DOOR and p.walking_frame >= 1024:
            done = True
            retrying = 'd'
        # if below pfdst and not hanging, fail
        if (p.ballpos[1] >= 208 and (not p.rope or p.rope.vel)):
            done = True
            retrying = not with_vidcap

        pf.tumble = [t for t in pf.tumble if t and not t.done()]
        for t in pf.tumble:
            t.move()

        if not soln and p.ballpos[0] >= 192+512 and level == first_level:
            if not pf.getcell(14+32, 9):
                soln = '2. Nova'
            elif pf.getcell(13+32, 10):
                soln = '1. Pino'
            elif p.state == p.ST_CLIMBING and p.ballpos[0] >= 216+512:
                soln = "3. Snowy"
            if soln:
                helptxt = soln

        # scrolling
        camtarget = p.ballpos[0] + (-16 if p.facing_left else 16)
        if p.rope and p.rope.pos and p.state == p.ST_FALLING:
            camtarget = (camtarget + p.rope.pos[0]) / 2
        camx = max(int(camtarget) - 128, pf.win_x * 16)
        camdelta = abs(camx - last_camx) // 16 + 1
        camx = min(last_camx + camdelta, max(last_camx - camdelta, camx))
        if camx != last_camx:
            wanted_winx = camx // 16
            if wanted_winx >= pf.win_x + 15:
                pf.win_x += 1
                load_level_col(pf, level, pf.win_x + 31)
            pf.cleardirty(True)
            last_camx = camx
        old_dirty = pf.redrawdirty(pfdst, camx, 0)
        spr_rects = []
        spr_rects.extend(p.draw(pfdst, camx))
        for t in pf.tumble:
            spr_rects.extend(t.draw(pfdst, camx))
        pf.setdirtyrects(spr_rects, camx)
        new_dirty = pf.getdirtyruns()
        all_dirty = pf.unionoldnewdirty(old_dirty, new_dirty)
        to_update = pf.dirtyrunstorects(all_dirty)
        chipsfx.fxq_play(sfx, enl.num_frames)

        screen.fill(status_bgc, (0, 0, 256, 16))
        txtrct = font.textout(screen, helptxt, 16, 8)
        if moviedata and (G.key.get_mods() & G.KMOD_RCTRL):
            clk.tick(600)
        else:
            clk.tick(60)
        inc_nmis()
        enl.flip()
    return retrying

def coprscreen(enl, font, notice):
    """Display a screen full of text.

Return the event of type pygame.KEYDOWN or pygame.QUIT that caused
the form to close, or None if the form was closed by pressing A.

"""
    screen = enl.get_surface()
    screen.fill((102, 102, 102))
    for y, txt in enumerate(notice.split('\n')):
        font.textout(screen, txt, 16, y * 8)
    enl.flip()
    
    clk = G.time.Clock()
    done = False
    r = None
    read_pads()  # flush out last screen's held keys
    while not done:
        for event in G.event.get():
            if event.type == G.KEYDOWN:
                done = r = event
            if event.type == G.QUIT:
                done = r = event
        (vkeys, new_vkeys) = read_pads()
        if new_vkeys & (VK_A | VK_START):
            done = True

        clk.tick(30)
    return r

def irle(it):
    last = None
    lastamt = 0
    for i in it:
        if i != last:
            if lastamt:
                yield (last, lastamt)
            last, lastamt = i, 0
        lastamt += 1
    yield (last, lastamt)

def save_tas(frames, filename):
    btns = 'AB__UDLR'
    btns = [(0x80 >> i, b) for (i, b) in enumerate(btns)]
    frames = [(''.join(b if (vkeys & i) else '' for (i, b) in btns) or '-',
               " %d\n" % n if n > 1 else "\n")
              for (vkeys, n) in irle(frames)]
    with open(filename, 'wt') as outfp:
        outfp.writelines(c for row in frames for c in row)

def load_tas(filename):
    from operator import or_
    try:
        reduce
    except NameError:
        from functools import reduce

    out = bytearray()
    tasbindings = {'U': VK_UP, 'D': VK_DOWN, 'L': VK_LEFT, 'R': VK_RIGHT, 'A': VK_A}
    with open(movie_filename, 'r') as infp:
        lines = [_f for _f in (line.strip().split('#', 1)[0] for line in infp) if _f]
    for line in lines:
        line = [c.strip() for c in line.split()[:2]]
        nframes = int(line[1]) if len(line) > 1 and line[1].isdigit() else 1
        btns = reduce(or_, (tasbindings.get(c, 0) for c in line[0].upper()))
        out.extend([btns] * nframes)
    return out

sfxdata = [
    ('launch', 0, 1, bytearray([
        0x8c,61,0x4c,30,0x89,29,0x86,29,0x84,29,0x83,29,0x82,29,0x81,29
    ])),
    ('anchor', 12, 2, bytearray([
        0x08,0x0c,0x08,0x08,0x05,0x0a,0x02,0x0b
    ])),
    ('land', 12, 2, bytearray([
        0x0c,0x0e,0x08,0x0f
    ])),
    ('steplift', 12, 1, bytearray([
        0x01,0x0e,0x01,0x05,0x02,0x05,0x01,0x05
    ])),
    ('step', 12, 1, bytearray([
        0x01,0x07,0x03,0x0f,0x02,0x0f,0x01,0x0f
    ])),
    ('item', 0, 2, bytearray([
        0x48,40,0x46,40,0x48,42,0x46,42,0x48,44,0x46,44,
        0x48,40,0x46,40,0x48,44,0x46,44,0x48,47,0x46,47,
        0x48,52,0x48,52,0x46,47,0x46,52,0x46,52,0x43,47,0x43,52,0x41,47,0x43,52,0x41,47,
    ])),
    ('climb', 0, 1, bytearray([
        0x44,26,0x45,29,0x46,31,0x47,32,0x48,33,0x48,33,0x48,34,0x48,34,0x46,34,0x46,34,0x45,33,0x44,31
    ])),
    ('blockfall', 0, 2, bytearray([
        0x82,60,0x83,59,0x83,58,0x84,57,0x84,56,0x84,55,
        0x84,54,0x84,53,0x84,52,0x83,51,0x83,50,0x82,49,
    ])),       
]

level_filenames = [
    'levels/first.map', 'levels/hubs.map'
]

def main():
    from enlarger import Enlarger
    from levels import load_all_levels
    from ascii import PyGtxt
    global bindings, sfx, moviedata

    sfx = chipsfx.make_sound_effects(sfxdata)
    try:
        sfx = dict((name, G.mixer.Sound(samples))
                   for (name, samples) in sfx.items())
    except TypeError as e:
        # did this change between 2.6 and 2.7, or between Linux and
        # Mac, or between 1.9.1 and 1.9.2?
        sfx = dict((name, G.mixer.Sound(buffer=samples))
                   for (name, samples) in sfx.items())
    joycfg.dump_joysticks(verbose=False)
    wndicon = G.image.load('tilesets/wndicon.png')
    if with_music:
        G.mixer.music.load('music/w1a.ogg')
    G.display.set_icon(wndicon)
    G.display.set_caption("Wrecking Ball Boy")
    font = PyGtxt(G.image.load('tilesets/ascii.png'), 8, 8)

    # set display mode
    logisize = (256, 208)
    physsize = tuple(c * gfx_scale for c in logisize)
    screen = G.display.set_mode(physsize)
    enl = Enlarger(screen, logisize if gfx_scale > 1 else None, True)

    if movie_filename:
        moviedata = iter(load_tas(movie_filename))

##    fontimg = G.image.load('tilesets/vwf7.png')
##    fontimg.set_colorkey(0)
##    font = PyGtxt(fontimg, 8, 8, 32, 3)
    bindings = joycfg.load_bindings(keybindings_filename)
    if bindings == 'reconfigure':
        bindings = joycfg.get_bindings(enl.get_surface(), font, action_names, flipper=enl)
        if not bindings:
            return
        joycfg.save_bindings(keybindings_filename, bindings, action_names)
    elif not isinstance(bindings, list):
        bindings = [('key', b) for b in default_bindings]
    if not skipNotices:
        e = coprscreen(enl, font, coprNotice)
        if e and e.type == G.KEYDOWN and e.key == G.K_ESCAPE:
            return
        if e and e.type == G.QUIT:
            return

    bindingsNotice = '\n'.join([
        "",
        "Controls (Tab to change)",
        "\n".join("%-7s%s" % (n+":", joycfg.format_binding(b))
                  for (n, b) in zip(action_names, bindings)),
        belowBindingsNotice
    ])
    if not skipNotices:
        e = coprscreen(enl, font, bindingsNotice)
        if e and e.type == G.KEYDOWN:
            if e.key == G.K_ESCAPE:
                return
            if e.key == G.K_TAB:
                newbindings = joycfg.get_bindings(enl.get_surface(), font, action_names, flipper=enl)
                if newbindings:
                    bindings = newbindings
                    joycfg.save_bindings(keybindings_filename, bindings, action_names)
        if e and e.type == G.QUIT:
            return
        e = coprscreen(enl, font, controlsNotice)
        if e and e.type == G.KEYDOWN and e.key == G.K_ESCAPE:
            return
        if e and e.type == G.QUIT:
            return
    del bindingsNotice

    if with_vidcap:
        if with_vidcap == 'pipe':
            import shlex, subprocess
            args = shlex.split(vidcap_pipe_cmd)
            ffpipe = subprocess.Popen(args, bufsize=-1, stdin=subprocess.PIPE)
            video_outfp = ffpipe.stdin
        else:
            video_outfp = open('vtee.raw', 'wb')
            ffpipe = None
            # convert this with
            # avconv -f rawvideo -r 30 -pix_fmt rgb24 -s 256x192 -y -an -i vtee.raw -c:v png vtee.avi
            # or see http://www.iabaldwin.com/2011/02/piping-raw-data-info-ffmpeg/
        enl.set_videotee(video_outfp, 2)
        title_png = G.image.load('tilesets/title.png')
        enl.get_surface().blit(title_png, (0, 0))
        for i in range(120):
            enl.flip()
    else:
        video_outfp = None

    all_levels = load_all_levels(level_filenames)
    global first_level
    first_level = all_levels[0]

    level_num = 0
    try:
        if with_music:
            G.mixer.music.set_volume(.7)
            G.mixer.music.play(-1)
        while True:
            continuing = runonce(enl, font, all_levels[level_num])
            if not continuing:
                break
            if continuing == 'd':
                level_num = (level_num + 1) % len(all_levels)
    finally:
        G.mixer.music.stop()
        if tasrecdata and movierec_filename:
            save_tas(tasrecdata, movierec_filename)
        if video_outfp:
            enl.get_surface().blit(title_png, (0, 0))
            for i in range(60):
                enl.flip()
            video_outfp.close()  # send EOF to avconv to make it finish encoding
            chipsfx.render_logged_fx(sfxdata, enl.num_frames)
            if ffpipe:
                ffpipe.wait()
        else:
            enl.get_surface().fill((102, 102, 102))
            enl.flip()

if __name__=='__main__':
    G.mixer.pre_init(mixer_freq, -16, 1, 1024)
    G.init()
    try:
        main()
    finally:
        G.quit()

# TO DO after coprNotice tasks:
# draw more kinds of platforms
# draw swingbars
# draw front-facing ladders in GIMP
# draw front-facing ladder climbing animation in GIMP
# latch to front-facing ladders
# climb front-facing ladders
# tug boxes upward
# snap theta to 3*Tau/16 or 5*Tau/16 when nearly upright and near a block
# hang directly from high bars
# shoot while hanging from high bar
# do something with the ladder at the end of first_level
# switch-activated doors
# bug jero to make a level
# body raise training to 50 reps in a half hour

##print("\n".join(repr((a-9, b-10)) for (a, b) in body_out))
##print("\n".join(repr((jx-ix, jy-iy))
##                for ((ix, iy), (jx, jy)) in zip(arms_in, arms_out)))
