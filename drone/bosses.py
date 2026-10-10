"""Native final bosses, drivers and fire hazards for areas V and VI."""
from dataclasses import dataclass
import math
from .combat import Bullet,RailBeam,Rocket,offset,turn,segment_hit
from .explosives import gap_to


@dataclass
class EnemyFlame:
    x: float
    y: float
    angle: float
    kind: int=0
    speed: float=375
    age: float=0
    duration: float=1.3
    start_scale: float=.1
    growth: float=5
    alpha: float=.65
    damage: float=0


@dataclass
class FireZone:
    x: float
    y: float
    age: float=0
    duration: float=21.6
    damage: float=.25

    @property
    def scale(self):return min(1.5,.025+1.25*self.age)

    @property
    def alpha(self):
        phase=self.age%2.4
        return .05+.1*(phase if phase<=1.2 else 2.4-phase)


def predictive_dodge(combat,enemy,target,collisions,radius=100):
    distance=math.hypot(target.x-enemy.x,target.y-enemy.y)
    a=math.radians(target.angle)
    x,y=target.x+distance*math.cos(a),target.y-distance*math.sin(a)
    return collisions.enemy_circle(enemy,x,y,radius) if collisions else math.hypot(x-enemy.x,y-enemy.y)<=radius+combat.data[enemy.kind]['radius']


def step_boss(combat,enemy,target,targets,dt,collisions):
    if not targets:return
    match combat.data[enemy.kind]['ai']:
        case 'mega_flame':step_transforming(combat,enemy,target,targets,dt,collisions)
        case 'mega_juggernaut':step_juggernaut(combat,enemy,target,targets,dt,collisions)
        case 'mega_driver':step_driver(combat,enemy,target,dt,collisions)


def step_transforming(combat,enemy,target,targets,dt,collisions):
    cfg=combat.data[enemy.kind]
    gap=min(gap_to(combat,enemy,t,collisions) for t in targets)
    aim=math.degrees(math.atan2(enemy.y-target.y,target.x-enemy.x))%360
    enemy.dodge_timer-=dt
    if enemy.dodge_timer<=1e-9:
        enemy.dodge_timer+=1;enemy.dodge_angle=90 if combat.rng.random()<.5 else -90
    if enemy.phase==2:
        enemy.phase_timer=max(0,enemy.phase_timer-dt)
        if enemy.phase_timer<=1e-9:enemy.phase=1
    # Deliberately sequential: the original changes phase and executes the
    # following phase's block within the same Step event.
    if enemy.phase==0:
        enemy.angle=aim;enemy.move_angle=aim
        enemy.move_speed=cfg['speed'] if gap>cfg['rail_stop'] else 0
        if gap<=cfg['flame_range']:enemy.phase=1
        if gap<=cfg['rail_range']:
            if enemy.fire_timer<=1e-9:
                length=3000
                distance=collisions.rail_barrier_distance(enemy.x,enemy.y,aim,length,combat.structures) if collisions else None
                if distance is not None:length=max(.01,distance-cfg['rail_muzzle']);combat.events.append('BarrierSound')
                combat.beams.append(RailBeam(*offset(enemy,cfg['rail_muzzle']),aim,length,hostile=1,damage=cfg['rail_damage']))
                enemy.fire_timer=cfg['rail_interval'];combat.events.append('RailgunSound')
            enemy.fire_timer=max(0,enemy.fire_timer-dt)
    if enemy.phase==1:
        enemy.angle=aim;enemy.move_angle=aim
        enemy.move_speed=cfg['speed'] if gap>cfg['flame_stop'] else 0
        if gap>cfg['flame_range']:enemy.phase=0
        if gap<cfg['flame_range']:
            combat.enemy_flame_sound=True
            for kind,muzzle in enumerate(cfg['flame_muzzles']):
                combat.enemy_flames.append(EnemyFlame(*offset(enemy,muzzle),aim+combat.rng.uniform(-10,10),kind))
            if enemy.flame_timer+1e-9>=cfg['flame_interval']:
                a=math.radians(aim)
                combat.enemy_flames.append(EnemyFlame(enemy.x+50*math.cos(a),enemy.y-47.5*math.sin(a),aim,2,damage=cfg['flame_damage']))
                enemy.flame_timer=0
            enemy.flame_timer=min(cfg['flame_interval'],enemy.flame_timer+dt)
        if gap<cfg['flee_gap']:
            enemy.phase=2;enemy.phase_timer=cfg['flee_duration'];enemy.move_angle=aim+180
            combat.enemy_flame_sound=False
            combat.fire_zones.append(FireZone(enemy.x,enemy.y,duration=cfg['fire_zone_duration'],damage=cfg['fire_zone_damage']))
            # The expanding ring is decorative; damage comes from FireBall.
            for angle in range(10,361,10):
                combat.enemy_flames.append(EnemyFlame(enemy.x,enemy.y,angle,speed=312.5,duration=1.2,start_scale=.02,growth=2,alpha=.5))
            combat.events.append('BurnSound')
    if enemy.phase==2:
        combat.enemy_flames.append(EnemyFlame(*offset(enemy,100),combat.rng.uniform(0,360),speed=combat.rng.uniform(0,5),duration=.5,start_scale=.02,growth=2,alpha=.5))
        enemy.move_speed=cfg['speed'];enemy.angle=enemy.move_angle%360
    elif gap<=cfg['rail_stop'] and getattr(target,'kind',None)!='generator' and predictive_dodge(combat,enemy,target,collisions,cfg['dodge_radius']):
        enemy.move_angle=aim+enemy.dodge_angle;enemy.move_speed=cfg['dodge_speed']
    a=math.radians(enemy.move_angle)
    enemy.x+=enemy.move_speed*dt*math.cos(a);enemy.y-=enemy.move_speed*dt*math.sin(a)


