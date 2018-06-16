#!/usr/bin/env python
from __future__ import with_statement, division, print_function, unicode_literals
import pygame as G
try:
    xrange
except NameError:
    xrange = range
import levels

with_double = True
mixer_freq = 44100  # for preview

tile_descriptions = [
    'empty',
    'grass',
    'crates',
    'solid dirt',
    'middle of pole',
    'top of pole',
    'W side ladder',
    'E side ladder',

    'unused 08',
    'unused 09',
    'unused 0A',
    'unused 0B',
    'rope powerup',
    'no-grapple wall',
    'level door',
    'level door base',

    'shack middle',
    'shack roof',
    'shack window',
    'shack door',
    'shack door base'
]

def make_empty_level():
    import array
    return {'screens':[array.array('H',[0xB001,0xC00F])],'start':(0,10)}

def decode_entire_level(level):
    from levels import load_level_col
    return [load_level_col(None, level, x)
            for x in xrange(0, 16 * len(level['screens']))]

def pf_update_cols(pf, cols, xleft, xright=None, with_markov=True):
    if xright is None:
        xright = xleft + 1
    xleft = max(pf.win_x, xleft)
    xright = min(pf.win_x + 32, xright)
    if xleft >= xright:
        return
    empty_col = [0]*12
    m = levels.markov
    for x in xrange(xleft, xright):
        col = cols[x] if x < len(cols) else empty_col
        last_p = 0
        for y, p in enumerate(col):
            if with_markov:
                p = p or (m[last_p] if last_p < len(m) else 0)
            last_p = p
            pf.setcell(x, y, p)

def markov_fill_and_unfill(col):
    import array
    filled = bytearray()
    unfilled = bytearray()
    last_p = 0
    m = levels.markov
    for tileno in col:
        pred = m[last_p] if last_p < len(m) else 0
        last_p = tileno or pred
        filled.append(last_p)
        unfilled.append(last_p if last_p != pred else 0)
    return filled, unfilled

def markov_optimize_screen(cols):
    cols = [markov_fill_and_unfill(col) for col in cols]
    filled = [col[0] for col in cols]
    unfilled = [(x, y, c)
                for (x, col) in enumerate(cols)
                for (y, c) in enumerate(col[1])
                if c]

    # Right now, an object file can be created from unfilled.
    # But first let's bucket sort them by Y so that we can find runs
    # of a given row that cover at least 3 unfilled.  The objects
    # are already sorted by X; sorting them by Y preserves this.
    byrow = [[] for i in xrange(12)]
    for (x, y, c) in unfilled:
        byrow[y].append((x, c))
    objs = []
    for (y, row) in enumerate(byrow):
        i = 0
        while i < len(row):
            x, c = row[i]

            # if there aren't 2 more like objects after this
            # on this row, emit a single tile
            if (i + 3 > len(row)
                or row[i + 1][1] != c
                or row[i + 2][1] != c):
                objs.append((x, y, c))
                i += 1
                continue

            # So we know the next two objects on this row are the
            # same tile number.  Search for how many are contiguous
            # in the filled data.
            xr = x + 1
            while xr < len(filled) and filled[xr][y] == c:
                xr += 1

            # If the run is not long enough, emit a single tile
            if row[i + 2][0] >= xr:
                objs.append((x, y, c))
                i += 1
                continue

            # Extend run to left for editor's convenience
            while x > 0 and filled[x - 1][y] == c:
                x -= 1

            # Now subsume all objs within this run
            oldi = i + 3
            while i < len(row) and row[i][0] < xr:
                i += 1
            objs.append((x, y, c))
            # Y=12 and X=0 means a run of tileno (2-15) more tiles
            objs.append((0, 12, xr - x - 1))

    # And at this point, we're ready to encode it
    import array
    screendata = array.array('H', (
        (y << 12) | (x << 8) | c for (x, y, c) in objs
    ))
    return screendata

