"""One keyboard handler owns both held movement and one-shot actions."""
from pyglet.window import key
from . import backend as ui


def pointer_position(window,fallback):
    """Poll the desktop cursor in client coordinates, including outside the window."""
    import sys
    if sys.platform!='win32':return fallback
    from ctypes import byref
    from ctypes.wintypes import POINT
    from pyglet.libs.win32 import _user32
    point=POINT()
    if not _user32.GetCursorPos(byref(point)):return fallback
    if not _user32.ScreenToClient(window._view_hwnd,byref(point)):return fallback
    scale=window._mouse_scale
    return point.x/scale,point.y/scale


class Keyboard:
    def __init__(self,window,game,display):
        self.keys=key.KeyStateHandler();self.game=game;self.display=display
        window.push_handlers(self)

    def on_key_press(self,symbol,modifiers):
        self.keys.on_key_press(symbol,modifiers)
        if symbol==key.F11:self.display.toggle();return
        self.game.handle_event(ui.event.Event(ui.KEYDOWN,key=key.symbol_string(symbol).lower()))
        return True

    def on_key_release(self,symbol,modifiers):
        self.keys.on_key_release(symbol,modifiers)

    def on_deactivate(self):self.keys.on_deactivate()

    def axes(self):
        k=self.keys
        return (int(k[key.D] or k[key.RIGHT])-int(k[key.A] or k[key.LEFT]),
                int(k[key.S] or k[key.DOWN])-int(k[key.W] or k[key.UP]))
