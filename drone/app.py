"""Native first milestone: room art, camera, player and wall collisions."""
import json
import math
from pathlib import Path
from . import backend as ui
from .graphics import Resources,ASSETS
from .model import Player
from .combat import Combat,offset
from .session import Waves,save_game,load_game
from .audio import Audio
from .collision import Collisions
from .progress import Profile,ARENA_SUFFIXES
from .structures import STRUCTURES,UNIT_TYPES
from .menu import Menu,WEAPONS,BUILDINGS
from .config import ARENAS,ENEMY_TYPES,DATA
from .transition import Transition
from .preferences import Preferences
from .locale import Locale
from . import armor
from .tutorial import Tutorial,BOXES


class Game:
    def __init__(self,screen,preferences=None,debug=False):
        self.screen=screen
        self.debug_enabled=debug;self.god_mode=False;self.free_buy=False;self.zoom_save_due=0
        self.rail_overlay=ui.Surface(screen.get_size(),ui.SRCALPHA)
        self.assets=Resources()
        self.audio=Audio(self.assets)
        self.preferences=preferences or Preferences()
        try:self.locale=Locale(self.preferences.language)
        except (OSError,ValueError):self.locale=Locale();self.preferences.language='english'
        self.t=self.locale
        self.themes=json.loads((DATA/'themes.json').read_text(encoding='utf8'))
        self.apply_theme()
        self.audio.volume=self.preferences.volume;self.audio.music_volume=self.preferences.music_volume
        self.set_vsync=lambda enabled:None
        self.exit_game=lambda:None
        self.audio.muted=not self.preferences.sound;self.audio.music_enabled=self.preferences.music
        self.toggle_fullscreen=lambda:None
        self.collisions=Collisions(self.assets)
        self.rooms=json.loads((DATA/'rooms.json').read_text(encoding='utf8'))
        self.room=self.rooms['room1']
        self.settings=json.loads((DATA/'gameplay.json').read_text(encoding='utf8'))
        self.rules=json.loads((DATA/'combat.json').read_text(encoding='utf8'))
        self.component_layers=json.loads((DATA/'render_layers.json').read_text(encoding='utf8'))
        self.component_order=0
        self.combat=Combat(self.rules)
        self.waves=Waves()
        self.room_name='room1'
        self.notice=''
        self.profile_error=False
        try:self.profile=Profile.load()
        except (OSError,ValueError,TypeError):
            self.profile=Profile();self.profile_error=True
            self.notice=self.t('notice.profile_error')
        self.paused=False;self.credits_time=0;self.teleport_age=-1
        self.menu=Menu();self.block_fire=False
        self.damage_flash=0
        self.death_marked=False
        self.death_age=-1;self.death_tip=0;self.death_scene=None;self.last_frame=None;self.death_button=None
        self.transition=None
        self.message='';self.message_alpha=0
        self.tutorial=None
        self.window_focused=True;self.visual_time=0;self.shake_offset=(0,0)
        self.portal_sparks=[];self.portal_clock=0
        self.building=False
        self.selling=False
        self.build_kind='turret'
        self.scale=1
        self.apply_theme()
        settings=self.settings['player']
        self.player=Player(*self.room['player_spawn'],self.rules['player']['speed'],self.rules['player']['acceleration'],settings['health'],settings['collision_radius'])
        self.circle_masks={}
        self.camera=ui.Vector2()
        self.set_room('room1')

    def apply_theme(self):
        import random
        if self.preferences.theme not in self.themes:self.preferences.theme='silver'
        selected=self.themes[self.preferences.theme]
        self.team_color=tuple(selected[0]);self.team_color2=tuple(selected[1])
        enemies=[name for name in self.themes if name!=self.preferences.theme]
        enemy=self.themes[random.SystemRandom().choice(enemies)]
        self.enemy_color=tuple(enemy[0]);self.enemy_color2=tuple(enemy[1])

    def draw_hud(self):
        s=self.ui_scale;t=self.t;c=self.combat;w=self.waves
        arena=self.room_name in [a['room'] for a in ARENAS.values()]
        width=300*s;map_height=0
        if self.preferences.minimap:self.draw_minimap();map_height=self.minimap_rect.h+6*s
        title=t('hud.arena',number=ARENAS[str(w.arena)]['number']) if arena else t('hud.tutorial' if self.tutorial else 'hud.base')
        extra=[]
        if self.building:extra.append(t(BUILDINGS[self.build_kind]))
        height=(64+len(extra)*23)*s
        rect=ui.Rect(8*s,8*s+map_height,width,height)
        self.hud_rect=ui.Rect(8*s,8*s,width,map_height+height);self.hud_buttons=[]
        ui.draw.rect(self.screen,(237,237,231,205),rect);ui.draw.rect(self.screen,(65,65,65),rect,1)
        if not arena or w.complete:self.menu.label(self,title,rect.x+10*s,rect.y+9*s,13*s,True)
        self.menu.label(self,t('ui.price',price=c.money),rect.x+10*s,rect.y+34*s,14*s)
        font=ui.font.SysFont('Arial',max(8,round(12*s)))
        right=[]
        if arena:right.append((t('hud.wave_timer',group=min(3,max(1,(w.number-1)//20+1)),wave=(w.number-1)%20+1 if w.number else 0,seconds=max(0,math.ceil(w.countdown))),rect.y+9*s))
        if c.equipped:
            name=t(f'weapon.{c.weapon}.name')
            right.append((t('hud.weapon_ammo',name=name,ammo=c.weapons[c.weapon].ammo) if c.weapon not in ('axe','repair') else name,rect.y+35*s))
        layer=self.screen.layer;self.screen.layer=layer+2
        for value,y in right:
            text=font.render(value,True,'black');self.screen.blit(text,(rect.right-10*s-text.get_width(),y))
        self.screen.layer=layer
        for i,text in enumerate(extra):self.menu.label(self,text,rect.x+10*s,rect.y+(59+i*23)*s,13*s)
        if arena and not w.complete:
            button=ui.Rect(rect.x+10*s,rect.y+5*s,100*s,24*s)
            self.menu.button(self,title,button.x,button.y,button.w,button.h,('wave',),enabled=self.player.health>0 and not self.paused)
            self.hud_buttons.append((button,('wave',)))

    def flush_zoom_settings(self,force=True):
        import time
        if not self.zoom_save_due or not force and time.monotonic()<self.zoom_save_due:return
        self.zoom_save_due=0
        try:self.preferences.save()
        except OSError:self.notice=self.t('notice.settings_error')

    def zoom_camera(self,steps):
        if self.death_age>=0:return
        import time
        previous=self.preferences.world_zoom
        zoom=round(max(.5,min(2,previous*1.1**max(-100,min(100,steps)))),4)
        if zoom==previous:return
        anchor=ui.mouse.get_pos();world=self.world_point(anchor)
        self.preferences.world_zoom=zoom
        self.update_world_scale()
        self.camera.update(world[0]-anchor[0]/self.scale,world[1]-anchor[1]/self.scale);self.clamp_camera()
        self.zoom_save_due=time.monotonic()+.25

    def update_world_scale(self):
        self.scale=min(self.screen.width/1280,self.screen.height/800)*self.preferences.world_zoom
        cfg=self.assets.manifest['fonts']['Font01']
        size=max(1,round(cfg['size']*96/72*min(self.screen.width/1280,self.screen.height/800)))
        if not getattr(getattr(self,'font',None),'world',False) or self.font.size!=size:
            base=ui.font.SysFont(cfg['family'],size,bool(cfg['bold']),bool(cfg['italic']))
            self.font=ui.Font(base.family,size,base.bold,base.italic);self.font.world=True
        self.font.scale=self.preferences.world_zoom

    def pointer_over_ui(self,pos):
        if getattr(self,'hud_rect',ui.Rect(0,0,0,0)).collidepoint(pos):return True
        if self.menu.open and self.menu.frame(self)[1].collidepoint(pos):return True
        return any(rect.collidepoint(pos) for rect,_,_ in self.menu.buttons)

    def set_room(self,name):
        self.teleport_age=0
        self.death_age=-1;self.death_scene=None;self.last_frame=None;self.death_button=None
        self.room_name=name;self.room=self.rooms[name]
        self.background=ui.image.load(ASSETS/self.assets.manifest['backgrounds'][self.room['background']]).convert()
        self.walls=[]
        for entry in self.room['walls']:
            mask,origin=self.collisions.mask(entry['sprite'])
            rect=ui.Rect(round(entry['x']+origin[0]),round(entry['y']+origin[1]),*mask.get_size())
            self.walls.append((entry,mask,rect))
        self.resize(self.screen)

    def enter_arena(self,arena=1,practice=False,bypass_lock=False):
        self.tutorial=None
        definition=ARENAS[str(arena)]
        required=definition.get('requires')
        if required and not self.profile.cleared(required) and not practice and not bypass_lock:
            self.notice=self.t('notice.unlock',arena=self.t(f'arena.{required}.title'));return False
        self.building=False
        self.selling=False
        self.set_room(definition['room'])
        self.player.x,self.player.y=self.room['player_spawn']
        self.player.vx=self.player.vy=0;self.player.vehicle_uid=0;self.player.mount_cooldown=0
        armor.equip(self.player,0);self.player.armor_owned=0;self.player.armor_cooldown=0;self.player.scorch_age=-1
        self.player.health=self.rules['player']['health']
        self.death_marked=False
        self.shake_offset=(0,0)
        self.portal_sparks=[]
        self.combat.workers.close()
        self.combat=Combat(self.rules);self.combat.free_buy=self.free_buy;self.waves=Waves(arena=arena,kind=definition['waves'][0][0])
        self.waves.practice=int(practice)
        difficulty=self.preferences.difficulty
        self.combat.money=(10000,5000,2500)[difficulty]
        self.combat.tax=definition.get('tax',(-.2,0,.2))[difficulty]
        self.combat.permanent_mines=definition.get('permanent_mines',False)
        from .mites import MoneyMite
        for displacement in definition.get('mites',[]):
            x,y=self.room['width']/2+displacement,self.room['height']/2
            self.combat.mites.append(MoneyMite(x,y,x,y,angle=0 if displacement>0 else 180))
        self.waves.difficulty=(.03,.05,.07)[difficulty]
        self.resize(self.screen)
        self.notice=self.t('notice.arena',title=self.t(f'arena.{arena}.title'),description=self.t(f'arena.{arena}.description'))
        self.show_message(self.t(f'arena.{arena}.intro_message'),2.5)
        self.load_arena_checkpoint()
        return True

    def enter_tutorial(self):
        self.return_to_base();self.set_room('room2')
        self.player.x,self.player.y=self.room['player_spawn'];self.tutorial=Tutorial();self.tutorial.start(self)
        self.resize(self.screen);self.notice=self.t('notice.tutorial')
        return True

    def resize(self,screen):
        self.screen=screen
        self.rail_overlay=ui.Surface(screen.get_size(),ui.SRCALPHA)
        # Stable logical viewport: resizing enlarges the scene, not its field
        # of view. Draw assets at final resolution to keep text sharp.
        base_scale=min(screen.get_width()/1280,screen.get_height()/800)
        self.scale=base_scale*self.preferences.world_zoom
        self.ui_scale=base_scale*self.preferences.ui_scale
        self.scaled_background=self.background
        self.update_world_scale()
        self.ui_font=ui.font.SysFont('Arial',max(12,round(20*self.ui_scale)))
        self.camera.update(self.player.x-screen.get_width()/self.scale/2,self.player.y-screen.get_height()/self.scale/2)
        self.clamp_camera()

    def request_room(self,target):
        if self.transition:return False
        if target not in ('h','b','t'):
            required=ARENAS[str(target)].get('requires')
            if required and not self.profile.cleared(required):
                self.notice=self.t('notice.unlock',arena=self.t(f'arena.{required}.title'));return False
        self.transition=Transition(target);self.block_fire=True
        self.teleport_age=0
        self.audio.loop('Flamesound',False)
        return True

    def return_to_base(self):
        self.tutorial=None
        armor.equip(self.player,0);self.player.armor_owned=0;self.player.armor_cooldown=0;self.player.scorch_age=-1
        self.building=False;self.selling=False;self.paused=False;self.death_marked=False
        self.shake_offset=(0,0)
        self.combat.workers.close()
        self.combat=Combat(self.rules);self.combat.free_buy=self.free_buy;self.waves=Waves()
        self.set_room('room1');self.player.x,self.player.y=self.room['player_spawn']
        self.player.vx=self.player.vy=0;self.player.vehicle_uid=0;self.player.mount_cooldown=0
        self.player.health=self.rules['player']['health']
        self.resize(self.screen);self.notice=''

    def portals(self):
        if self.room_name=='room1':
            yield 't',self.room['width']/2,self.room['height']/2-340,self.t('portal.tutorial'),True
            for number,definition in ARENAS.items():
                required=definition.get('requires')
                yield int(number),*definition['portal'],self.t(f'arena.{number}.title'),not required or self.profile.cleared(required)
        elif self.waves.return_ready:
            if self.tutorial:yield 'h',BOXES[8]['x'],BOXES[8]['y'],self.t('portal.base'),True
            else:yield 'h',self.room['width']/2,self.room['height']/2,self.t('portal.base'),True

    def draw_portals(self):
        layer=self.screen.layer
        for target,x,y,title,unlocked in self.portals():
            px,py=self.point(x,y)
            layer=self.screen.layer;self.screen.layer=50000
            fade=max(0,min(1,2-2.5*self.transition.alpha)) if self.transition and self.transition.phase=='out' else 1
            self.draw_sprite('BigTankMask',x,y,scale=1.4,tint=self.team_color,alpha=fade if unlocked else .3*fade)
            self.screen.layer=150001
            self.draw_sprite('BigTankMask',x,y,scale=1.15,tint=self.team_color2,alpha=fade if unlocked else .3*fade)
            self.draw_sprite('BigTankMask',x,y,tint=(255,255,255),alpha=fade if unlocked else .3*fade)
            for index,line in enumerate((self.t('portal.home'),) if target=='h' else (self.t('portal.tutorial'),) if target=='t' else (self.t('portal.area'),ARENAS[str(target)]['number'])):
                if not hasattr(self,'portal_fonts'):self.portal_fonts={}
                key=line,self.font.size
                if key not in self.portal_fonts:
                    width=self.font.render(line,True,'black').width
                    size=max(1,math.floor(self.font.size*min(1,48*self.scale/max(1,width))))
                    font=ui.Font(self.font.family,size,self.font.bold,self.font.italic);font.world=True;self.portal_fonts[key]=font
                font=self.portal_fonts[key];font.scale=self.font.scale
                label=font.render(line,True,'black');label.set_alpha(round(255*(fade if unlocked else .3*fade)))
                self.screen.blit(label,label.get_rect(center=(round(px),round(py+(index-(0 if target in ('h','t') else .5))*18*self.scale))))
            if self.room_name=='room1' and type(target) is int:
                self.screen.layer=300000
                cfg=self.assets.manifest['fonts']['UIFont02']
                font=ui.font.SysFont(cfg['family'],max(1,round(cfg['size']*96/72*self.scale)),bool(cfg['bold']))
                suffix=ARENA_SUFFIXES[target]
                for dy,field,text in ((70,'no_weapons',self.t('award.no_weapons')),(90,'no_structures',self.t('award.no_structures'))):
                    label=font.render(text,True,'black');label.set_alpha(191)
                    self.screen.blit(label,label.get_rect(center=(round(px),round(py+dy*self.scale))))
                    self.draw_sprite('SmallTankMask',x-85,y+dy,tint=(255,255,255) if getattr(self.profile,f'{field}_{suffix}') else (0,0,0),alpha=.5)
                self.screen.layer=layer
        self.screen.layer=75000
        for x,y,_,_,_,age in self.portal_sparks:
            ui.draw.circle(self.screen,(128,60,255,round(255*min(1,2.5*age))),self.point(x,y),min(15,25*age)*self.scale)
        self.screen.layer=layer

    def step_portal_sparks(self,dt):
        self.portal_clock+=dt
        frames=int((self.portal_clock+1e-9)*50);self.portal_clock-=frames/50
        for _,x,y,_,unlocked in self.portals():
            if not unlocked:continue
            for _ in range(frames):
                angle=self.combat.effects.rng.uniform(0,2*math.pi)
                self.portal_sparks.append([x+100*math.cos(angle),y+100*math.sin(angle),x,y,self.combat.effects.rng.uniform(200,300),0])
        alive=[]
        for spark in self.portal_sparks:
            x,y,tx,ty,speed,age=spark;distance=math.hypot(tx-x,ty-y)
            travel=min(distance,speed*dt)
            if distance-travel<=15:continue
            alive.append([x+(tx-x)*travel/distance,y+(ty-y)*travel/distance,tx,ty,speed,age+dt])
        self.portal_sparks=alive

    def portal_at(self,x,y,mouse):
        mask,origin=self.collisions.mask('BigTankMask')
        px=round(mouse[0])-round(x+origin[0]);py=round(mouse[1])-round(y+origin[1])
        return 0<=px<mask.get_size()[0] and 0<=py<mask.get_size()[1] and bool(mask.get_at((px,py)))

    def clamp_camera(self):
        self.camera.x=max(0,min(self.camera.x,max(0,self.room['width']-self.screen.get_width()/self.scale)))
        self.camera.y=max(0,min(self.camera.y,max(0,self.room['height']-self.screen.get_height()/self.scale)))

    def blocked(self,x,y,radius):
        size=round(radius*2+1)
        rect=ui.Rect(round(x-radius),round(y-radius),size,size)
        if size not in self.circle_masks:
            image=ui.Surface((size,size),ui.SRCALPHA)
            ui.draw.circle(image,'white',(round(radius),round(radius)),round(radius))
            self.circle_masks[size]=ui.mask.from_surface(image)
        circle=self.circle_masks[size]
        return any(rect.colliderect(wall_rect) and wall_mask.overlap(circle,(rect.x-wall_rect.x,rect.y-wall_rect.y)) is not None
                   for _,wall_mask,wall_rect in self.walls)

    def step(self,horizontal,vertical,mouse_screen,dt=.02,firing=False):
        self.flush_zoom_settings(force=False)
        self.audio.loop('Music01',True)
        if self.death_age>=0:
            self.death_age+=dt
            if self.death_age>=10-1e-9:self.respawn()
            return
        self.visual_time+=dt
        self.credits_time=max(0,self.credits_time-dt)
        if self.teleport_age>=0:
            previous=self.teleport_age
            self.teleport_age+=dt
            if previous<.2-1e-9<=self.teleport_age:self.audio.play('sndTeleport')
            if self.teleport_age>=2.2:self.teleport_age=-1
        if not self.paused:self.message_alpha=max(0,self.message_alpha-.25*dt)
        if not self.transition:self.step_portal_sparks(dt)
        if self.transition:
            if self.player.health>0 and not self.player.vehicle_uid:
                self.player.step(horizontal,vertical,self.world_point(mouse_screen),self.blocked,dt)
                damping=.25**(50*dt)
                self.player.vx*=damping;self.player.vy*=damping
            event=self.transition.step(dt)
            if event=='switch':
                if self.transition.target in ('h','b'):self.return_to_base()
                elif self.transition.target=='t':self.enter_tutorial()
                else:self.enter_arena(self.transition.target)
            elif event=='done':self.transition=None
            return
        if not firing:self.block_fire=False
        firing=firing and not self.block_fire and not self.pointer_over_ui(mouse_screen)
        player_flames=not self.paused and firing and self.combat.weapon=='flamethrower' and self.combat.equipped and self.combat.flamethrower_ammo>0 and self.player.health>0 and not self.player.vehicle_uid and not self.building and not self.selling and not self.pointer_over_ui(mouse_screen)
        self.audio.loop('Flamesound',player_flames or not self.paused and self.combat.enemy_flame_sound)
        if self.paused:return
        self.damage_flash=max(0,self.damage_flash-dt)
        mouse=self.world_point(mouse_screen)
        previous_angle=self.player.angle
        swinging=self.combat.swing_remaining>0
        mounted=self.combat.control_vehicle(self.player,mouse,horizontal,vertical,dt,self.blocked,self.collisions)
        if self.player.health>0 and not mounted:self.player.step(horizontal,vertical,mouse,self.blocked,dt)
        if (swinging or firing and self.combat.equipped and self.combat.owns(self.combat.weapon) and self.combat.weapon in ('axe','repair')) and (not mounted or self.combat.weapon=='repair'):self.player.angle=(previous_angle+900*dt)%360
        self.combat.update_commands(self.player,mouse,dt,self.collisions)
        self.combat.room_size=self.room['width'],self.room['height']
        if firing and not self.building and not self.selling and not self.pointer_over_ui(mouse_screen):self.combat.hold_fire(self.player,dt)
        health_before=self.player.health
        if self.tutorial:self.tutorial.step(self,dt)
        previous_enemies=list(self.combat.enemies)
        self.combat.step(self.player,dt,self.blocked,self.collisions)
        if self.debug_enabled and self.god_mode:self.player.health=max(health_before,self.player.health)
        if self.tutorial:self.tutorial.deaths(self,previous_enemies)
        self.shake_offset=(self.combat.effects.rng.randint(-2,2),self.combat.effects.rng.randint(-2,2)) if self.preferences.camera_shake and self.combat.effects.shake>0 else (0,0)
        if self.player.health<=0 and self.death_age<0:
            self.begin_death();return
        self.audio.loop('Flamesound',player_flames or self.combat.enemy_flame_sound)
        if self.player.vehicle_uid and not any(t.uid==self.player.vehicle_uid and t.kind in ('buggy','light_tank','juggernaut') for t in self.combat.structures):
            self.player.vehicle_uid=0;self.player.mount_cooldown=.5
        self.combat.bullets=[bullet for bullet in self.combat.bullets if -200<=bullet.x<=self.room['width']+200 and -200<=bullet.y<=self.room['height']+200]
        if self.player.health<health_before:self.damage_flash=1
        self.flush_audio()
        if self.room_name in [arena['room'] for arena in ARENAS.values()] and self.player.health>0:
            for event in self.waves.step(self.combat,self.room,dt):
                if event in ('level_clear','area_clear'):
                    self.notice=self.t('message.level_clear') if event=='level_clear' else self.t('message.area_clear')
                    self.show_message(self.t('message.level_clear') if event=='level_clear' else self.t('message.area_clear'))
                elif event=='checkpoint':
                    self.audio.play('Victory')
                    try:save_game(self);self.notice=self.t('message.checkpoint');self.show_message(self.notice)
                    except OSError:self.notice=self.t('notice.checkpoint_error')
                elif event=='return':
                    self.audio.play('Victory')
                    heading=self.t('message.game_complete') if self.waves.arena>=5 else self.t('message.door_open') if not self.profile.cleared(self.waves.arena) and not self.waves.practice else ''
                    award=self.t('message.no_structures') if not self.combat.structures_built else self.t('message.no_weapons') if not self.combat.has_weapons else ''
                    self.show_message('#'.join(part for part in (heading,self.t('message.return'),award) if part))
                    self.notice=self.t('notice.return')
                    if self.waves.practice:self.notice=self.t('notice.practice_clear')
                    elif not self.profile_error:
                        try:
                            self.profile.victory(self.combat.has_weapons,structures_built=self.combat.structures_built,arena=self.waves.arena)
                            self.notice=self.t('notice.arena_clear',arena=self.t(f'arena.{self.waves.arena}.title'))
                        except OSError:self.notice=self.t('notice.progress_error')
        if self.player.health>0 and not self.building and not self.selling:
            for target,x,y,_,unlocked in self.portals():
                if unlocked and self.collisions.overlap(self.collisions.mask('BigTankMask'),x,y,self.collisions.mask(self.collisions.ally_name(self.player),angle=self.player.angle),self.player.x,self.player.y):
                    self.request_room(target);break
        width,height=self.screen.get_width()/self.scale,self.screen.get_height()/self.scale
        edge_width=10*self.scale
        edge=self.window_focused and (mouse_screen[0]<edge_width or mouse_screen[0]>self.screen.get_width()-edge_width or mouse_screen[1]<edge_width or mouse_screen[1]>self.screen.get_height()-edge_width)
        target=mouse if edge else (self.player.x,self.player.y)
        border=10 if edge else 250
        for axis,size,t in (('x',width,target[0]),('y',height,target[1])):
            old=getattr(self.camera,axis);b=min(border,size/2);desired=old
            if t<old+b:desired=t-b
            elif t>old+size-b:desired=t-size+b
            # Gameplay menu sets GM view_hspeed/view_vspeed to 10 per 50 Hz step.
            setattr(self.camera,axis,old+max(-500*dt,min(500*dt,desired-old)))
        self.clamp_camera()

    def point(self,x,y):
        return (x-self.camera.x+self.shake_offset[0])*self.scale,(y-self.camera.y+self.shake_offset[1])*self.scale

    def world_point(self,screen_point):
        return screen_point[0]/self.scale+self.camera.x-self.shake_offset[0],screen_point[1]/self.scale+self.camera.y-self.shake_offset[1]

    def flush_audio(self):
        for name in set(self.combat.events):
            if name=='low_ammo':self.on_low_ammo()
            else:self.audio.play(name)
        self.combat.events.clear()

    def on_low_ammo(self):
        self.audio.play('AccessDenied')
        self.show_message(self.t('message.low_ammo'),1)

    def close_menu(self):
        if self.menu.open:self.audio.play('PageFlip')
        self.menu.open=False

    def begin_death(self):
        self.death_marked=True;self.death_age=0
        self.death_tip=self.combat.effects.rng.randrange(10)
        self.death_scene=list(self.last_frame) if self.last_frame is not None else None
        self.player.vx=self.player.vy=0;self.paused=False;self.credits_time=0
        self.building=False;self.selling=False;self.block_fire=True
        self.close_menu();self.menu.buttons=[];self.hud_buttons=[]
        self.audio.loop('Flamesound',False);self.audio.play('AccessDenied')

    def load_arena_checkpoint(self):
        from .session import SAVE_PATH
        room=self.room_name
        if room in [a['room'] for a in ARENAS.values()] and SAVE_PATH.exists():
            try:
                checkpoint=json.loads(SAVE_PATH.read_text(encoding='utf8'))
                if checkpoint.get('room')==room and checkpoint.get('player',{}).get('health',0)>0:
                    transition=self.transition
                    load_game(self,SAVE_PATH);self.transition=transition
                    self.message='';self.message_alpha=0
                    return True
            except (OSError,ValueError,KeyError,TypeError,AttributeError):self.notice=self.t('notice.load_error')
        return False

    def respawn(self):
        room=self.room_name;arena=self.waves.arena;practice=bool(self.waves.practice)
        if not self.load_arena_checkpoint():
            if self.tutorial:self.enter_tutorial()
            elif room=='room1':self.return_to_base()
            else:self.enter_arena(arena,practice=practice,bypass_lock=True)
        self.death_marked=False;self.death_age=-1;self.death_scene=None;self.last_frame=None;self.death_button=None
        self.message='';self.message_alpha=0;self.damage_flash=0;self.close_menu();self.block_fire=True

    def draw_death(self):
        screen=self.screen;s=self.ui_scale;screen.layer=30000000
        # GM freezes the last frame and tints it light gray. No image files
        # or framebuffer screenshots are needed for the retained scene.
        ui.draw.rect(screen,(0,0,0,63),screen.get_rect())
        screen.layer=30000001
        alpha=min(1,max(0,2.5-.25*self.death_age))
        self.draw_center_message(self.t('death.title'),alpha=alpha,color='red',outline='black')
        tip=self.t(f'death.tip.{self.death_tip}')
        tip_y=screen.height/2+(45+(len(tip.split('\n'))-1)*14*1.3/2)*s
        self.draw_center_message(tip,alpha=alpha,size=14*s,y=tip_y,color='red',outline='black')
        definition=self.assets.sprites['Button01'];width=definition['frames'][0]['width']*s;height=definition['frames'][0]['height']*s
        cy=min(screen.height-height/2-8*s,screen.height/2+200*s)
        rect=ui.Rect(round(screen.width/2-width/2),round(cy-height/2),round(width),round(height));self.death_button=rect
        screen.layer=30000003
        self.assets.draw_sprite(screen,'Button01',0,rect.centerx,rect.centery,s,s,color=(128,128,128) if rect.collidepoint(ui.mouse.get_pos()) else (255,0,0))
        font=self.assets.manifest['fonts']['UIFont01']
        label=ui.font.SysFont(font['family'],max(8,round(font['size']*96/72*s)),bool(font['bold'])).render(self.t('death.respawn'),True,'black')
        screen.blit(label,label.get_rect(center=rect.center));self.menu.buttons=[];self.hud_buttons=[]

    def draw_center_message(self,text,alpha=1,size=None,y=None,color='black',outline='white'):
        cfg=self.assets.manifest['fonts']['Font05']
        font=ui.font.SysFont(cfg['family'],max(8,round(size or cfg['size']*96/72*self.ui_scale)),bool(cfg['bold']))
        rows=text.split('\n');cx=self.screen.width/2;cy=self.screen.height/2 if y is None else y
        layer=self.screen.layer;spacing=font.size*1.3
        for index,row in enumerate(rows):
            center=(cx,cy+(index-(len(rows)-1)/2)*spacing)
            self.screen.layer=layer
            for dx,dy in ((1,1),(1,-1),(-1,1),(-1,-1)):
                label=font.render(row,True,outline);label.set_alpha(round(255*alpha))
                self.screen.blit(label,label.get_rect(center=(center[0]+dx*self.ui_scale,center[1]+dy*self.ui_scale)))
            self.screen.layer=layer+1
            label=font.render(row,True,color);label.set_alpha(round(255*alpha))
            self.screen.blit(label,label.get_rect(center=center))
        self.screen.layer=layer

    def show_message(self,text,alpha=1.5):
        self.message=text.replace('#','\n');self.message_alpha=alpha

    def cycle_weapon(self,direction):
        if self.death_age>=0 or self.transition or self.tutorial and self.tutorial.stage<5:return
        names=[name for name,_ in WEAPONS]
        start=names.index(self.combat.weapon) if self.combat.weapon in names else (-1 if direction>0 else 0)
        for offset in range(1,len(names)+1):
            name=names[(start+offset*direction)%len(names)]
            if self.combat.owns(name) and self.combat.weapons[name].enabled:
                self.combat.equip(name);break

    def draw_sprite(self,name,x,y,scale=1,angle=0,tint=(255,255,255),alpha=1):
        layer=self.screen.layer
        if name in self.component_layers:self.screen.layer=self.component_layers[name]+self.component_order
        x,y=self.point(x,y)
        self.assets.draw_sprite(self.screen,name,0,x,y,self.scale*scale,self.scale*scale,angle,color=tint,alpha=alpha)
        self.screen.layer=layer

    def draw(self):
        if self.death_age>=0 and self.death_scene is not None:
            self.screen.commands.clear();self.screen.commands.extend(self.death_scene)
            self.draw_death();return
        self.screen.layer=0
        self.screen.fill('black')
        self.screen.commands.append(('image',self.background,round((-self.camera.x+self.shake_offset[0])*self.scale),round((-self.camera.y+self.shake_offset[1])*self.scale),self.background.width*self.scale,self.background.height*self.scale))
        self.screen.layer=150001
        for mark in self.combat.effects.marks:
            for sprite in ('BlastSprite01','BlastSprite02','BlastSprite03'):
                self.draw_sprite(sprite,mark.x,mark.y,scale=mark.scale,angle=mark.angle,tint=(0,0,0),alpha=max(0,.1-.005*mark.age))
        self.screen.layer=970000
        self.draw_portals()
        # GM projectiles have depth 10; turret tops have depth -20/-25.
        # Hide the initial centre-spawned bullet beneath its own barrel.
        self.screen.layer=50000
        self.draw_projectiles()
        self.screen.layer=100000
        for wall,_,_ in self.walls:self.draw_sprite(wall['sprite'],wall['x'],wall['y'],tint=(75,75,75))
        self.screen.layer=200000
        for index,turret in enumerate(self.combat.structures):
            self.component_order=index*2
            self.screen.layer=200000+index*2
            if turret.kind=='juggernaut':self.draw_juggernaut(turret)
            elif turret.kind=='light_tank':
                self.draw_sprite('Vehicle0102',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
                self.draw_sprite('Vehicle0101',turret.x,turret.y,angle=turret.angle,alpha=turret.seat_alpha)
                self.draw_sprite('Vehicle0103',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
            elif turret.kind=='buggy':self.draw_buggy(turret)
            elif turret.kind=='factory':self.draw_factory(turret)
            elif turret.kind=='boss_factory':self.draw_boss_factory(turret)
            elif turret.kind in ('pistol_factory','axe_factory'):self.draw_pistol_factory(turret)
            elif turret.kind=='generator':self.draw_sprite('Square02',turret.x,turret.y,tint=self.team_color)
            elif turret.kind=='laser':
                self.draw_sprite('TurretBase01',turret.x,turret.y,tint=self.team_color2)
                self.draw_sprite('LaserTurretTop',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
            elif turret.kind=='minigun_turret':
                self.draw_sprite('MachineTurretBase',turret.x,turret.y,tint=self.team_color2)
                self.draw_sprite('MinigunTurretTop',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
            elif turret.kind=='cannon':
                self.draw_sprite('TurretBase01',turret.x,turret.y,tint=self.team_color2)
                self.draw_sprite('TurretTop01',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
            elif turret.kind=='command':
                self.draw_sprite('CommandBottom2' if turret.command_active else 'CommandBottom',turret.x,turret.y,tint=self.team_color)
                self.draw_sprite('CommandTop',turret.x,turret.y,alpha=turret.pulse_alpha)
            else:
                self.draw_sprite('MachineTurretBase',turret.x,turret.y,tint=self.team_color2)
                self.draw_sprite('MachineTurretTop',turret.x,turret.y,angle=turret.angle,tint=self.team_color)
            hx,hy=(-13,-3) if turret.kind=='factory' else (-96,0) if turret.kind=='boss_factory' else (25,-25) if turret.kind=='command' else (0,0)
            x,y=self.point(*offset(turret,8)) if turret.kind=='buggy' else self.point(*offset(turret,10)) if turret.kind=='light_tank' else self.point(turret.x+hx,turret.y+hy)
            text=self.font.render(str(math.ceil(turret.health)),True,'black')
            if turret.kind in ('turret','minigun_turret','laser','cannon','buggy'):self.screen.layer=self.component_layers['MachineTurretTop' if turret.kind=='buggy' else STRUCTURES[turret.kind]['top']]+self.component_order+1
            self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.screen.layer=300000
        self.component_order=0
        for drone in self.combat.drones:self.draw_sprite('MiteTank',drone.x,drone.y,angle=drone.angle,tint=self.team_color)
        if self.building:
            x,y=self.world_point(ui.mouse.get_pos())
            x,y=self.snap_build(x,y)
            valid=self.can_build(x,y)
            self.draw_sprite(STRUCTURES[self.build_kind]['preview'],x,y,tint=(60,200,100) if valid else (200,60,60),alpha=.5)
        for coin in self.combat.coins:self.draw_coin(coin)
        for mite in self.combat.mites:self.draw_money_mite(mite)
        self.screen.layer=400000
        for index,unit in enumerate(self.combat.units):
            self.screen.layer=400000+index*3
            sprite=UNIT_TYPES[unit.kind]['sprite']
            if unit.roam:
                self.draw_sprite(sprite,unit.x,unit.y,scale=1.2,angle=unit.angle,tint=(255,0,0),alpha=.5)
            self.screen.layer=400001+index*3
            self.draw_sprite(sprite,unit.x,unit.y,angle=unit.angle,tint=self.team_color)
            if unit.kind!='deployed_robot':
                x,y=self.point(unit.x,unit.y);text=self.font.render(str(math.ceil(unit.health)),True,'black')
                self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.screen.layer=500000
        enemy_sprites={kind:definition['sprite'] for kind,definition in ENEMY_TYPES.items()}
        for index,enemy in enumerate(self.combat.enemies):
            self.component_order=(len(self.combat.structures)+index)*2
            self.screen.layer=500000+index*2
            size=1
            if enemy.kind in ('scatter','scatter_parent','pistol_scatter'):size=1+min(enemy.age,.6-enemy.age)*2.5
            sprite='TankPipe02' if enemy.kind in ('bomber','heavy_apc_unit') and enemy.reload_timer>0 else enemy_sprites[enemy.kind]
            if enemy.kind=='mega_flame':sprite='BossRailgun' if enemy.phase==0 else 'BossFlamethrower'
            tint=(255,0,0) if enemy.kind=='mega_flame' and enemy.phase==2 else self.enemy_color2
            self.draw_sprite(sprite,enemy.x,enemy.y,scale=max(.1,size),angle=enemy.angle,tint=tint)
            if enemy.kind=='mega_juggernaut':
                self.draw_sprite('JuggernaughtBarrier',enemy.x,enemy.y,angle=enemy.angle,tint=tint)
                self.draw_sprite('Vehicle0101',*offset(enemy,-31),angle=enemy.angle,alpha=.5)
                for side,name,sign in ((-99,'JuggerNaughtDoor02',1),(99,'JuggernaughtDoor01',-1)):
                    self.draw_sprite(name,*offset(enemy,118,side),angle=enemy.angle+sign*(enemy.door_angle if enemy.phase==2 else 0),tint=tint)
                if enemy.turret_health>0:
                    pos=offset(enemy,self.combat.data[enemy.kind]['turret_offset'])
                    self.draw_sprite('MinigunTurretTop',*pos,angle=enemy.turret_angle,tint=tint)
                    x,y=self.point(*pos);text=self.font.render(str(math.ceil(enemy.turret_health)),True,'black')
                    layer=self.screen.layer;self.screen.layer=self.component_layers['MinigunTurretTop']+self.component_order+1
                    self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
                    self.screen.layer=layer
            if enemy.kind=='enemy_tank':
                self.draw_sprite('Vehicle0101',enemy.x,enemy.y,angle=enemy.angle,alpha=.5)
                self.draw_sprite('Vehicle0103',enemy.x,enemy.y,angle=enemy.angle,tint=self.enemy_color)
            if enemy.kind in ('apc','heavy_apc'):
                for name,side,sign in (('APCBase02',-32,1),('APCBase03',32,-1)):
                    x,y=offset(enemy,39,side)
                    self.draw_sprite(name,x,y,angle=enemy.angle+sign*enemy.door_angle,tint=self.enemy_color)
                if enemy.turret_health>0:
                    x,y=offset(enemy,-104)
                    self.draw_sprite('TurretTop01' if enemy.kind=='heavy_apc' else 'MachineTurretTop',x,y,angle=enemy.turret_angle,tint=self.enemy_color)
            if enemy.kind not in ('child','scatter','pistol_child','pistol_scatter','mega_unit'):
                text=self.font.render(str(math.ceil(enemy.health)),True,'black')
                x,y=self.point(*offset(enemy,10)) if enemy.kind=='enemy_tank' else self.point(enemy.x,enemy.y)
                self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.screen.layer=600000
        self.component_order=0
        self.draw_rails()
        self.draw_lasers()
        self.screen.layer=700000
        for bomb in self.combat.bombs:self.draw_sprite('Pipe',bomb.x,bomb.y,scale=bomb.size,angle=bomb.angle,tint=self.team_color)
        for bomb in self.combat.enemy_bombs:self.draw_sprite('Pipe',bomb.x,bomb.y,scale=bomb.size,angle=bomb.angle,tint=self.enemy_color)
        for blast in self.combat.blasts:
            if not blast.kind:self.draw_sprite('BlastSprite03',blast.x,blast.y,scale=blast.scale,angle=blast.age*500,tint=(255,194,14) if blast.scale==5 else (230,150,0),alpha=.15*(1-blast.age/.3))
        for x,y,age in self.combat.effects.bursts:
            self.draw_sprite('Circle01',x,y,scale=1+100*age,tint=(255,255,max(0,round(255-510*age))),alpha=max(0,.15-.5*age))
        for particle in self.combat.effects.smoke:
            self.draw_sprite('Ball02',particle.x,particle.y,scale=.05+5*particle.age,tint=(192,192,192),alpha=max(0,.5-particle.age))
        for particle in self.combat.effects.particles:
            self.draw_sprite('Ball02',particle.x,particle.y,scale=.1+5*particle.age,tint=(255,min(255,round(637.5*particle.age)),0),alpha=max(0,.2-.5*particle.age))
        for x,y,_,_,_,angle,_,sx,sy,age,big,hostile in self.combat.effects.gibs:
            self.assets.draw_sprite(self.screen,'Giblet01',0,*self.point(x,y),sx*(2 if big else 1)*(1-age)*self.scale,sy*(2 if big else 1)*(1-age)*self.scale,angle,self.enemy_color if hostile else self.team_color,.5*(1-age))
        for flame in self.combat.flames:
            if flame.kind!=2:self.draw_sprite('Ball02',flame.x,flame.y,scale=.1+5*flame.age,tint=(255,min(255,round(flame.age*255)),0),alpha=.5*(1-flame.age))
        for flame in self.combat.enemy_flames:
            if flame.kind!=2:self.draw_sprite('Ball02',flame.x,flame.y,scale=flame.start_scale+flame.growth*flame.age,tint=(255,min(255,round(flame.age*195)),0),alpha=max(0,flame.alpha*(1-flame.age/flame.duration)))
        for zone in self.combat.fire_zones:
            self.draw_sprite('FireBall',zone.x,zone.y,scale=zone.scale,alpha=zone.alpha)
        if self.player.scorch_age>=0:
            age=self.player.scorch_age;phase=age%2.4
            self.draw_sprite('FireBall',self.player.scorch_x,self.player.scorch_y,scale=min(1.5,.025+1.25*age),tint=(255,150,0),alpha=.05+.1*(phase if phase<=1.2 else 2.4-phase))
        for particle in self.combat.healing_effects.particles:
            self.draw_sprite('HealLogo',particle.x,particle.y,scale=particle.scale,tint=(0,150,0),alpha=particle.alpha)
        self.screen.layer=800000
        p=self.player
        for barrier in armor.barriers(p):self.draw_sprite('SuitBarrier01',barrier.x,barrier.y,angle=barrier.angle,tint=self.team_color)
        if p.warp_time:self.draw_sprite('Bolt',p.warp_x,p.warp_y,angle=p.warp_angle,tint=self.team_color,alpha=min(1,p.warp_time*5))
        for scale in (1,.75,.5):self.draw_sprite('AxeMask02',p.x,p.y,scale,tint=self.team_color,alpha=.05)
        sprites={'pistol':'TankPistol','shotgun':'TankShotgun','machinegun':'TankMachinegun','axe':'TankAxe','repair':'TankRepair','railgun':'TankRailgun'}
        sprites['pipebomb']='TankPipe02' if self.combat.bombs else 'TankPipe01'
        sprites['rpg']='TankRPG02' if self.combat.rpg_cooldown else 'TankRPG01'
        sprites['flamethrower']='TankFlamethrower'
        sprites['minigun']='TankMinigun'
        if p.health>0:
            name=sprites[self.combat.weapon] if self.combat.equipped else self.settings['player']['sprite']
            self.screen.layer=799997
            self.draw_sprite(name,p.x+5,p.y+5,angle=p.angle,tint=(0,0,0),alpha=.1)
            self.screen.layer=800000
            if p.armor:self.draw_sprite(f'Suit0{p.armor}',p.x,p.y,angle=p.angle,tint=self.team_color,alpha=.5 if p.armor_cooldown else 1)
            self.screen.layer=800001
            distance=80+20*math.cos(self.visual_time*50*math.pi/40)
            for index in range(3):
                angle=self.visual_time*50+index*120;a=math.radians(angle)
                self.draw_sprite('Crosshairs02',p.x+distance*math.cos(a),p.y-distance*math.sin(a),angle=angle+180,tint=(255,0,0),alpha=.1)
            self.draw_sprite(sprites[self.combat.weapon] if self.combat.equipped else self.settings['player']['sprite'],p.x,p.y,angle=p.angle,tint=self.team_color)
            text=self.font.render(str(math.ceil(p.health)),True,'black')
            x,y=self.point(p.x,p.y)
            self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.draw_command_overlays()
        if self.teleport_age>=.2 and self.player.health>0:
            age=self.teleport_age-.2;size=max(0,min(age,2-age));self.screen.layer=985000
            for index in range(10):self.draw_sprite('AxeMask02',p.x,p.y,scale=(.10+.15*index)*size,alpha=.1*size)
            flash=max(0,min(1,2*(age-.5),2*(1.5-age)))
            if flash:
                name=sprites[self.combat.weapon] if self.combat.equipped else self.settings['player']['sprite']
                self.draw_sprite(name,p.x,p.y,angle=p.angle,alpha=flash)
        self.screen.layer=150000
        if self.tutorial:self.tutorial.draw(self)
        self.screen.layer=1000000
        self.draw_hud()
        if self.damage_flash:
            ui.draw.rect(self.screen,(round(230*self.damage_flash),0,0),self.screen.get_rect(),max(1,round(12*self.ui_scale*self.damage_flash)))
        self.screen.layer=10000000
        if self.message_alpha and not self.paused:
            self.draw_center_message(self.message,alpha=min(1,self.message_alpha))
            if self.message==self.t('message.low_ammo'):self.draw_center_message(self.t('hud.buy_ammo'),alpha=min(1,self.message_alpha),size=14*self.ui_scale,y=self.screen.height/2+45*self.ui_scale)
        if self.paused:
            self.screen.layer=9000000
            ui.draw.rect(self.screen,(0,0,0,110),self.screen.get_rect())
            self.screen.layer=9000001
            if self.credits_time:self.draw_center_message(self.t('credits.text'))
            else:
                self.draw_center_message(self.t('hud.paused'))
                self.draw_center_message(self.t('hud.resume'),size=14*self.ui_scale,y=self.screen.height/2+45*self.ui_scale)
            self.screen.layer=10000000
        if self.menu.open:self.menu.draw(self)
        else:self.menu.draw_tabs(self)
        if self.selling:
            cfg=self.assets.manifest['fonts']['Cash03font']
            font=ui.font.SysFont(cfg['family'],max(20,round(cfg['size']*96/72*self.ui_scale)),True)
            layer=self.screen.layer;x,y=ui.mouse.get_pos()
            for dx,dy in ((1,1),(1,-1),(-1,1),(-1,-1),(0,0)):
                self.screen.layer=layer+int(not(dx or dy))
                text=font.render(self.t('ui.currency'),True,(255,0,0) if not(dx or dy) else 'white')
                self.screen.blit(text,text.get_rect(center=(round(x+dx*self.ui_scale),round(y+dy*self.ui_scale))))
            self.screen.layer=layer
        if self.transition:
            self.screen.layer=20000000
            ui.draw.rect(self.screen,(0,0,0,round(255*min(1,self.transition.alpha))),self.screen.get_rect())
        if self.death_age>=0:
            self.death_scene=list(self.screen.commands);self.draw_death()
        else:self.last_frame=list(self.screen.commands)

    def draw_command_overlays(self):
        for tower in self.combat.structures:
            if tower.kind!='command' or not tower.command_active or tower.health<=0:continue
            center=self.point(tower.target_x,tower.target_y)
            self.screen.layer=985000
            for radius in (100,200):ui.draw.circle(self.screen,(255,0,0,26),center,radius*self.scale)
            self.screen.layer=985001
            ui.draw.line(self.screen,'red',self.point(tower.x+31,tower.y+19),center,max(1,round(2*self.scale)))
            self.screen.layer=985002
            self.draw_sprite('Crosshairs01',tower.target_x,tower.target_y,scale=.5,tint=(255,0,0))

    def draw_minimap(self):
        width=round(300*self.ui_scale);height=round(width*self.room['height']/self.room['width'])
        padding=round(8*self.ui_scale)
        rect=ui.Rect(padding,padding,width,height);self.minimap_rect=rect
        panel=ui.Surface(rect.size,ui.SRCALPHA);panel.fill((15,18,24,95))
        sx=width/self.room['width'];sy=height/self.room['height']
        def point(x,y):return round(x*sx),round(y*sy)
        for enemy in self.combat.enemies:ui.draw.circle(panel,(220,90,65),point(enemy.x,enemy.y),max(2,round(2*self.ui_scale)))
        for structure in [*self.combat.structures,*self.combat.mites]:
            if structure.health>0:ui.draw.circle(panel,(70,180,210) if structure.kind!='money_mite' else (200,150,0),point(structure.x,structure.y),max(2,round(3*self.ui_scale)))
        ui.draw.circle(panel,(230,230,230),point(self.player.x,self.player.y),max(2,round(3*self.ui_scale)))
        viewport=ui.Rect(round(self.camera.x*sx),round(self.camera.y*sy),round(self.screen.get_width()/self.scale*sx),round(self.screen.get_height()/self.scale*sy))
        ui.draw.rect(panel,(140,150,160),viewport,1)
        self.screen.blit(panel,rect)

    def draw_projectiles(self):
        for bullet in self.combat.bullets:
            if bullet.kind==1:self.draw_sprite('Round01',bullet.x,bullet.y,.25,angle=math.degrees(math.atan2(-bullet.vy,bullet.vx)))
            else:self.draw_sprite('Ball01',bullet.x,bullet.y,1 if bullet.kind==2 else .25 if bullet.kind==3 else .1)
        for rocket in self.combat.rockets:self.draw_sprite('Shell01' if rocket.kind in (1,2) else 'Missile01',rocket.x,rocket.y,scale=.35 if rocket.kind==2 else .25 if rocket.kind==1 else 1,angle=rocket.angle,tint=self.enemy_color if rocket.hostile else self.team_color)

    def draw_money_mite(self,mite):
        layer=self.screen.layer;self.screen.layer=150000
        self.draw_sprite('Crosshairs01',mite.mine_x,mite.mine_y,angle=mite.mine_rotation,tint=(200,150,0),alpha=mite.mine_alpha)
        self.screen.layer=250000
        from types import SimpleNamespace
        for side,sign in ((-16,1),(16,-1)):
            x,y=offset(mite,-30,side);angle=mite.angle+sign*mite.arm_angle
            self.draw_sprite('MiteTank0201',x,y,angle=angle,tint=self.team_color)
            pose=SimpleNamespace(x=x,y=y,angle=angle)
            x,y=offset(pose,35)
            self.draw_sprite('MiteTank0202',x,y,angle=angle-sign*mite.forearm_angle,tint=self.team_color)
        self.screen.layer=320000
        self.draw_sprite('MiteTank02',mite.x,mite.y,angle=mite.angle,tint=self.team_color)
        x,y=self.point(mite.x,mite.y);text=self.font.render(str(math.ceil(mite.health)),True,'black')
        self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.screen.layer=layer

    def draw_coin(self,coin):
        name='Cash03font' if coin.value>=250 else 'Cash02font' if coin.value>=50 else 'Cash01font'
        if not hasattr(self,'coin_fonts'):self.coin_fonts={}
        key=name,self.scale
        if key not in self.coin_fonts:
            cfg=self.assets.manifest['fonts'][name]
            import pyglet
            available=pyglet.font.have_font(cfg['family'])
            self.coin_fonts[key]=ui.font.SysFont(cfg['family'] if available else 'Arial',max(1,round(cfg['size']*96/72*self.scale)),not available)
        font=self.coin_fonts[key];x,y=self.point(coin.x,coin.y)
        x,y=round(x),round(y)
        layer=self.screen.layer
        for dx,dy in ((1,1),(1,-1),(-1,1),(-1,-1),(0,0)):
            # Pyglet batches glyphs by texture. Put the gold fill above
            # every white outline so batching cannot reverse their order.
            self.screen.layer=layer+int(not (dx or dy))
            text=font.render(self.t('ui.currency'),True,(200,150,0) if not (dx or dy) else 'white')
            self.screen.blit(text,text.get_rect(center=(round(x+dx*self.scale),round(y+dy*self.scale))))
        self.screen.layer=layer

    def draw_juggernaut(self,vehicle):
        self.draw_sprite('Juggernaught01',vehicle.x,vehicle.y,angle=vehicle.angle,tint=self.team_color)
        self.draw_sprite('JuggernaughtBarrier',vehicle.x,vehicle.y,angle=vehicle.angle,tint=self.team_color)
        self.draw_sprite('Vehicle0101',*offset(vehicle,-31),angle=vehicle.angle,alpha=vehicle.seat_alpha)
        for side,name,sign in ((-99,'JuggerNaughtDoor02',1),(99,'JuggernaughtDoor01',-1)):
            self.draw_sprite(name,*offset(vehicle,118,side),angle=vehicle.angle+sign*vehicle.door_angle,tint=self.team_color)
        if vehicle.turret_health>0:
            self.draw_sprite('MinigunTurretTop',*offset(vehicle,-176),angle=vehicle.turret_angle,tint=self.team_color)
            x,y=self.point(*offset(vehicle,-176));text=self.font.render(str(math.ceil(vehicle.turret_health)),True,'black')
            layer=self.screen.layer;self.screen.layer=self.component_layers['MinigunTurretTop']+self.component_order+1
            self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
            self.screen.layer=layer

    def draw_buggy(self,vehicle):
        for forward,side in ((-47,-29),(4,-24),(-47,29),(4,24)):
            self.draw_sprite('Vehicle0202',*offset(vehicle,forward,side),angle=vehicle.wheel_angle if forward==4 else vehicle.angle,tint=self.team_color)
        self.draw_sprite('Vehicle0201',vehicle.x,vehicle.y,angle=vehicle.angle,tint=self.team_color)
        self.draw_sprite('Vehicle0101',vehicle.x,vehicle.y,angle=vehicle.angle,alpha=vehicle.seat_alpha)
        self.draw_sprite('MachineTurretTop',*offset(vehicle,8),angle=vehicle.turret_angle,tint=self.team_color)

    def draw_factory(self,factory):
        layer=self.screen.layer;self.screen.layer=400000
        self.draw_sprite('MiteTank',factory.x+53,factory.y+2,tint=self.team_color2,alpha=factory.assembly_alpha)
        self.screen.layer=layer
        self.draw_sprite('MiteBaseOn' if factory.base_on else 'MiteBase',factory.x,factory.y,tint=self.team_color)
        if factory.part_visible:self.draw_sprite('Barracks04',factory.x-6,factory.y-23,tint=self.team_color)
        self.draw_sprite('Barracks02' if factory.arm_up else 'Barracks03',factory.x-22,factory.y+16,angle=factory.arm_angle,tint=self.team_color)

    def draw_pistol_factory(self,factory):
        self.draw_sprite('Barracks01',factory.x,factory.y,tint=self.team_color)
        for index,(dx,dy) in enumerate(factory.parts):
            if factory.parts_visible&(1<<index):self.draw_sprite('Barracks04',factory.x+dx,factory.y+dy,tint=self.team_color)
        for dx,dy,angle in ((-40,-40,135),(-40,40,225),(40,-40,45),(40,40,315)):
            layer=self.screen.layer;self.screen.layer=400000
            self.draw_sprite('TankAxe' if factory.kind=='axe_factory' else 'TankPistol',factory.x+dx,factory.y+dy,angle=angle,tint=self.team_color2,alpha=factory.assembly_alpha)
            health=(4-factory.piles)*(5 if factory.kind=='axe_factory' else 2)
            text=self.font.render(str(health),True,'black');text.set_alpha(round(255*factory.assembly_alpha))
            x,y=self.point(factory.x+dx,factory.y+dy)
            self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
            self.screen.layer=layer
        phase=factory.factory_age%4
        shift=-30*phase if phase<2 else -60+30*(phase-2)
        for dx,dy,angle in ((0,-62,270),(62,0,180),(0,62,90),(-62,0,0)):
            self.draw_sprite('Barracks03' if phase<2 else 'Barracks02',factory.x+dx,factory.y+dy,angle=angle+shift,tint=self.team_color)

    def draw_boss_factory(self,factory):
        layer=self.screen.layer
        assembling=not any(u.kind=='boss_robot' and u.owner_uid==factory.uid and u.health>0 for u in self.combat.units)
        if assembling:
            self.screen.layer=400000
            self.draw_sprite('TankBigMamaAxe',factory.x,factory.y,tint=self.team_color2,alpha=factory.assembly_alpha)
            self.screen.layer=layer
        self.draw_sprite('BossFactory01',factory.x,factory.y,tint=self.team_color)
        self.screen.layer=900000
        name='BossFactory02' if factory.arm_up else 'BossFactory03'
        self.draw_sprite(name,factory.x-81,factory.y-63,angle=factory.arm_angle,tint=self.team_color)
        self.draw_sprite(name,factory.x-81,factory.y+63,angle=factory.second_arm_angle,tint=self.team_color)
        if factory.part_visible:
            for side in (-100,100):self.draw_sprite('BossFactory04',factory.x-22,factory.y+side,tint=self.team_color)
        if assembling:
            self.screen.layer=400001
            text=self.font.render(str(math.ceil(factory.ghost_health)),True,'black');text.set_alpha(round(255*factory.assembly_alpha))
            x,y=self.point(factory.x,factory.y);self.screen.blit(text,text.get_rect(center=(round(x),round(y))))
        self.screen.layer=layer

    def draw_rails(self):
        if not self.combat.beams:return
        self.rail_overlay.fill((0,0,0,0))
        for beam in self.combat.beams:
            a=math.radians(beam.angle);x,y=self.point(beam.x,beam.y)
            dx=beam.length*math.cos(a)*self.scale;dy=-beam.length*math.sin(a)*self.scale
            if beam.age<=.02:
                self.assets.draw_sprite(self.screen,'RailgunMask',0,x,y,self.scale*beam.length/3000,self.scale,beam.angle,color=(0,0,255))
            alpha=round(255*.25*max(0,1-beam.age));green=min(250,beam.age*250)
            for index in range(16):
                t=index/16;end=(index+1)/16
                color=(0,round(green*t),round(max(0,150-green*t)),alpha)
                ui.draw.line(self.rail_overlay,color,(x+dx*t,y+dy*t),(x+dx*end,y+dy*end),max(1,round(beam.age*37.5*self.scale)))
        self.screen.blit(self.rail_overlay,(0,0))

    def draw_lasers(self):
        active=[t for t in self.combat.structures if t.kind=='laser' and t.laser_active and t.health>0]
        if not active:return
        self.rail_overlay.fill((0,0,0,0))
        for turret in active:
            end=self.point(*offset(turret,72,7))
            for forward,side in ((50,-17),(47,7),(50,29)):
                ui.draw.line(self.rail_overlay,(0,0,255,128),self.point(*offset(turret,forward,side)),end,max(1,round(2*self.scale)))
            ui.draw.line(self.rail_overlay,(0,0,255,128),end,self.point(turret.target_x,turret.target_y),max(1,round(2*self.scale)))
        self.screen.blit(self.rail_overlay,(0,0))

    def snap_build(self,x,y):return math.floor(x/75+.5)*75,math.floor(y/75+.5)*75

    def can_build(self,x,y):
        if self.tutorial and (self.tutorial.stage!=15 or self.build_kind!='turret' or not (970<=x<=1160 and 1000<=y<=1140)):return False
        if self.build_kind=='command' and any(t.kind=='command' for t in self.combat.structures):return False
        cost=STRUCTURES[self.build_kind]['price']
        return (50<=x<=self.room['width']-50 and 50<=y<=self.room['height']-50 and (self.free_buy or self.combat.money>=cost) and not self.blocked(x,y,32)
                and (x-self.player.x)**2+(y-self.player.y)**2>(25+self.player.radius)**2
                and all((x-t.x)**2+(y-t.y)**2>=60**2 for t in self.combat.structures)
                and all((x-e.x)**2+(y-e.y)**2>(25+self.rules[e.kind]['radius'])**2 for e in self.combat.enemies if e.health>0))

    def handle_event(self,event):
        if self.death_age>=0:
            if event.type==ui.MOUSEBUTTONDOWN and event.button==1:self.respawn()
            return
        if self.transition:return
        if event.type==ui.MOUSEBUTTONDOWN and event.button==3:self.selling=False;self.building=False;self.block_fire=True;return
        if event.type==ui.KEYDOWN and event.key==ui.K_z:self.menu_action(('sell',));return
        if event.type==ui.KEYDOWN and event.key==ui.K_n:self.menu_action(('build','generator'));return
        if event.type==ui.KEYDOWN and event.key==ui.K_h:
            self.menu_action(('weapon','repair') if self.combat.owns('repair') else ('denied',));return
        if event.type==ui.KEYDOWN and event.key in (ui.K_q,ui.K_e) and self.menu.open:self.cycle_weapon(-1 if event.key==ui.K_q else 1);return
        if event.type==ui.KEYDOWN and event.key==ui.K_PAUSE:
            self.paused=not self.paused;self.credits_time=0;self.audio.loop('Flamesound',False);return
        if event.type==ui.KEYDOWN and event.key==ui.K_TAB:
            self.menu.open=not self.menu.open;self.block_fire=True
            self.audio.play('PageFlip')
            self.audio.loop('Flamesound',False);return
        if self.menu.open:
            action=None
            if event.type==ui.KEYDOWN and event.key==ui.K_ESCAPE:self.close_menu();self.paused=False;self.credits_time=0;self.building=False;self.selling=False;self.block_fire=True
            elif event.type==ui.MOUSEBUTTONDOWN and event.button==1:
                action=self.menu.click(event.pos)
                if action:self.menu_action(action)
            if event.type==ui.MOUSEBUTTONDOWN and self.menu.frame(self)[1].collidepoint(event.pos):return
            if event.type==ui.KEYDOWN and event.key==ui.K_ESCAPE:return
            if event.type==ui.MOUSEBUTTONDOWN and action:return
        if event.type==ui.KEYDOWN:
            if event.key==ui.K_ESCAPE:
                if self.building or self.selling:self.building=False;self.selling=False
                self.paused=False;self.credits_time=0
            elif event.key==ui.K_F6 and self.room_name=='room1' and not self.profile_error:
                old=self.preferences.difficulty
                self.preferences.difficulty=(old+1)%3
                try:self.preferences.save()
                except OSError:self.preferences.difficulty=old;self.notice=self.t('notice.settings_error')
            elif event.key==ui.K_F8:self.menu_action(('volume','volume',-self.preferences.volume if self.preferences.volume else .5))
            elif event.key==ui.K_F9:
                if self.room_name not in [arena['room'] for arena in ARENAS.values()]:self.audio.play('AccessDenied');return
                try:
                    load_game(self);self.notice=self.t('notice.loaded')
                except (OSError,ValueError,KeyError,TypeError):self.notice=self.t('notice.load_error');self.audio.play('AccessDenied')
            elif event.key==ui.K_e and self.waves.return_ready and self.player.health>0 and not self.paused and math.hypot(self.player.x-self.room['width']/2,self.player.y-self.room['height']/2)<=100:
                self.request_room('h')
            elif not self.paused and self.player.health>0:
                if event.key==ui.K_e and self.room_name=='room1':
                    for target,x,y,_,unlocked in self.portals():
                        if unlocked and math.hypot(self.player.x-x,self.player.y-y)<=100:
                            self.request_room(target);break
                elif event.key==ui.K_SPACE:
                    if self.player.armor:armor.activate(self.player,self.combat,self.room)
                    self.flush_audio()
                elif event.key==ui.K_f:
                    self.menu_action(('wave',))
                elif event.key==ui.K_r:self.menu_action(('ammo',))
                elif event.key in (ui.K_q,ui.K_e):self.cycle_weapon(-1 if event.key==ui.K_q else 1)
        elif event.type==ui.MOUSEBUTTONDOWN and event.button==1:
            action=self.menu.click(event.pos)
            if action:self.menu_action(action);return
            for rect,action in getattr(self,'hud_buttons',[]):
                if rect.collidepoint(event.pos):self.menu_action(action);return
            if self.pointer_over_ui(event.pos):return
            mouse=self.world_point(event.pos)
            if self.selling:
                self.block_fire=True
                if self.player.health>0 and self.combat.sell_turret(*mouse,self.collisions.turret_at):self.selling=False;self.flush_audio();self.notice=self.t('notice.sold')
                else:self.notice=self.t('notice.sell')
                return
            if self.paused:return
            if self.building:
                self.block_fire=True
                x,y=self.snap_build(*mouse)
                if self.player.health>0 and self.can_build(x,y) and self.combat.build_structure(x,y,self.blocked,self.build_kind):
                    self.building=False;self.flush_audio()
                    if self.tutorial:self.tutorial.stage=16
                else:self.notice=self.t('notice.build_error');self.audio.play('AccessDenied')
                return
            if self.player.health>0:
                for target,x,y,_,unlocked in self.portals():
                    if self.portal_at(x,y,mouse):
                        self.block_fire=True
                        if unlocked:self.request_room(target)
                        elif target!='h':self.notice=self.t('notice.unlock',arena=self.t(f"arena.{ARENAS[str(target)]['requires']}.title"))
                        return
            if self.combat.swing_remaining<=0 and not self.player.vehicle_uid:self.player.angle=math.degrees(math.atan2(self.player.y-mouse[1],mouse[0]-self.player.x))%360
            for mite in self.combat.mites:
                if self.collisions.turret_at(mite,*mouse):mite.state=1
            self.combat.fire(self.player,mouse)
            self.flush_audio()

    def menu_action(self,action):
        if self.death_age>=0:return
        kind=action[0];c=self.combat
        self.block_fire=True
        if self.tutorial and not self.tutorial.action_allowed(action):
            self.audio.play('AccessDenied');self.notice=self.t('notice.tutorial_task');return
        match kind:
            case 'denied':self.audio.play('AccessDenied')
            case 'quit':self.exit_game()
            case 'back':self.audio.play('PageFlip');self.menu.tab='settings'
            case 'reset_checkpoint':
                if self.room_name not in [arena['room'] for arena in ARENAS.values()]:self.audio.play('AccessDenied');return
                from .session import SAVE_PATH
                try:
                    SAVE_PATH.unlink(missing_ok=True)
                    self.enter_arena(self.waves.arena,practice=bool(self.waves.practice))
                    self.close_menu()
                except OSError:self.notice=self.t('notice.load_error')
            case 'page':
                self.menu.pages[self.menu.tab]=action[1];self.audio.play('PageFlip')
            case 'purchase' if self.player.health>0:
                name=action[1]
                if not c.owns(name) and c.buy_weapon(name):
                    self.notice=self.t('notice.purchase',name=self.t(f'weapon.{name}.name'))
                    if self.tutorial and self.tutorial.stage==1:self.tutorial.stage=2
                else:self.notice=self.t('notice.no_money');self.audio.play('AccessDenied')
            case 'purchase_armor' if self.player.health>0:
                number=action[1];cost=armor.ARMOR[str(number)]['price']
                if not self.player.armor_owned&(1<<number) and (self.free_buy or c.money>=cost):
                    c.money-=0 if self.free_buy else cost;self.player.armor_owned|=1<<number;c.events.append('Pickup')
                    self.notice=self.t('notice.purchase',name=self.t(f'armor.{number}.name'))
                else:self.notice=self.t('notice.no_money');self.audio.play('AccessDenied')
            case 'unequip':c.unequip(action[1] if len(action)>1 else c.weapon)
            case 'sound':
                self.audio.muted=not self.audio.muted;self.preferences.sound=not self.audio.muted
                self.audio.refresh_volumes();self.preferences.save()
            case 'setting':
                field=action[1];setattr(self.preferences,field,not getattr(self.preferences,field))
                if field=='vsync':self.set_vsync(self.preferences.vsync)
                self.preferences.save()
            case 'volume':
                field=action[1];value=round(max(0,min(1,getattr(self.preferences,field)+action[2])),2)
                setattr(self.preferences,field,value);setattr(self.audio,field,value)
                self.preferences.sound=self.preferences.volume>0;self.preferences.music=self.preferences.music_volume>0
                self.audio.muted=not self.preferences.sound;self.audio.music_enabled=self.preferences.music
                self.audio.refresh_volumes();self.audio.loop('Music01',True);self.preferences.save()
            case 'ui_scale':
                sizes=(.75,1.,1.25);self.preferences.ui_scale=action[1] if len(action)>1 else sizes[(sizes.index(self.preferences.ui_scale)+1)%3]
                self.resize(self.screen);self.preferences.save()
            case 'theme':
                names=list(self.themes);self.preferences.theme=action[1] if len(action)>1 and action[1] in names else names[(names.index(self.preferences.theme)+1)%len(names)]
                self.apply_theme();self.preferences.save()
            case 'language':
                self.menu.languages=self.locale.available();self.menu.tab='languages';self.menu.open=True;self.audio.play('PageFlip')
            case 'select_language':
                if action[1] not in [name for name,_ in self.menu.languages]:return
                self.locale.select(action[1]);self.preferences.language=self.locale.language
                self.message='';self.notice=self.t('notice.language',name=self.t('meta.language'));self.preferences.save()
                self.menu.tab='settings';self.audio.play('PageFlip')
            case 'credits':
                self.paused=True;self.credits_time=10;self.close_menu()
            case 'difficulty' if self.room_name=='room1' and not self.profile_error:
                old=self.preferences.difficulty;self.preferences.difficulty=(old+1)%3
                try:self.preferences.save()
                except OSError:self.preferences.difficulty=old;self.notice=self.t('notice.settings_error')
            case 'armor' if self.player.health>0:
                self.notice=self.t('notice.armor_selected') if armor.buy(self.player,c,action[1]) else self.t('notice.armor_error')
            case 'music':
                self.preferences.music=not self.preferences.music;self.audio.music_enabled=self.preferences.music;self.audio.loop('Music01',True);self.preferences.save()
            case 'fullscreen':self.toggle_fullscreen()
            case 'close':self.close_menu()
            case 'tab':
                tab={'build':'structures','game':'settings'}.get(action[1],action[1])
                if tab=='debug' and not self.debug_enabled:return
                self.audio.play('PageFlip')
                self.menu.open=not (self.menu.open and self.menu.tab==tab);self.menu.tab=tab
            case 'key':
                if action[1]==ui.K_F9 and self.room_name not in [arena['room'] for arena in ARENAS.values()]:self.audio.play('AccessDenied');return
                self.close_menu()
                self.handle_event(ui.event.Event(ui.KEYDOWN,key=action[1]))
            case 'leave_area':
                if self.room_name=='room1':self.audio.play('AccessDenied');return
                self.close_menu();self.request_room('h')
            case 'weapon' if self.player.health>0:
                name=action[1]
                success=c.equip(name) if c.owns(name) else c.buy_weapon(name)
                self.notice=self.t('notice.weapon_selected') if success else self.t('notice.no_money')
                if not success:self.audio.play('AccessDenied')
                self.building=False;self.selling=False
                if success and self.tutorial:
                    if self.tutorial.stage==1:
                        self.tutorial.stage=2;c.equipped=False;c.weapon='repair'
                    elif self.tutorial.stage==3:self.tutorial.stage=4
            case 'ammo' if self.player.health>0:
                success=c.buy_ammo(action[1] if len(action)>1 else None)
                self.notice=self.t('notice.ammo') if success else self.t('notice.no_money')
                if not success:self.audio.play('AccessDenied')
            case 'build' if self.player.health>0:
                if action[1] not in STRUCTURES or not self.free_buy and c.money<STRUCTURES[action[1]]['price'] or action[1]=='command' and any(t.kind=='command' and t.health>0 for t in c.structures):
                    self.audio.play('AccessDenied');self.notice=self.t('notice.no_money');return
                if self.tutorial:self.tutorial.stage=15
                self.build_kind=action[1];self.building=True;self.selling=False
                self.notice=self.t('notice.build')
            case 'sell' if self.player.health>0:
                self.selling=True;self.building=False;self.close_menu()
                self.notice=self.t('notice.sell')
            case 'god_mode' if self.debug_enabled:
                self.god_mode=not self.god_mode
            case 'free_buy' if self.debug_enabled:
                self.free_buy=not self.free_buy;c.free_buy=self.free_buy
            case 'wave' if not self.paused and self.room_name in [arena['room'] for arena in ARENAS.values()] and self.player.health>0:
                self.waves.skip(c)
            case 'difficulty'|'weapon'|'ammo'|'build'|'purchase'|'purchase_armor'|'armor'|'wave':self.audio.play('AccessDenied')
        self.flush_audio()