def update_camxvel(vel, dist):
    # If not same sign, brake
    if vel < 0 and dist >= 0:
        return min(0, vel + 1)
    if vel > 0 and dist <= 0:
        return max(0, vel - 1)
    if dist == vel == 0:
        return 0

    # If closer than the distance if next frame accelerates, brake
    avel = abs(vel)
    adist = abs(dist)
    adist_if_noaccel = (avel + 1) * avel / 2
    adist_if_accel = adist_if_noaccel + avel
    if adist <= adist_if_noaccel:
        return vel + (1 if dist < 0 else -1)
    if adist <= adist_if_accel:
        return vel
    if adist < 64 or adist < 2 * adist_if_accel:
        return vel - (1 if dist < 0 else -1)
    return vel - (2 if dist < 0 else -2)

class SmoothpanCamera(object):
    def __init__(self):
        self.camx = self.camx_vel = 0

    def move_toward(self, target_camx):
        self.camx_vel = update_camxvel(self.camx_vel, target_camx - self.camx)
        self.camx = max(0, self.camx + self.camx_vel)

class Activity(object):
    def __init__(self, context):
        self.context = context
        self.screen, self.sheet, self.fixfont, self.vwf = context
        self.quitting = self.closing = False
        self.popup = None
        self.scalex = G.display.get_surface().get_width() / self.screen.get_width()
        self.scaley = G.display.get_surface().get_height() / self.screen.get_height()

    def event_to_action(self, event):
        """Move."""
        if event.type == G.KEYDOWN:
            if event.key == G.K_ESCAPE:
                return ('back',)
            if (event.key == G.K_p and (event.mod & G.KMOD_CTRL)):
                return ('screenshot',)
        if event.type == G.QUIT:
            return ('quit',)
        return None

    def get_scaled_mouse_coords(self, event):
        m_x = int(event.pos[0] // self.scalex)
        m_y = int(event.pos[1] // self.scaley)
        return (m_x, m_y)

    def handle_action(self, event):
        if not event:
            return
        e0 = event[0]
        if e0 == 'quit':
            self.quitting = True
        elif e0 == 'screenshot':
            G.image.save(self.screen, "wbb_snap.png")
        elif e0 == 'back':
            self.closing = True
        else:
            print("event:", event)

    def get_tile_srcarea(self, tileno):
        sheet_tile_width = self.sheet.get_width() // 16
        y = tileno // sheet_tile_width * 16
        if y >= self.sheet.get_height():
            return None
        return (tileno % sheet_tile_width * 16, y, 16, 16)

    def draw_tile_to_status_bar(self, tileno, x):
        screen = self.screen
        if tileno == 'insert':
            tilename = 'Insert columns'
        elif tileno == 'delete':
            tilename = 'Delete columns'
        else:
            screen.blit(self.sheet, (x, 0), self.get_tile_srcarea(tileno))
            self.fixfont.textout(screen, "$%02x" % tileno, x + 16, 0)
            try:
                tilename = tile_descriptions[tileno]
            except IndexError:
                tilename = '???'
        self.vwf.textout(screen, tilename, x + 18, 8)
        
    def uncover(self):
        """Redraw anything using dirty rectangles."""

    def draw(self):
        """Draw to screen."""

class Editor(Activity):
    def __init__(self, context):
        from mtplane import MetatilePlane

        Activity.__init__(self, context)
        self.with_markov = False
        self.pfdst = self.screen.subsurface((0, 16, 256, 192))
        self.pf = MetatilePlane()
        self.pf.sheet = self.sheet
        self.pf.win_x = 0
        self.camera = SmoothpanCamera()
        self.target_camx = 0
        self.tileno = 2
        self.cols = []
        self.mousemove_xy = None
        self.actions = []

    def get_tile_coords(self, m_xy):
        t_x = (m_xy[0] + self.camera.camx) // 16
        t_y = (m_xy[1] - 16) // 16
        return (t_x, t_y)

    def update_all_cols(self):
        xbase = self.pf.win_x
        pf_update_cols(self.pf, self.cols,
                       xbase, xbase + 17, with_markov=self.with_markov)

    def load_cols_from_level(self, level):
        self.cols = decode_entire_level(level)
        self.update_all_cols()

    def move_camera(self):
        last_camx = self.camera.camx
        self.target_camx = max(0, min((len(self.cols) - 8) * 16,
                                      self.target_camx))
        self.camera.move_toward(self.target_camx)

        if self.camera.camx != last_camx:
            self.pf.cleardirty(True)
            new_wx = self.camera.camx // 16
            while self.pf.win_x < new_wx:
                self.pf.win_x += 1
                pf_update_cols(self.pf, self.cols, self.pf.win_x + 16,
                               with_markov=self.with_markov)
            while self.pf.win_x > new_wx:
                self.pf.win_x -= 1
                pf_update_cols(self.pf, self.cols, self.pf.win_x,
                               with_markov=self.with_markov)

    def event_to_action(self, event):
        """Translates SDL inputs into high-level events."""
        if event.type == G.MOUSEBUTTONDOWN:
            m_x, m_y = self.get_scaled_mouse_coords(event)
            if event.button == 4:  # wheel up
                return ('scroll', -64)
            if event.button == 5:  # wheel down
                return ('scroll', 64)
            if event.button == 1 and 0 <= m_y < 16:
                if 16 <= m_x < 40:
                    return ('pageup',)
                if 48 <= m_x < 72:
                    return ('pagedown',)
                if 80 <= m_x < 184:
                    return ('opentilepicker',)
                if 192 <= m_x < 208:
                    return ('togglemarkov',)
                print("left-click status bar at x=%d" % m_x)
            elif 16 <= m_y < 208:
                t_x, t_y = self.get_tile_coords((m_x, m_y))
                self.mousemove_xy = (t_x, t_y)
                if event.button == 1:
                    if self.tileno == 'insert':
                        return ('insertcol', min(t_x, len(self.cols)))
                    elif self.tileno == 'delete' and len(self.cols) > 1:
                        return ('deletecol', min(t_x, len(self.cols) - 1))
                    else:
                        return ('placetile', t_x, t_y)
                elif event.button == 3:
                    return ('pickuptile', t_x, t_y)
            print("(%3d, %3d, button %d)" % (m_x, m_y, event.button))
        elif event.type == G.MOUSEMOTION:
            if not any(event.buttons):
                return Activity.event_to_action(self, event)
            m_x, m_y = self.get_scaled_mouse_coords(event)
            if 16 <= m_y < 208 and self.tileno not in ('insert', 'delete'):
                t_key = self.get_tile_coords((m_x, m_y))
                if t_key != self.mousemove_xy:
                    self.mousemove_xy = t_key
                    t_x, t_y = t_key
                    if event.buttons[0] and self.tileno not in ('insert', 'delete'):
                        return ('placetile', t_x, t_y)
                    if event.buttons[2]:
                        return ('pickuptile', t_x, t_y)
            return Activity.event_to_action(self, event)
        elif event.type == G.KEYDOWN:
            if (event.key == G.K_m):
                return ('togglemarkov',)
            if event.key == G.K_RIGHT:
                return ('scroll', 16)
            if event.key == G.K_LEFT:
                return ('scroll', -16)
            if event.key == G.K_SPACE:
                return ('settileno', 0)
            if event.key == G.K_INSERT:
                return ('settileno', 'insert')
            if event.key in (G.K_DELETE, G.K_BACKSPACE):
                return ('settileno', 'delete' if self.tileno != 'delete' else 'insert')
            if event.key == G.K_UP:
                return ('addtileno', -1)
            if event.key == G.K_DOWN:
                return ('addtileno', 1)
            if event.key == G.K_HOME:
                return ('scrolltostart',)
            if event.key == G.K_END:
                return ('scrolltoend',)
            if event.key == G.K_PAGEDOWN:
                return ('pagedown',)
            if event.key == G.K_PAGEUP:
                return ('pageup',)
        return Activity.event_to_action(self, event)

    def tilepicker_onchange(self, tileno):
        self.tileno = tileno

    def uncover(self):
        self.pf.cleardirty(True)

    def handle_action(self, event):
        if not event:
            return
        e0 = event[0]
        if e0 == 'togglemarkov':
            self.with_markov = not self.with_markov
            self.update_all_cols()
        elif e0 == 'scroll':
            self.target_camx += event[1]
        elif e0 == 'scrolltostart':
            self.target_camx = 0
        elif e0 == 'scrolltoend':
            self.target_camx = len(self.cols) * 16
        elif e0 == 'pageup':
            self.target_camx = (self.target_camx - 16) // 256 * 256
        elif e0 == 'pagedown':
            self.target_camx = (self.target_camx + 256) // 256 * 256
        elif e0 == 'deletecol' and event[1] < len(self.cols) and len(self.cols) > 1:
            del self.cols[event[1]]
            self.update_all_cols()
        elif e0 == 'insertcol':
            x = min(len(self.cols) - 1, event[1])
            self.cols.insert(x, self.cols[x][:])
            self.update_all_cols()
        elif e0 == 'settileno':
            self.tileno = event[1]
        elif e0 == 'addtileno':
            self.tileno = max(0, min(len(levels.markov) - 1, self.tileno + event[1]))
        elif e0 == 'placetile':
            t_x, t_y = event[1:3]
            if 0 <= t_x < len(self.cols) and 0 <= t_y < 12:
                self.cols[t_x][t_y] = self.tileno
                pf_update_cols(self.pf, self.cols, t_x, with_markov=self.with_markov)
        elif e0 == 'pickuptile':
            t_x, t_y = event[1:3]
            if 0 <= t_x < len(self.cols) and 0 <= t_y < 12:
                self.tileno = self.cols[t_x][t_y]
        elif e0 == 'opentilepicker':
            picker_tileno = self.tileno if isinstance(self.tileno, int) else 0
            self.popup = TilePicker(self.context, picker_tileno,
                                    self.tilepicker_onchange)
        else:
            Activity.handle_action(self, event)

    def draw_status_bar(self):
        screen = self.screen
        status_bgc = (89, 167, 255)

        scrno = self.target_camx // 256 + 1
        nscrns = (len(self.cols) + 15) // 16
        
        screen.fill(status_bgc, (0, 0, 256, 16))
        self.fixfont.textout(screen, "Screen", 16, 0)
        self.fixfont.textout(screen, "\x1b%2d/%2d\x1a" % (scrno, nscrns), 16, 8)
        self.draw_tile_to_status_bar(self.tileno, 80)
        self.fixfont.textout(screen, "\x09\x12" if self.with_markov else "\x08\x12",
                          192, 8)
        self.vwf.textout(screen, "Fill", 192, 0)

    def draw(self):
        self.move_camera()
        self.pf.redrawdirty(self.pfdst, self.camera.camx, 0)
        self.draw_status_bar()

class TilePicker(Activity):
    def __init__(self, context, tileno, onchange):
        Activity.__init__(self, context)
        self.tileno = tileno
        self.onchange = onchange
        self.all_dirty = True
        self.dirty_tiles = set()

    def event_to_action(self, event):
        if event.type == G.MOUSEBUTTONDOWN and event.button == 1:
            m_x, m_y = self.get_scaled_mouse_coords(event)
            if m_y < 16:
                return ('confirm',)
            t_x = m_x // 16
            t_y = (m_y - 16) // 16
            tileno = t_y * 16 + t_x
            if tileno >= len(levels.markov):
                return ('back',)
            if tileno == self.tileno:
                return ('confirm',)
            return ('settileno', tileno)
        if event.type == G.KEYDOWN:
            if (event.key == G.K_RETURN):
                return ('confirm',)
            if event.key == G.K_RIGHT:
                return ('addtileno', 1)
            if event.key == G.K_LEFT:
                return ('addtileno', -1)
            if event.key == G.K_UP:
                return ('addtileno', -16)
            if event.key == G.K_DOWN:
                return ('addtileno', 16)
            if event.key == G.K_HOME:
                return ('scrolltostart',)
            if event.key == G.K_END:
                return ('scrolltoend',)
            if event.key == G.K_PAGEDOWN:
                return ('pagedown',)
            if event.key == G.K_PAGEUP:
                return ('pageup',)
        return Activity.event_to_action(self, event)

    def handle_action(self, event):
        if not event:
            return
        e0 = event[0]
        if e0 == 'settileno':
            self.dirty_tiles.add(self.tileno)
            self.tileno = event[1] & 0x7F
            self.dirty_tiles.add(self.tileno)
        elif e0 == 'addtileno':
            self.dirty_tiles.add(self.tileno)
            self.tileno = (self.tileno + event[1]) & 0x7F
            self.dirty_tiles.add(self.tileno)
        elif e0 == 'confirm':
            self.onchange(self.tileno)
            self.closing = True
        else:
            return Activity.handle_action(self, event)

    def draw_status_bar(self):
        screen = self.screen
        status_bgc = (191, 0, 0)

        screen.fill(status_bgc, (0, 0, 256, 16))
        self.draw_tile_to_status_bar(self.tileno, 80)

    def draw_single_tile(self, tileno):
        dsty = (tileno & 0xF0) + 16
        dstx = (tileno & 0x0F) << 4
        srcarea = self.get_tile_srcarea(tileno)
        selcolor = (191, 0, 0)
        screen = self.screen
        if srcarea:
            screen.blit(self.sheet, (dstx, dsty), srcarea)
        else:
            screen.fill((0, 0, 0), (dstx, dsty, 16, 16))
        if tileno == self.tileno:
            for y in (dsty, dsty + 14):
                screen.fill(selcolor, (dstx, y, 16, 2))
            for x in (dstx, dstx + 14):
                screen.fill(selcolor, (x, dsty, 2, 16))

    def draw(self):
        self.draw_status_bar()
        if self.all_dirty:
            self.dirty_tiles = xrange(len(levels.markov))
            self.all_dirty = False
        for t in self.dirty_tiles:
            self.draw_single_tile(t)
        self.dirty_tiles = set()
        

def runonce(enl, font, vwf, level):
    sheet = G.image.load('tilesets/bgtiles.png').convert()
    context = (enl.get_surface(), sheet, font, vwf)
    e = Editor(context)
    e.load_cols_from_level(level)
    clk = G.time.Clock()
    backstack = [e]
    while backstack:
        fm = backstack[-1]
        actions = [fm.event_to_action(event) for event in G.event.get()]
        for action in actions:
            fm.handle_action(action)
        fm.draw()
        clk.tick(60)
        enl.flip()
        if fm.popup:
            backstack.append(fm.popup)
            fm.popup = None
        if fm.closing or fm.quitting:
            backstack.pop()
            if backstack:
                backstack[-1].uncover()
        if fm.quitting and backstack:
            backstack[-1].handle_action(('quit',))

    lvltosave = {
        'screens': [markov_optimize_screen(e.cols[i:i + 16])
                    for i in xrange(0, len(e.cols), 16)],
        'start': level['start']
    }
    return lvltosave

def main():
    from enlarger import Enlarger
    from ascii import PyGtxt
    global bindings, joysticks

    wndicon = G.image.load('tilesets/wndicon.png')
    G.display.set_icon(wndicon)
    G.display.set_caption('level editor')
    G.key.set_repeat(250, 33)
    screen_size = (256, 208)
    screen = G.display.set_mode(tuple(c * 2 for c in screen_size)
                                if with_double
                                else screen_size)
    enl = Enlarger(screen, screen_size if with_double else None, True)
    sheet = G.image.load('tilesets/bgtiles.png').convert()
    font = PyGtxt(G.image.load('tilesets/ascii.png'), 8, 8)
    vwfimg = G.image.load('tilesets/vwf7.png')
    vwfimg.set_colorkey(0)
    vwf = PyGtxt(vwfimg, 8, 8, 32, 3)

    try:
        with open("levels/editor.map", 'rb') as infp:
            lvldata = infp.read()
    except IOError as e:
        import errno
        if e.errno == errno.ENOENT:
            lvldata = ''
            print("Creating new file")
        else:
            raise

    lvldata = levels.decode_level(lvldata) if lvldata else make_empty_level()
    lvltosave = runonce(enl, font, vwf, lvldata)

    enl.get_surface().fill((102, 102, 102))
    font.textout(enl.get_surface(), 'Saving', 32, 16)
    enl.flip()
    lvldata = levels.encode_level(lvltosave)
    with open("levels/editor.map", 'wb') as outfp:
        outfp.write(lvldata)

    import wbb
    wbb.level_filenames[:] = ["levels/editor.map"]
    wbb.main()


if __name__=='__main__':
    G.mixer.pre_init(mixer_freq, -16, 1, 1024)
    G.init()
    try:
        main()
    finally:
        G.quit()
