"""Localized shop, inventory and modern settings in the original paper style."""
import math
import json
from pathlib import Path
from functools import lru_cache
from . import backend as ui
from .config import ARENAS,STRUCTURES,ENEMY_TYPES
from .weapons import WEAPON_NAMES
from .armor import ARMOR

WEAPONS=tuple((name,f'weapon.{name}.name') for name in WEAPON_NAMES)
BUILDINGS={name:f'structure.{name}.name' for name in STRUCTURES}
WEAPON_PAGES=(('axe','pistol','shotgun','machinegun','pipebomb'),('railgun','flamethrower','repair','rpg','minigun'))
STRUCTURE_PAGES=(('factory','generator','turret','axe_factory','cannon'),('command','pistol_factory','laser','minigun_turret','boss_factory'),('buggy','light_tank','juggernaut'))
ICONS={'repair':'TankRepair','axe':'TankAxe','pistol':'TankPistol','shotgun':'TankShotgun','machinegun':'TankMachinegun','pipebomb':'TankPipe01','railgun':'TankRailgun','flamethrower':'TankFlamethrower','rpg':'TankRPG01','minigun':'TankMinigun'}
PAGE_COLOR=(247,247,244)

CONTROLS=tuple((f'controls.{name}.key',f'controls.{name}.action') for name in ('move','fire','weapons','repair','node','sell','wave','ability','pause','escape','menu','zoom','fullscreen','ammo','checkpoint'))