def edge_driver(combat,owner):
    width,height=combat.room_size;side=combat.rng.randrange(4)
    x=0 if side==0 else width if side==1 else combat.rng.uniform(0,width)
    y=0 if side==2 else height if side==3 else combat.rng.uniform(0,height)
    driver=combat.spawn(x,y,'mega_driver');driver.owner_uid=owner.uid
    return driver


def component_gap(combat,name,x,y,angle,target,collisions,radius=25):
    if not collisions:return max(0,math.hypot(target.x-x,target.y-y)-radius-target.radius)
    first=collisions.bounds(name,x,y,angle);second=collisions.bounds(collisions.ally_name(target),target.x,target.y,target.angle)
    return math.hypot(max(0,first.left-second.right,second.left-first.right),max(0,first.top-second.bottom,second.top-first.bottom))


def step_juggernaut(combat,enemy,target,targets,dt,collisions):
    cfg=combat.data[enemy.kind]
    preferred=[t for t in targets if getattr(t,'kind',None) not in ('drone','money_mite')] or targets
    nearest=min(preferred,key=lambda t:(t.x-enemy.x)**2+(t.y-enemy.y)**2)
    gap=min(gap_to(combat,enemy,t,collisions) for t in preferred)
    aim=math.degrees(math.atan2(enemy.y-nearest.y,nearest.x-enemy.x))%360
    if enemy.phase==1:
        enemy.phase_timer=max(0,enemy.phase_timer-dt)
        if enemy.phase_timer<=1e-9:enemy.phase=2
    if enemy.phase==0:
        enemy.angle=turn(enemy.angle,aim,cfg['turn_speed']*dt)
        enemy.move_speed=cfg['speed'] if gap>cfg['stop_gap'] else 0
        if gap<=cfg['stop_gap'] and abs((enemy.angle-aim+180)%360-180)<1e-9:
            enemy.phase=1;enemy.phase_timer=cfg['spin_duration']
    if enemy.phase==1:enemy.angle=(enemy.angle+enemy.turn_direction*dt)%360
    if enemy.phase==2:
        enemy.move_speed=0
        if gap>cfg['chase_gap']:enemy.phase=0
        all_gap=min(gap_to(combat,enemy,t,collisions) for t in targets)
        if all_gap<cfg['door_gap'] and enemy.door_state==0:
            enemy.door_state=2;enemy.door_timer=cfg['door_duration'];enemy.spawn_timer=cfg['deploy_delay']
        elif all_gap>=cfg['door_gap'] and enemy.door_state==1:
            enemy.door_state=3;enemy.door_timer=cfg['door_duration'];enemy.spawn_timer=0
        if enemy.door_state in (2,3):
            enemy.door_timer=max(0,enemy.door_timer-dt)
            enemy.door_angle=max(0,min(90,enemy.door_angle+(100 if enemy.door_state==2 else -100)*dt))
            if enemy.door_timer<=1e-9:enemy.door_state=1 if enemy.door_state==2 else 0
        if enemy.door_state in (1,2):
            enemy.spawn_timer-=dt
            if enemy.spawn_timer<=1e-9:
                if sum(e.kind=='mega_unit' and e.health>0 for e in combat.enemies)<cfg['deploy_limit']:
                    for sign in (1,-1):
                        angle=enemy.angle+sign*combat.rng.uniform(15,45);a=math.radians(angle)
                        unit=combat.spawn(enemy.x+150*math.cos(a),enemy.y-150*math.sin(a),'mega_unit');unit.angle=angle
                enemy.spawn_timer+=cfg['deploy_interval']
    a=math.radians(enemy.angle)
    enemy.x+=enemy.move_speed*dt*math.cos(a);enemy.y-=enemy.move_speed*dt*math.sin(a)
    if not any(e.kind=='mega_driver' and e.owner_uid==enemy.uid and e.health>0 for e in combat.enemies):edge_driver(combat,enemy)
    if enemy.turret_health>0:
        tx,ty=offset(enemy,cfg['turret_offset'])
        nearest=min(targets,key=lambda t:(t.x-tx)**2+(t.y-ty)**2)
        turret_gap=min(component_gap(combat,'MinigunTurretTop',tx,ty,enemy.turret_angle,t,collisions) for t in targets)
        desired=math.degrees(math.atan2(ty-nearest.y,nearest.x-tx))%360
        if turret_gap<cfg['turret_range']:
            aligned=desired-5<enemy.turret_angle<desired+5
            enemy.turret_angle=turn(enemy.turret_angle,desired,cfg['turret_turn_speed']*dt)
            if aligned:
                if enemy.fire_timer+1e-9>=cfg['turret_interval']:
                    a=math.radians(enemy.turret_angle+math.ceil(combat.rng.uniform(-2.5,2.5)))
                    combat.bullets.append(Bullet(tx,ty,1000*math.cos(a),-1000*math.sin(a),.8,hostile=1,damage=cfg['turret_damage'],kind=1))
                    combat.events.append('Fire03');enemy.fire_timer=0
                enemy.fire_timer=min(cfg['turret_interval'],enemy.fire_timer+dt)
        else:enemy.turret_angle=turn(enemy.turret_angle,enemy.angle,cfg['turret_turn_speed']*dt)
    for index,(distance,side) in enumerate((distance,side) for side in (-79,79) for distance in cfg['side_offsets']):
        x,y=offset(enemy,distance,side);angle=enemy.angle+(90 if side<0 else -90);a=math.radians(angle)
        in_range=min(component_gap(combat,'TankRepair',x,y,angle,t,collisions,16) for t in targets)<=cfg['side_range']
        hit=in_range and any(collisions.ally_line(t,x,y,angle,cfg['side_range']) if collisions else segment_hit(x,y,cfg['side_range']*math.cos(a),-cfg['side_range']*math.sin(a),t.x,t.y,t.radius) is not None for t in targets)
        if hit:
            if enemy.side_charges[index]+1e-9>=cfg['side_interval']:
                combat.rockets.append(Rocket(x,y,angle,speed=375,kind=2,hostile=1));combat.events.append('TurretSound');enemy.side_charges[index]=0
            enemy.side_charges[index]=min(cfg['side_interval'],enemy.side_charges[index]+dt)
    enemy.health=min(cfg['health'],enemy.health);enemy.turret_health=min(cfg['turret_health'],enemy.turret_health)


