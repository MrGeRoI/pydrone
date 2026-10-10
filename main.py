"""Pyglet entry point; original simulation runs at a fixed 50 Hz."""
import argparse
from pathlib import Path

def parse_args(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--stress',type=int,default=0)
    parser.add_argument('--menu',action='store_true')
    parser.add_argument('--debug',action='store_true',help='enable god mode and free buy controls')
    parser.add_argument('--arena',choices=('b','t','1','2','3','4','5','6'),default='b',metavar='{b,t,1-6}',help='start in the base (b, default) or an arena (t: tutorial)')
    args=parser.parse_args(argv)
    from drone.config import ARENAS
    if args.arena not in ('b','t') and args.arena not in ARENAS:
        name='Tutorial' if args.arena=='t' else f'Arena {args.arena}'
        parser.error(f"{name} has not been ported yet. Available arenas: {', '.join(ARENAS)}.")
    return args


def main():
    args=parse_args()
    from drone.display import enable_dpi_awareness,DisplayMode
    enable_dpi_awareness()
    import pyglet
    pyglet.options['debug_gl']=False
    from pyglet.window import key,mouse
    from drone import backend as ui
    from drone.app import Game
    from drone.renderer import Renderer
    from drone.input import Keyboard,pointer_position
    from drone.preferences import Preferences
    preferences=Preferences()
    window=pyglet.window.Window(*preferences.size,resizable=True,visible=not args.smoke,caption='PyDrone',vsync=preferences.vsync)
    window.set_icon(pyglet.image.load(str(Path(__file__).resolve().parent/'data/assets/logo.png')))
    monitor=window.screen
    window.set_location(monitor.x+(monitor.width-window.width)//2,monitor.y+(monitor.height-window.height)//2)
    renderer=Renderer(window);game=Game(ui.Surface(window.get_size()),preferences,debug=args.debug);display=DisplayMode(window,preferences)
    game.toggle_fullscreen=display.toggle
    game.exit_game=window.close
    game.set_vsync=window.set_vsync;window.set_caption(game.t("app.title"))
    if preferences.fullscreen:display.toggle();game.resize(ui.Surface(window.get_size()))
    pressed=False;accumulated=0;resize_pending=None
    if args.smoke:game.audio.muted=True
    if args.menu:game.menu.open=True
    if args.arena=='t':game.enter_tutorial()
    elif args.arena not in ('b','h'):game.enter_arena(int(args.arena),bypass_lock=True)
    if args.stress:
        from drone.structures import DeployRobot
        import random
        if args.arena in ('b','h'):game.enter_arena(practice=True)
        rng=random.Random(17)
        from drone.config import ARENAS
        kinds=[entry[0] for entry in ARENAS[str(game.waves.arena)]['waves']]
        for i in range(args.stress):game.combat.spawn(game.player.x+rng.uniform(-450,450),game.player.y+rng.uniform(-300,300),kinds[i%len(kinds)] if args.arena not in ('b','h') else 'axebot')
        for _ in range(100):game.combat.units.append(DeployRobot(game.player.x+rng.uniform(-300,300),game.player.y+rng.uniform(-200,200),game.player.x,game.player.y,deploy_age=3))
        game.waves.practice=1
    @window.event
    def on_resize(width,height):
        nonlocal resize_pending
        if width and height:
            import time
            resize_pending=(width,height,time.monotonic())
    @window.event
    def on_draw():
        window.clear();game.draw();renderer.draw(game.screen)
    @window.event
    def on_mouse_motion(x,y,dx,dy):
        ui.mouse.position=(x,window.height-y)
    @window.event
    def on_mouse_enter(x,y):
        ui.mouse.position=(x,window.height-y)
    @window.event
    def on_mouse_leave(x,y):
        nonlocal pressed
        pressed=False
    @window.event
    def on_deactivate():
        nonlocal pressed
        pressed=False;game.window_focused=False
    @window.event
    def on_activate():game.window_focused=True
    @window.event
    def on_mouse_drag(x,y,dx,dy,buttons,modifiers):
        ui.mouse.position=(x,window.height-y)
    @window.event
    def on_mouse_press(x,y,button,modifiers):
        nonlocal pressed
        ui.mouse.position=(x,window.height-y)
        if button==mouse.LEFT:pressed=True
        game.handle_event(ui.event.Event(ui.MOUSEBUTTONDOWN,button=1 if button==mouse.LEFT else 3 if button==mouse.RIGHT else 2,pos=ui.mouse.position))
    @window.event
    def on_mouse_release(x,y,button,modifiers):
        nonlocal pressed
        if button==mouse.LEFT:pressed=False
    @window.event
    def on_mouse_scroll(x,y,scroll_x,scroll_y):
        ui.mouse.position=(x,window.height-y)
        if scroll_y:game.zoom_camera(scroll_y)
    keyboard=Keyboard(window,game,display)
    def update(dt):
        nonlocal accumulated,resize_pending
        if resize_pending:
            import time
            width,height,changed=resize_pending
            if time.monotonic()-changed>=.15:
                game.resize(ui.Surface((width,height)));resize_pending=None
                if not display.fullscreen:
                    display.size=(width,height);preferences.size=display.size;preferences.save()
        accumulated+=min(dt,.25);interval=1/game.rules['simulation_hz']
        horizontal,vertical=keyboard.axes()
        window.set_mouse_visible(not game.selling or not game.window_focused)
        if game.window_focused:ui.mouse.position=pointer_position(window,ui.mouse.position)
        while accumulated>=interval:
            game.step(horizontal,vertical,ui.mouse.position,interval,firing=pressed);accumulated-=interval
    try:
        if args.smoke:
            for _ in range(50):game.step(0,0,(720,450))
            window.switch_to();on_draw()
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                pyglet.image.get_buffer_manager().get_color_buffer().save(str(args.screenshot))
            import sys
            print(f'Pyglet: 50 simulation steps and GPU rendering OK; GIL enabled: {sys._is_gil_enabled()}')
        else:pyglet.clock.schedule_interval(update,1/120);pyglet.app.run()
    finally:
        if not args.smoke:
            if not display.fullscreen:preferences.size=window.get_size()
            preferences.fullscreen=display.fullscreen
            preferences.save()
        game.flush_zoom_settings()
        game.combat.workers.close();game.audio.stop();renderer.close();window.close()

if __name__=='__main__':main()
