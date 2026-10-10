"""World-space collision masks from original PNGs and GM sprite metadata."""
from collections import OrderedDict
import math
from . import backend as ui
from .combat import offset
from .structures import STRUCTURES,UNIT_TYPES
from .config import ENEMY_TYPES


class Collisions:
    def __init__(self,assets):
        self.assets=assets;self.cache=OrderedDict()
        self.cache_bytes=0
        self.bounds_cache=OrderedDict();self.circle_cache={};self.rail_cache=None
        self.names={kind:definition['mask'] for kind,definition in ENEMY_TYPES.items()}

    def mask(self,name,scale=1,angle=0,scale_y=None):
        sy=scale if scale_y is None else scale_y
        key=(name,scale,angle%360,sy)
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        definition=self.assets.sprites[name]
        from PIL import Image,ImageDraw
        image=self.assets.image(name)
        w,h=image.get_size()
        clipped=ui.Surface((w,h),pixels=Image.new('RGBA',(w,h)))
        bbox=(definition['bbox_left'],definition['bbox_top'],definition['bbox_right']+1,definition['bbox_bottom']+1)
        clipped.pixels.paste(image.pixels.crop(bbox),bbox[:2])
        shape=definition['mask_shape']
        if shape:
            clipped.pixels=Image.new('RGBA',(w,h));paint=ImageDraw.Draw(clipped.pixels)
            left,top,right,bottom=bbox;box=(left,top,right-1,bottom-1)
            if shape==1:paint.rectangle(box,fill='white')
            elif shape==2:paint.ellipse(box,fill='white')
            elif shape==3:paint.polygon([((left+right)//2,top),(right-1,(top+bottom)//2),((left+right)//2,bottom-1),(left,(top+bottom)//2)],fill='white')
        w,h=image.get_size()
        clipped=ui.transform.scale(clipped,(max(1,round(w*scale)),max(1,round(h*sy))))
        clipped=ui.transform.rotate(clipped,angle)
        a=math.radians(angle);dx=(w/2-definition['origin_x'])*scale;dy=(h/2-definition['origin_y'])*sy
        origin=(dx*math.cos(a)+dy*math.sin(a)-clipped.get_width()/2,-dx*math.sin(a)+dy*math.cos(a)-clipped.get_height()/2)
        result=(ui.mask.from_surface(clipped,definition['alpha_tolerance']),origin)
        self.cache[key]=result
        def size(mask):return math.ceil(mask.get_size()[0]/32)*4*mask.get_size()[1]
        self.cache_bytes+=size(result[0])
        while len(self.cache)>512 or self.cache_bytes>32*1024*1024:
            _,removed=self.cache.popitem(last=False);self.cache_bytes-=size(removed[0])
        return result

    def overlap(self,first,x,y,second,tx,ty):
        mask,origin=first;other,other_origin=second
        return mask.overlap(other,(round(tx+other_origin[0])-round(x+origin[0]),round(ty+other_origin[1])-round(y+origin[1]))) is not None

    def melee(self,enemy,player):
        scale=.5 if enemy.kind in ('child','mega_unit') else 2 if enemy.kind in ('axe_boss','splitter_boss') else 1.5
        if not self.path_near_sprite(self.ally_name(player),player.x,player.y,player.angle,'AxeMask',scale,enemy.x,enemy.y,0,0):return False
        # Source attack objects are created with image_angle=0, independently
        # of the visible swing rotation.
        return self.overlap(self.mask('AxeMask',scale),enemy.x,enemy.y,self.mask(self.ally_name(player),angle=player.angle),player.x,player.y)

    def ally_name(self,actor):
        if getattr(actor,'kind',None) in UNIT_TYPES:return UNIT_TYPES[actor.kind]['mask']
        return STRUCTURES.get(getattr(actor,'kind',None),{}).get('top','TankMask')

    def repair(self,player,target):
        if not self.path_near_sprite(self.ally_name(target),target.x,target.y,target.angle,'AxeMask',1,player.x,player.y,0,0):return False
        return self.overlap(self.mask('AxeMask'),player.x,player.y,self.mask(self.ally_name(target),angle=target.angle),target.x,target.y)

    def turret_at(self,turret,x,y):
        mask,origin=self.mask(self.ally_name(turret),angle=turret.angle)
        px=round(x)-round(turret.x+origin[0]);py=round(y)-round(turret.y+origin[1])
        return 0<=px<mask.get_size()[0] and 0<=py<mask.get_size()[1] and bool(mask.get_at((px,py)))

    def command_occupied(self,tower,player):
        mask,origin=self.mask(self.ally_name(player),angle=player.angle)
        x=round(tower.x)-round(player.x+origin[0]);y=round(tower.y)-round(player.y+origin[1])
        return 0<=x<mask.get_size()[0] and 0<=y<mask.get_size()[1] and bool(mask.get_at((x,y)))

    def sweep(self,name,angle,tx,ty,x,y,dx,dy,projectile_kind=0):
        projectile='Round01' if projectile_kind==1 else 'Ball01'
        scale=.25 if projectile_kind in (1,3) else 1 if projectile_kind==2 else .1
        if not self.path_near_sprite(name,tx,ty,angle,projectile,scale,x,y,dx,dy):return None
        target=self.mask(name,angle=angle)
        bullet=self.mask('Round01',.25,math.degrees(math.atan2(-dy,dx))) if projectile_kind==1 else self.mask('Ball01',.1)
        if projectile_kind==2:bullet=self.mask('Ball01')
        if projectile_kind==3:bullet=self.mask('Ball01',.25)
        steps=max(1,math.ceil(math.hypot(dx,dy)))
        for index in range(steps+1):
            t=index/steps
            if self.overlap(bullet,x+dx*t,y+dy*t,target,tx,ty):return t
        return None

    def enemy_hit(self,enemy,x,y,dx,dy,component=0,projectile_kind=0):
        if component:
            name,tx,ty,angle=self.enemy_turret_pose(enemy)
            return self.sweep(name,angle,tx,ty,x,y,dx,dy,projectile_kind)
        return self.sweep(self.names[enemy.kind],enemy.angle,enemy.x,enemy.y,x,y,dx,dy,projectile_kind)

    def enemy_turret_pose(self,enemy):
        definition=ENEMY_TYPES[enemy.kind]['turret']
        x,y=offset(enemy,definition['offset'])
        return definition['sprite'],x,y,enemy.turret_angle

    def vehicle_wall_hit(self,vehicle,x,y,angle,walls):
        from types import SimpleNamespace
        pose=SimpleNamespace(kind=vehicle.kind,x=x,y=y,angle=angle,door_angle=vehicle.door_angle)
        components=[(self.ally_name(vehicle),x,y,angle),*self.vehicle_barriers(pose)]
        for name,tx,ty,rotation in components:
            mask,origin=self.mask(name,angle=rotation)
            rect=ui.Rect(round(tx+origin[0]),round(ty+origin[1]),*mask.get_size())
            for _,wall,wall_rect in walls:
                if rect.colliderect(wall_rect) and wall.overlap(mask,(rect.x-wall_rect.x,rect.y-wall_rect.y)) is not None:return True
        return False

    def move_vehicle(self,vehicle,dx,dy,target_angle,walls):
        # Sample both turning and travel at at most one pixel of hull motion.
        delta=(target_angle-vehicle.angle+180)%360-180
        radius=300 if vehicle.kind=='juggernaut' else 150
        steps=max(1,math.ceil(abs(math.radians(delta))*radius))
        start=vehicle.angle
        for i in range(1,steps+1):
            angle=(start+delta*i/steps)%360
            if self.vehicle_wall_hit(vehicle,vehicle.x,vehicle.y,angle,walls):break
            vehicle.angle=angle
        distance=math.hypot(dx,dy);steps=max(1,math.ceil(distance))
        start_x,start_y=vehicle.x,vehicle.y
        for i in range(1,steps+1):
            x,y=start_x+dx*i/steps,start_y+dy*i/steps
            if self.vehicle_wall_hit(vehicle,x,y,vehicle.angle,walls):break
            vehicle.x,vehicle.y=x,y

    def vehicle_barriers(self,vehicle):
        if vehicle.kind=='armor_shield':return [('SuitBarrier01',vehicle.x,vehicle.y,vehicle.angle)]
        if vehicle.kind in ('light_tank','enemy_tank'):return [('Vehicle0103',vehicle.x,vehicle.y,vehicle.angle)]
        if vehicle.kind not in ('juggernaut','mega_juggernaut'):return []
        barriers=[('JuggernaughtBarrier',vehicle.x,vehicle.y,vehicle.angle)]
        door_angle=0 if vehicle.kind=='mega_juggernaut' and vehicle.phase!=2 else vehicle.door_angle
        for side,name,sign in ((-99,'JuggerNaughtDoor02',1),(99,'JuggernaughtDoor01',-1)):
            x,y=offset(vehicle,118,side)
            barriers.append((name,x,y,vehicle.angle+sign*door_angle))
        return barriers

    def vehicle_barrier_hit(self,vehicle,x,y,dx,dy):
        hits=[self.sweep(name,angle,tx,ty,x,y,dx,dy) for name,tx,ty,angle in self.vehicle_barriers(vehicle)]
        return min((hit for hit in hits if hit is not None),default=None)

    def enemy_line(self,enemy,x,y,angle,length):
        # GM collision_line with prec=false checks the transformed bounding box.
        rect=self.bounds(self.names[enemy.kind],enemy.x,enemy.y,enemy.angle)
        a=math.radians(angle)
        return bool(rect.clipline((x,y),(x+length*math.cos(a),y-length*math.sin(a))))

    def ally_line(self,target,x,y,angle,length):
        rect=self.bounds(self.ally_name(target),target.x,target.y,target.angle)
        a=math.radians(angle)
        return bool(rect.clipline((x,y),(x+length*math.cos(a),y-length*math.sin(a))))

    def player_hit(self,player,x,y,dx,dy,projectile_kind=0):
        return self.sweep(self.ally_name(player),player.angle,player.x,player.y,x,y,dx,dy,projectile_kind)

    def player_axe(self,enemy,player,component=0):
        name=self.names[enemy.kind];x,y=enemy.x,enemy.y;angle=enemy.angle
        if component:name,x,y,angle=self.enemy_turret_pose(enemy)
        if not self.path_near_sprite(name,x,y,angle,'AxeMask',1.5,player.x,player.y,0,0):return False
        return self.overlap(self.mask('AxeMask',1.5),player.x,player.y,self.mask(name,angle=angle),x,y)

    def rail_hit(self,enemy,beam,component=0):
        name=self.names[enemy.kind];x,y=enemy.x,enemy.y;angle=enemy.angle
        if component:name,x,y,angle=self.enemy_turret_pose(enemy)
        return self.rail_mask_hit(name,x,y,angle,beam)

    def rail_ally_hit(self,target,beam):
        return self.rail_mask_hit(self.ally_name(target),target.x,target.y,target.angle,beam)

    def rail_mask_hit(self,name,x,y,angle,beam):
        rect=self.bounds(name,x,y,angle)
        a=math.radians(beam.angle)
        # A conservative strip around the centre line includes its five-pixel
        # thickness and raster rounding. Only candidates need pixel masks.
        expanded=ui.Rect(rect.x-5,rect.y-5,rect.width+10,rect.height+10)
        if not expanded.clipline((beam.x,beam.y),(beam.x+beam.length*math.cos(a),beam.y-beam.length*math.sin(a))):return False
        width=self.assets.image('RailgunMask').get_width()
        # Only horizontal beam scale changes in the GM sprite. RailgunMask is
        # 3000x5, so avoid scaling its thickness with its length.
        key=beam.length,beam.angle
        if self.rail_cache is None or self.rail_cache[0]!=key:
            self.rail_cache=(key,self.mask('RailgunMask',beam.length/width,beam.angle,scale_y=1))
        return self.overlap(self.rail_cache[1],beam.x,beam.y,self.mask(name,angle=angle),x,y)

    def enemy_circle(self,enemy,x,y,radius):
        if radius not in self.circle_cache:
            surface=ui.Surface((2*radius+1,2*radius+1),ui.SRCALPHA)
            ui.draw.circle(surface,'white',(radius,radius),radius)
            self.circle_cache[radius]=(ui.mask.from_surface(surface),(-radius,-radius))
        return self.overlap(self.circle_cache[radius],x,y,self.mask(self.names[enemy.kind],angle=enemy.angle),enemy.x,enemy.y)

    def rail_barrier_distance(self,x,y,angle,length,vehicles):
        a=math.radians(angle);dx,dy=length*math.cos(a),-length*math.sin(a);nearest=None
        for vehicle in vehicles:
            if vehicle.health<=0:continue
            for name,tx,ty,rotation in self.vehicle_barriers(vehicle):
                mask,origin=self.mask(name,angle=rotation)
                left,top=round(tx+origin[0]),round(ty+origin[1])
                rect=ui.Rect(left,top,*mask.get_size())
                segment=rect.clipline((x,y),(x+dx,y+dy))
                if not segment:continue
                start,end=segment;sx,sy=start;ex,ey=end
                steps=max(1,math.ceil(math.hypot(ex-sx,ey-sy)))
                for index in range(steps+1):
                    px,py=sx+(ex-sx)*index/steps,sy+(ey-sy)*index/steps
                    mx,my=round(px)-left,round(py)-top
                    if 0<=mx<mask.width and 0<=my<mask.height and mask.get_at((mx,my)):
                        distance=math.hypot(px-x,py-y)
                        nearest=distance if nearest is None else min(nearest,distance)
                        break
        return nearest

    def blast_hit(self,enemy,blast,component=0):
        name=self.names[enemy.kind];x,y=enemy.x,enemy.y;angle=enemy.angle
        if component:name,x,y,angle=self.enemy_turret_pose(enemy)
        if not self.path_near_sprite(name,x,y,angle,'AxeMask',blast.scale,blast.x,blast.y,0,0):return False
        return self.overlap(self.mask('AxeMask',blast.scale),blast.x,blast.y,self.mask(name,angle=angle),x,y)

    def ally_blast_hit(self,target,blast):
        if not self.path_near_sprite(self.ally_name(target),target.x,target.y,target.angle,'AxeMask',blast.scale,blast.x,blast.y,0,0):return False
        return self.overlap(self.mask('AxeMask',blast.scale),blast.x,blast.y,self.mask(self.ally_name(target),angle=target.angle),target.x,target.y)

    def enemy_barrier_hit(self,enemy,x,y,dx,dy,projectile_kind=0):
        hits=[self.sweep(name,angle,tx,ty,x,y,dx,dy,projectile_kind) for name,tx,ty,angle in self.vehicle_barriers(enemy)]
        return min((hit for hit in hits if hit is not None),default=None)

    def ally_flame_hit(self,target,flame,scale):
        if not self.path_near_sprite(self.ally_name(target),target.x,target.y,target.angle,'Ball02',scale,flame.x,flame.y,0,0):return False
        return self.overlap(self.mask('Ball02',scale),flame.x,flame.y,self.mask(self.ally_name(target),angle=target.angle),target.x,target.y)

    def enemy_flame_barrier(self,flame,vehicle,scale):
        return any(self.overlap(self.mask('Ball02',scale),flame.x,flame.y,self.mask(name,angle=angle),x,y) for name,x,y,angle in self.vehicle_barriers(vehicle))

    def fire_zone_hit(self,target,zone):
        if not self.path_near_sprite(self.ally_name(target),target.x,target.y,target.angle,'FireBall',zone.scale,zone.x,zone.y,0,0):return False
        return self.overlap(self.mask('FireBall',zone.scale),zone.x,zone.y,self.mask(self.ally_name(target),angle=target.angle),target.x,target.y)

    def shell_sweep(self,name,angle,tx,ty,rocket,dx,dy):
        if not self.path_near_sprite(name,tx,ty,angle,'Shell01',.35 if rocket.kind==2 else .25,rocket.x,rocket.y,dx,dy):return None
        missile=self.mask('Shell01',.35 if rocket.kind==2 else .25,rocket.angle);target=self.mask(name,angle=angle)
        steps=max(1,math.ceil(math.hypot(dx,dy)))
        for index in range(steps+1):
            t=index/steps
            if self.overlap(missile,rocket.x+dx*t,rocket.y+dy*t,target,tx,ty):return t
        return None

    def ally_rocket_hit(self,target,rocket,dx,dy):
        return self.shell_sweep(self.ally_name(target),target.angle,target.x,target.y,rocket,dx,dy)

    def ally_rocket_barrier_hit(self,vehicle,rocket,dx,dy):
        hits=[self.shell_sweep(name,angle,tx,ty,rocket,dx,dy) for name,tx,ty,angle in self.vehicle_barriers(vehicle)]
        return min((hit for hit in hits if hit is not None),default=None)

    def flame_hit(self,enemy,flame,component=0):
        name=self.names[enemy.kind];x,y=enemy.x,enemy.y;angle=enemy.angle
        if component:name,x,y,angle=self.enemy_turret_pose(enemy)
        if not self.path_near_sprite(name,x,y,angle,'Ball02',.1+5*flame.age,flame.x,flame.y,0,0):return False
        return self.overlap(self.mask('Ball02',.1+5*flame.age),flame.x,flame.y,self.mask(name,angle=angle),x,y)

    def rocket_hit(self,enemy,rocket,dx,dy,component=0):
        name=self.names[enemy.kind];x,y=enemy.x,enemy.y;angle=enemy.angle
        if component:name,x,y,angle=self.enemy_turret_pose(enemy)
        projectile='Shell01' if rocket.kind in (1,2) else 'Missile01'
        scale=.35 if rocket.kind==2 else .25 if rocket.kind==1 else 1
        if not self.path_near_sprite(name,x,y,angle,projectile,scale,rocket.x,rocket.y,dx,dy):return None
        missile=self.mask('Shell01',.35 if rocket.kind==2 else .25,rocket.angle) if rocket.kind in (1,2) else self.mask('Missile01',angle=rocket.angle)
        target=self.mask(name,angle=angle)
        steps=max(1,math.ceil(math.hypot(dx,dy)))
        for index in range(steps+1):
            t=index/steps
            if self.overlap(missile,rocket.x+dx*t,rocket.y+dy*t,target,x,y):return t
        return None

    def enemy_rocket_barrier_hit(self,enemy,rocket,dx,dy):
        projectile='Shell01' if rocket.kind in (1,2) else 'Missile01'
        scale=.35 if rocket.kind==2 else .25 if rocket.kind==1 else 1
        missile=None
        hits=[]
        for name,x,y,angle in self.vehicle_barriers(enemy):
            if not self.path_near_sprite(name,x,y,angle,projectile,scale,rocket.x,rocket.y,dx,dy):continue
            if missile is None:missile=self.mask(projectile,scale,rocket.angle)
            hit=self.swept_mask_hit(missile,self.mask(name,angle=angle),x,y,rocket.x,rocket.y,dx,dy)
            if hit is not None:hits.append(hit)
        return min(hits,default=None)

    def path_near_sprite(self,name,x,y,angle,projectile,scale,px,py,dx,dy):
        # Cover the whole projectile around its origin, plus raster rounding.
        sprite=self.assets.sprites[projectile]
        rx=max(abs(sprite['bbox_left']-sprite['origin_x']),abs(sprite['bbox_right']+1-sprite['origin_x']))
        ry=max(abs(sprite['bbox_top']-sprite['origin_y']),abs(sprite['bbox_bottom']+1-sprite['origin_y']))
        radius=math.hypot(rx,ry)*scale+3;target=self.bounds(name,x,y,angle)
        return not (max(px,px+dx)+radius<target.left or min(px,px+dx)-radius>target.right or max(py,py+dy)+radius<target.top or min(py,py+dy)-radius>target.bottom)

    def swept_mask_hit(self,missile,target,x,y,px,py,dx,dy):
        mask,origin=missile;other,offset=target
        left=min(px,px+dx)+origin[0];top=min(py,py+dy)+origin[1]
        right=max(px,px+dx)+origin[0]+mask.get_size()[0];bottom=max(py,py+dy)+origin[1]+mask.get_size()[1]
        if right<x+offset[0]-2 or left>x+offset[0]+other.get_size()[0]+2 or bottom<y+offset[1]-2 or top>y+offset[1]+other.get_size()[1]+2:return None
        steps=max(1,math.ceil(math.hypot(dx,dy)))
        for index in range(steps+1):
            t=index/steps
            if self.overlap(missile,px+dx*t,py+dy*t,target,x,y):return t
        return None

    def gap(self,enemy,player):
        first=self.bounds(self.names[enemy.kind],enemy.x,enemy.y,enemy.angle)
        second=self.bounds(self.ally_name(player),player.x,player.y,player.angle)
        dx=max(0,first.left-second.right,second.left-first.right)
        dy=max(0,first.top-second.bottom,second.top-first.bottom)
        return math.hypot(dx,dy)

    def bounds(self,name,x,y,angle):
        key=name,angle%360
        rect=self.bounds_cache.get(key)
        if rect is None:
            d=self.assets.sprites[name];a=math.radians(angle);c=math.cos(a);sn=math.sin(a);points=[]
            for px in (d['bbox_left']-d['origin_x'],d['bbox_right']+1-d['origin_x']):
                for py in (d['bbox_top']-d['origin_y'],d['bbox_bottom']+1-d['origin_y']):points.append((px*c+py*sn,-px*sn+py*c))
            left=math.floor(min(p[0] for p in points));top=math.floor(min(p[1] for p in points))
            rect=ui.Rect(left,top,math.ceil(max(p[0] for p in points))-left,math.ceil(max(p[1] for p in points))-top)
            self.bounds_cache[key]=rect
            if len(self.bounds_cache)>512:self.bounds_cache.popitem(last=False)
        else:self.bounds_cache.move_to_end(key)
        return rect.move(round(x),round(y))

    def command_circle(self,unit,x,y,radius):
        if radius not in self.circle_cache:
            surface=ui.Surface((2*radius+1,2*radius+1),ui.SRCALPHA)
            ui.draw.circle(surface,'white',(radius,radius),radius)
            self.circle_cache[radius]=(ui.mask.from_surface(surface),(-radius,-radius))
        return self.overlap(self.circle_cache[radius],x,y,self.mask(self.ally_name(unit),angle=unit.angle),unit.x,unit.y)

    def marker_gap(self,vehicle,x,y):
        first=self.bounds(self.ally_name(vehicle),vehicle.x,vehicle.y,vehicle.angle)
        second=self.bounds('Crosshairs01',x,y,0)
        return math.hypot(max(0,first.left-second.right,second.left-first.right),max(0,first.top-second.bottom,second.top-first.bottom))