def step_driver(combat,enemy,target,dt,collisions):
    owner=next((e for e in combat.enemies if e.kind=='mega_juggernaut' and e.uid==enemy.owner_uid and e.health>0),None)
    if owner is None:enemy.health=0;return
    cfg=combat.data[enemy.kind];x,y=offset(owner,combat.data[owner.kind]['driver_offset'])
    distance=math.hypot(x-enemy.x,y-enemy.y)
    enemy.dodge_timer-=dt
    if enemy.dodge_timer<=1e-9:
        enemy.dodge_timer+=1;enemy.dodge_angle=90 if combat.rng.random()<.5 else -90
    if not enemy.driving:
        angle=math.degrees(math.atan2(enemy.y-y,x-enemy.x))%360
        # The original keeps image_angle aimed at DestX/DestY even when
        # its movement direction is overridden by a sideways dodge.
        enemy.angle=angle
        if predictive_dodge(combat,enemy,target,collisions,cfg['dodge_radius']):angle=math.degrees(math.atan2(enemy.y-target.y,target.x-enemy.x))+enemy.dodge_angle
        a=math.radians(angle);travel=min(distance,cfg['speed']*dt)
        enemy.x+=travel*math.cos(a);enemy.y-=travel*math.sin(a)
        # EnemyMegaBoss0207 Step checks arrival after move_towards_point
        # and its dodge branch, before executing the seated repair branch.
        if math.hypot(x-enemy.x,y-enemy.y)<5:enemy.driving=1
    if enemy.driving:
        enemy.x,enemy.y=x,y;enemy.angle=(enemy.angle+900*dt)%360
        enemy.fire_timer+=dt
        if enemy.fire_timer+1e-9>=cfg['repair_interval']:
            enemy.fire_timer=0;amount=cfg['repair_amount']
            owner.health=min(combat.data[owner.kind]['health'],owner.health+amount)
            if owner.turret_health>0:owner.turret_health=min(combat.data[owner.kind]['turret_health'],owner.turret_health+amount)
            combat.events.extend(('Fire05','RepairSound'))
            width=collisions.assets.image('Juggernaught01').get_width() if collisions else 480
            combat.healing_effects.repair(owner.x,owner.y,width)
            if owner.turret_health>0:combat.healing_effects.repair(*offset(owner,combat.data[owner.kind]['turret_offset']),50)


