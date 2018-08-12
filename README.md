Wrecking Ball Boy
=================

> How do you like to go up in a swing,  
> Up in the air so blue?  
> Oh, I do not think it the pleasantest thing  
> Ever a child can do!

Robert Louis Stevenson, ["The Swing"][1], _A Child's Garden of Verses_ (1885)

This is a prototype using Pygame of a puzzle platformer that I plan to port to the NES once it's done. It stars a character who compensates for his lack of lower limbs by carrying a grappling hook and using it to swing from whatever object is above him.

Installation
------------
To prepare, install Python 3.6 and Pygame. Under Windows, for
example, once you have installed Python, you can install Pygame with
the following commands at a command prompt:

    py -m pip install --upgrade pip
    py -m pip install pygame

Then run the file `wbb.py`.

Full usage instructions are in `how.html`.

Why SDL 1.2?
------------
Pygame uses SDL 1.2.  When exporting a replay as a video, the game
uses `pygame.image.tostring()` to capture the video to an RGB byte
string and then feed it to FFmpeg.  (See `enlarger.py`.)  I know of
two SDL 2-based replacements for Pygame, neither of which has any
counterpart to `pygame.image.tostring()`

[PySDL2 docs][1] state:

> tostring(): No equivalent yet

The README for the Ren'Py project's [pygame_sdl2][2] states:

> Current omissions include:  
> APIs that expose pygame data as buffers or arrays.

License choice is pending.

[1]: https://en.wikisource.org/wiki/The_Swing
[3]: https://pysdl2.readthedocs.io/en/rel_0_9_6/tutorial/pygamers.html#pygame-image
[4]: https://github.com/renpy/pygame_sdl2