class Menu:
    def __init__(self):
        self.open=False;self.tab='weapons';self.buttons=[];self.pages={};self.debug_page=0;self.languages=[]

    def frame(self,game):
        scale=min(game.ui_scale,(game.screen.height-16)/680);page=self.pages.get(self.tab,0)%3
        for _ in range(4):
            width=350*scale;height=680*scale;descriptions=None
            if self.tab=='weapons':
                descriptions=[game.t(f'weapon.{name}.description') for name in WEAPON_PAGES[page]] if page<2 else [game.t(f'armor.{n}.description') for n in (1,2,3)]
            elif self.tab=='structures':descriptions=[game.t(f'structure.{name}.description') for name in STRUCTURE_PAGES[page]]
            elif self.tab=='inventory':
                count=sum(game.combat.owns(name) for name in WEAPON_NAMES)+sum(bool(game.player.armor_owned&(1<<n)) for n in (1,2,3))
                height=(65+math.ceil(count/3)*102)*scale if count else 200*scale
            elif self.tab=='controls':height=(65+len(CONTROLS)*30)*scale
            elif self.tab=='languages':height=(65+len(self.languages)*33)*scale
            elif self.tab=='debug':height=135*scale
            if descriptions is not None:height=115*scale+sum((70+len(self.wrapped_lines(text,width-32*scale,12*scale))*14.4)*scale for text in descriptions)
            limit=game.screen.height-56*scale
            if height<=limit:break
            scale*=game.screen.height/(height+56*scale)
        return scale,ui.Rect(round(game.screen.width-width-8*scale),round(48*scale),round(width),round(min(game.screen.height-56*scale,height)))

    def draw_tabs(self,game,reset=True):
        if reset:self.buttons=[]
        s,p=self.frame(game)
        parent='settings' if self.tab in ('debug','controls','languages') else self.tab
        for i,tab in enumerate(('weapons','structures','inventory','settings')):
            active=self.open and parent==tab
            y=8*s if active or not self.open else 12*s
            bottom=p.y+1 if self.open else 40*s
            rect=ui.Rect(round(p.x+i*(p.w-36*s)/4),round(y),round((p.w-36*s)/4-2*s),round(bottom-y))
            self.tab_button(game,game.t('menu.'+tab),rect,('tab',tab),active,s)
        self.button(game,game.t('ui.currency'),p.right-32*s,8*s,32*s,32*s,('sell',),selected=game.selling,font_size=23*s)

    def tab_button(self,game,text,rect,action,active,scale):
        screen=game.screen;layer=screen.layer;over=rect.collidepoint(ui.mouse.get_pos())
        screen.layer=layer+1
        ui.draw.rect(screen,PAGE_COLOR if active else (235,239,230) if over else (222,222,220),rect)
        screen.layer=layer+2
        color=(65,65,65)
        # The active tab has no bottom edge, opening into the sheet below.
        ui.draw.line(screen,color,(rect.left,rect.bottom-1),(rect.left,rect.top),1)
        ui.draw.line(screen,color,(rect.left,rect.top),(rect.right-1,rect.top),1)
        ui.draw.line(screen,color,(rect.right-1,rect.top),(rect.right-1,rect.bottom-1),1)
        if not active:ui.draw.line(screen,color,(rect.left,rect.bottom-1),(rect.right-1,rect.bottom-1),1)
        screen.layer=layer+3
        font,lines=self.button_text(text,max(1,rect.w-8*scale),max(1,rect.h-4*scale),12*scale)
        for i,line in enumerate(lines):
            label=font.render(line,True,(20,20,20))
            screen.blit(label,label.get_rect(center=(rect.centerx,rect.centery+(i-(len(lines)-1)/2)*font.size*1.25)))
        screen.layer=layer;self.buttons.append((rect,action,True))

    @lru_cache(maxsize=512)
    def button_text(self,text,width,height,size):
        # Cache wrapping and fitting; hovering does not rebuild the UI layout.
        for pixels in range(max(8,round(size)),5,-1):
            lines=self.wrapped_lines(text,width,pixels)
            font=ui.font.SysFont('Arial',pixels)
            if len(lines)*pixels*1.25<=height and all(font.render(line,True,'black').width<=width for line in lines):return font,lines
        return ui.font.SysFont('Arial',6),self.wrapped_lines(text,width,6)

    def button(self,game,text,x,y,w,h,action,enabled=True,selected=False,font_size=None):
        rect=ui.Rect(round(x),round(y),round(w),round(h));screen=game.screen;layer=screen.layer
        over=rect.collidepoint(ui.mouse.get_pos());hover=over and enabled
        if over:text=self.hint(game,action) or text
        screen.layer=layer+1
        ui.draw.rect(screen,(183,198,181) if selected else (235,239,230) if hover else (222,222,220) if enabled else (196,196,194),rect)
        screen.layer=layer+2;ui.draw.rect(screen,(65,65,65),rect,1)
        screen.layer=layer+3
        font,lines=self.button_text(text,max(1,rect.w-8*game.ui_scale),max(1,rect.h-4*game.ui_scale),font_size or 13*game.ui_scale)
        for i,line in enumerate(lines):
            label=font.render(line,True,(20,20,20) if enabled else (105,105,105))
            screen.blit(label,label.get_rect(center=(rect.centerx,rect.centery+(i-(len(lines)-1)/2)*font.size*1.25)))
        screen.layer=layer;self.buttons.append((rect,action,enabled))

    def label(self,game,text,x,y,size=14,bold=False,color=(20,20,20)):
        layer=game.screen.layer;game.screen.layer=layer+2
        font=ui.font.SysFont('Arial',max(8,round(size)),bold)
        game.screen.blit(font.render(text,True,color),(round(x),round(y)));game.screen.layer=layer

    @lru_cache(maxsize=256)
    def wrapped_lines(self,text,width,size):
        font=ui.font.SysFont('Arial',max(8,round(size)));lines=[]
        for paragraph in text.splitlines():
            line=''
            for word in paragraph.split():
                candidate=f'{line} {word}'.strip()
                if line and font.render(candidate,True,'black').get_width()>width:lines.append(line);line=word
                else:line=candidate
            lines.append(line)
        return tuple(lines)

    def paragraph(self,game,text,x,y,width,size,max_lines=4):
        for index,line in enumerate(self.wrapped_lines(text,width,size)[:max_lines]):self.label(game,line,x,y+index*size*1.2,size)

    def icon(self,game,name,x,y,size):
        d=game.assets.sprites[name];frame=d['frames'][0];scale=size/max(frame['width'],frame['height'])
        layer=game.screen.layer;game.screen.layer=layer+2
        game.assets.draw_sprite(game.screen,name,0,x+(d['origin_x']-frame['width']/2)*scale,y+(d['origin_y']-frame['height']/2)*scale,scale,scale,color=(179,179,179))
        game.screen.layer=layer

    def draw(self,game):
        s,p=self.frame(game);self.buttons=[];screen=game.screen;c=game.combat;t=game.t
        layer=screen.layer;screen.layer=layer-2
        ui.draw.rect(screen,PAGE_COLOR,p)
        screen.layer=layer
        ui.draw.rect(screen,(65,65,65),p,1)
        self.draw_tabs(game,False)
        title=t('menu.'+self.tab)
        self.button(game,t('menu.close'),p.right-42*s,p.y+10*s,27*s,27*s,('close',),font_size=14*s)
        if self.tab in ('debug','controls','languages'):
            self.button(game,t('menu.back'),p.right-74*s,p.y+10*s,27*s,27*s,('back',),font_size=14*s)
        cards=[];pages=1;page=self.pages.get(self.tab,0)
        match self.tab:
            case 'weapons':
                pages=3;page%=pages
                if page<2:
                    for name in WEAPON_PAGES[page]:
                        owned=c.owns(name);cfg=c.data[name];included=c.weapons[name].enabled
                        action=('unequip',name) if included else ('weapon',name) if owned else ('purchase',name)
                        text=t('ui.toggle_remove' if included else 'ui.toggle_equip') if owned else t('ui.buy_weapon')
                        buttons=[(text,action,owned or game.free_buy or c.money>=cfg['price'],included)]
                        if 'ammo_price' in cfg:
                            buttons.append((t('ui.buy_rounds',amount=cfg['ammo_pack']),('ammo',name),owned and (game.free_buy or c.money>=cfg['ammo_price']),False))
                        cards.append((t(f'weapon.{name}.name'),t(f'weapon.{name}.description'),ICONS[name],buttons,False))
                else:
                    title=t('menu.armor')
                    for number in (1,2,3):
                        owned=game.player.armor_owned&(1<<number);included=game.player.armor==number
                        text=t('ui.toggle_remove' if included else 'ui.toggle_equip') if owned else t('ui.buy_armor')
                        action=('armor',number) if owned else ('purchase_armor',number)
                        buttons=[(text,action,bool(owned) or game.free_buy or c.money>=ARMOR[str(number)]['price'],included)]
                        cards.append((t(f'armor.{number}.name'),t(f'armor.{number}.description'),f'Suit0{number}',buttons,False))
            case 'structures':
                pages=3;page%=pages
                if page==2:title=t('menu.vehicles')
                for name in STRUCTURE_PAGES[page]:
                    cfg=STRUCTURES[name];unique=name=='command' and any(v.kind=='command' for v in c.structures)
                    text=t('ui.buy_vehicle' if page==2 else 'ui.buy_structure')
                    cards.append((t(f'structure.{name}.name'),t(f'structure.{name}.description'),cfg['preview'],[(text,('build',name),(game.free_buy or c.money>=cfg['price']) and not unique,False)],False))
            case 'inventory':
                items=[('weapon',name) for name in WEAPON_NAMES if c.owns(name)]+[('armor',n) for n in (1,2,3) if game.player.armor_owned&(1<<n)]
                width=(p.w-32*s)/3
                for i,(category,name) in enumerate(items):
                    included=c.weapons[name].enabled if category=='weapon' else game.player.armor==name
                    action=('unequip',name) if included and category=='weapon' else ('weapon',name) if category=='weapon' else ('armor',name)
                    x=p.x+16*s+(i%3)*width;y=p.y+(55+(i//3)*102)*s
                    self.icon(game,ICONS[name] if category=='weapon' else f'Suit0{name}',x+width/2,y+32*s,60*s)
                    self.button(game,t(f'{category}.{name}.name'),x,y+66*s,width-4*s,29*s,action,selected=included,font_size=11*s)
                if not items:
                    self.paragraph(game,t('ui.empty_inventory'),p.x+18*s,p.y+55*s,p.w-36*s,14*s)
                    self.button(game,t('menu.weapons'),p.x+18*s,p.y+145*s,p.w-36*s,32*s,('tab','weapons'))
            case 'settings':
                pages=self.settings(game,p,s,page);page%=pages
            case 'debug' if game.debug_enabled:
                for i,(key,field) in enumerate((('debug.god_mode','god_mode'),('debug.free_buy','free_buy'))):
                    text=t('ui.enabled',name=t(key),state=t('ui.on' if getattr(game,field) else 'ui.off'))
                    self.button(game,text,p.x+16*s,p.y+(55+i*36)*s,p.w-32*s,30*s,(field,),selected=getattr(game,field),font_size=13*s)
            case 'controls':
                for i,(keys,description) in enumerate(CONTROLS):
                    y=p.y+(55+i*30)*s
                    self.label(game,t(keys),p.x+16*s,y,12*s,True)
                    self.label(game,t(description),p.x+135*s,y,12*s)
            case 'languages':
                for i,(name,label) in enumerate(self.languages):
                    self.button(game,label,p.x+16*s,p.y+(55+i*33)*s,p.w-32*s,27*s,('select_language',name),selected=game.preferences.language==name,font_size=12*s)
        self.pages[self.tab]=page
        self.label(game,title.upper(),p.x+16*s,p.y+16*s,17*s,True)
        if self.tab in ('weapons','structures'):self.label(game,t('ui.price',price=c.money),p.x+16*s,p.y+76*s,14*s,True)
        if pages>1:
            self.button(game,t('menu.previous'),p.x+16*s,p.y+48*s,96*s,25*s,('page',page-1),font_size=12*s)
            text=ui.font.SysFont('Arial',max(8,round(12*s))).render(t('menu.page',page=page+1,pages=pages),True,(20,20,20))
            screen.layer=layer+2;screen.blit(text,text.get_rect(center=(p.centerx,p.y+60*s)));screen.layer=layer
            self.button(game,t('menu.next'),p.right-112*s,p.y+48*s,96*s,25*s,('page',page+1),font_size=12*s)
        top=p.y+105*s
        for index,(name,description,icon,buttons,active) in enumerate(cards):
            y=top
            lines=self.wrapped_lines(description,p.w-32*s,12*s) if description else []
            row=(70+len(lines)*14.4)*s if description else 66*s
            top+=row
            ui.draw.line(screen,(145,145,140),(p.x+16*s,y-4*s),(p.right-16*s,y-4*s),1)
            self.icon(game,icon,p.x+36*s,y+15*s,32*s)
            self.label(game,name.upper(),p.x+62*s,y+4*s,13*s,True)
            self.paragraph(game,description,p.x+16*s,y+33*s,p.w-32*s,12*s,len(lines))
            for i,(text,action,enabled,selected) in enumerate(buttons):
                width=(p.w-32*s)/2
                self.button(game,text,p.x+16*s+i*width,y+row-31*s,width-3*s,25*s,action,enabled,selected,font_size=12*s)

    def settings(self,game,p,s,page):
        t=game.t;o=game.preferences
        state=lambda value:t('ui.on' if value else 'ui.off')
        toggle=lambda key,value,action:(t('ui.enabled',name=t('settings.'+key),state=state(value)),action,value)
        entries=[
            toggle('fullscreen',o.fullscreen,('fullscreen',)),toggle('vsync',o.vsync,('setting','vsync')),
            (t('settings.ui_scale'),('ui_scale',),False),
            toggle('minimap',o.minimap,('setting','minimap')),toggle('shake',o.camera_shake,('setting','camera_shake')),
            (t('ui.value',name=t('settings.volume'),value=t('ui.percent',value=o.volume)),('volume','volume'),False),
            (t('ui.value',name=t('settings.music_volume'),value=t('ui.percent',value=o.music_volume)),('volume','music_volume'),False),
            (t('settings.language'),('language',),False),
            (t('settings.theme'),('theme',),False),(t('menu.controls'),('tab','controls'),False),
            (t('ui.value',name=t('settings.difficulty'),value=t(f'difficulty.{game.preferences.difficulty}')),('difficulty',),False),
            (t('settings.reset'),('reset_checkpoint',),False),(t('settings.load'),('key',ui.K_F9),False),
            (t('settings.base'),('leave_area',),False),(t('settings.credits'),('credits',),False),(t('settings.quit'),('quit',),False),
        ]
        if game.debug_enabled:entries.append((t('settings.debug'),('tab','debug'),False))
        available=p.h-60*s;groups=[[]];used=0
        for entry in entries:
            height=(53 if entry[1][0]=='theme' else 33)*s
            if groups[-1] and used+height>available:groups.append([]);used=0
            groups[-1].append(entry);used+=height
        page%=len(groups);y=p.y+55*s
        for text,action,selected in groups[page]:
            if action[0]=='ui_scale':
                self.label(game,text,p.x+16*s,y+6*s,12*s)
                for j,(size,key) in enumerate(((.75,'settings.small'),(1.,'settings.medium'),(1.25,'settings.large'))):
                    self.button(game,t(key),p.x+(144+j*60)*s,y,57*s,27*s,('ui_scale',size),selected=o.ui_scale==size,font_size=11*s)
            elif action[0]=='theme':
                self.label(game,text,p.x+16*s,y,12*s)
                width=(p.w-32*s)/len(game.themes)
                for j,name in enumerate(game.themes):
                    self.button(game,t('theme.'+name),p.x+16*s+j*width,y+18*s,width-3*s,27*s,('theme',name),selected=o.theme==name,font_size=10*s)
            elif action[0]=='volume':
                self.label(game,text,p.x+16*s,y+6*s,12*s)
                for j,delta in enumerate((-.1,.1)):self.button(game,t('settings.minus' if delta<0 else 'settings.plus'),p.right-(82-36*j)*s,y,30*s,27*s,('volume',action[1],delta),font_size=14*s)
            else:
                arena=game.room_name in [definition['room'] for definition in ARENAS.values()]
                enabled=(action[0]!='difficulty' or game.room_name=='room1' and not game.profile_error) and (action!=('leave_area',) or game.room_name!='room1') and (action not in (('reset_checkpoint',),('key',ui.K_F9)) or arena)
                self.button(game,text,p.x+16*s,y,p.w-32*s,27*s,action,enabled=enabled,selected=selected,font_size=12*s)
            y+=(53 if action[0]=='theme' else 33)*s
        return len(groups)

    @staticmethod
    @lru_cache(maxsize=8)
    def checkpoint_values(path,stamp,size):
        try:
            data=json.loads(Path(path).read_text(encoding='utf8'))
            return int(data['waves']['number']),int(data['combat']['money'])
        except (OSError,ValueError,TypeError,KeyError):return None

    def hint(self,game,action):
        t=game.t
        match action:
            case ('ammo',name):return t('hint.ammo_price',amount=game.combat.weapons[name].ammo,price=game.combat.data[name]['ammo_price'])
            case ('purchase',name):return t('ui.price',price=game.combat.data[name]['price'])
            case ('purchase_armor',number):return t('ui.price',price=ARMOR[str(number)]['price'])
            case ('build',name):return t('ui.price',price=STRUCTURES[name]['price'])
            case ('weapon',name):return t('ui.toggle_equip')
            case ('unequip',name):return t('ui.toggle_remove')
            case ('armor',number):return t('ui.toggle_remove' if game.player.armor==number else 'ui.toggle_equip')
            case ('fullscreen',):return t('hint.fullscreen')
            case ('language',):return t('meta.language')
            case ('wave',):return t('hint.next_wave')
            case ('difficulty',):return '' if game.room_name=='room1' and not game.profile_error else t('hint.difficulty')
            case ('reset_checkpoint',):return t('hint.reset')
            case ('leave_area',):return t('hint.base')
            case ('key',key) if key==ui.K_F9:
                from .session import SAVE_PATH
                try:
                    stat=SAVE_PATH.stat();values=self.checkpoint_values(str(SAVE_PATH),stat.st_mtime_ns,stat.st_size)
                except OSError:values=None
                return t('hint.checkpoint',wave=values[0],money=values[1]) if values else t('hint.no_checkpoint')
            case ('sell',):return t('hint.sell')
            case ('setting',field) if field in ('vsync','camera_shake'):return t('hint.'+field)
        return ''

    def click(self,pos):
        found=next(((action,enabled) for rect,action,enabled in self.buttons if rect.collidepoint(pos)),None)
        return (found[0] if found[1] else ('denied',)) if found else None
