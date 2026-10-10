"""Pyglet fullscreen on the current monitor; restore window geometry."""
import sys,ctypes

def enable_dpi_awareness():
    if sys.platform=='win32':ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

class DisplayMode:
    def __init__(self,window,preferences=None):self.window=window;self.preferences=preferences;self.fullscreen=False;self.size=window.get_size();self.position=window.get_location()
    def toggle(self):
        if not self.fullscreen:
            self.size=self.window.get_size();self.position=self.window.get_location()
            x,y=self.position
            screen=next((s for s in self.window.display.get_screens() if s.x<=x<s.x+s.width and s.y<=y<s.y+s.height),self.window.screen)
            self.window.set_fullscreen(True,screen=screen)
        else:
            self.window.set_fullscreen(False,width=self.size[0],height=self.size[1]);self.window.set_location(*self.position)
        self.fullscreen=not self.fullscreen
        if self.preferences:
            self.preferences.fullscreen=self.fullscreen;self.preferences.size=self.size;self.preferences.save()