def step_fire(combat,targets,dt,blocked,collisions):
    flames=[]
    for flame in combat.enemy_flames:
        flame.age+=dt
        if flame.age>=flame.duration-1e-9:continue
        flame.speed=max(0,flame.speed-combat.rng.random()*250*dt)
        a=math.radians(flame.angle);flame.x+=flame.speed*dt*math.cos(a);flame.y-=flame.speed*dt*math.sin(a)
        scale=flame.start_scale+flame.growth*flame.age
        if blocked(flame.x,flame.y,2):continue
        if collisions and any(collisions.enemy_flame_barrier(flame,vehicle,scale) for vehicle in [*combat.structures,*getattr(combat,'player_barriers',[])] if vehicle.health>0):continue
        consumed=False
        if flame.kind:
            for target in targets:
                if target.health<=0:continue
                hit=collisions.ally_flame_hit(target,flame,scale) if collisions else math.hypot(target.x-flame.x,target.y-flame.y)<=25*scale+target.radius
                if hit:
                    # Ordinary boss fire is decorative and consumed on contact;
                    # only EnemyMegaBossBullet0403 has a PUG damage event.
                    if flame.damage:target.health=max(0,target.health-flame.damage*50*dt)
                    if flame.kind==1:consumed=True;break
        if not consumed:flames.append(flame)
    combat.enemy_flames=flames
    zones=[]
    for zone in combat.fire_zones:
        zone.age+=dt
        if zone.age>=zone.duration-1e-9:continue
        for target in targets:
            if target.health<=0:continue
            hit=collisions.fire_zone_hit(target,zone) if collisions else math.hypot(target.x-zone.x,target.y-zone.y)<=250*zone.scale+target.radius
            if hit:target.health=max(0,target.health-zone.damage*50*dt)
        zones.append(zone)
    combat.fire_zones=zones
