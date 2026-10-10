"""Native pistol/axebot slice. No GM events, globals or alarm timers."""
from dataclasses import dataclass,field
import math
import random
from .structures import Turret,STRUCTURES,PistolRobot,AxeRobot,BossRobot,VehicleTurret,UNIT_TYPES
from .parallel import BattleWorkers
from .weapons import WeaponInventory,WeaponState,WEAPON_NAMES
from .config import ENEMY_TYPES


def segment_hit(x,y,dx,dy,cx,cy,radius):
    """First intersection of a swept projectile with a circle, in [0, 1]."""
    ox,oy=x-cx,y-cy
    c=ox*ox+oy*oy-radius*radius
    if c<=0:return 0.0
    a=dx*dx+dy*dy
    if not a:return None
    b=2*(ox*dx+oy*dy)
    disc=b*b-4*a*c
    if disc<0:return None
    t=(-b-math.sqrt(disc))/(2*a)
    return t if 0<=t<=1 else None


def turn(angle,target,maximum):
    delta=(target-angle+180)%360-180
    return (angle+max(-maximum,min(maximum,delta)))%360


def offset(enemy,distance,side=0):
    angle=math.radians(enemy.angle)
    return enemy.x+distance*math.cos(angle)+side*math.sin(angle),enemy.y-distance*math.sin(angle)+side*math.cos(angle)


@dataclass
class Enemy:
    x: float
    y: float
    health: float
    angle: float=0
    attack: float=0
    age: float=0
    kind: str='axebot'
    scatter_speed: float=0
    scatter_heading: float=0
    deployed: int=0
    spawn_timer: float=0
    turret_health: float=250
    turret_angle: float=0
    fire_timer: float=0
    door_angle: float=0
    move_speed: float=0
    move_angle: float=0
    dodge_angle: float=100
    dodge_timer: float=1
    uid: int=0
    owner_uid: int=0
    driving: int=0
    reload_timer: float=0
    phase: int=0
    phase_timer: float=0
    flame_timer: float=0
    turn_direction: float=18
    door_state: int=0
    door_timer: float=0
    side_charges: list=field(default_factory=list)
    melee_vx: float=0
    melee_vy: float=0


@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    hostile: int=0
    damage: float=5
    kind: int=0


@dataclass
class Coin:
    x: float
    y: float
    speed: float=0
    age: float=0
    value: int=10
    permanent: int=0


@dataclass
class RailBeam:
    x: float
    y: float
    angle: float
    length: float=3000
    age: float=0
    applied: int=0
    hostile: int=0
    damage: float=25


@dataclass
class PipeBomb:
    x: float
    y: float
    target_x: float
    target_y: float
    start_distance: float
    age: float=0
    size: float=.5
    angle: float=0
    detonate: int=0


@dataclass
class Blast:
    x: float
    y: float
    age: float=0
    applied: int=0
    scale: float=5
    damage: float=50
    kind: int=0
    hostile: int=0


@dataclass
class Rocket:
    x: float
    y: float
    angle: float
    speed: float=0
    age: float=0
    pending: int=0
    kind: int=0
    hostile: int=0


@dataclass
class EnemyBomb:
    x: float
    y: float
    target_x: float
    target_y: float
    start_distance: float
    speed: float
    age: float=0
    size: float=.5
    angle: float=0


@dataclass
class Flame:
    x: float
    y: float
    angle: float
    kind: int=0
    speed: float=375
    age: float=0


class Combat(WeaponInventory):
    def __init__(self,data,rng=None):
        self.room_size=(2800,1750)
        self.workers=BattleWorkers()
        self.unit_gaps={}
        self.data=data
        self.weapons={name:WeaponState() for name in WEAPON_NAMES}
        self.rng=rng or random.Random()
        self.enemies=[];self.bullets=[];self.coins=[]
        self.mites=[];self.permanent_mines=False
        self.enemy_flames=[];self.fire_zones=[];self.enemy_flame_sound=False
        self.money=5000;self.equipped=False
        self.events=[]
        from .effects import HealingEffects,BattleEffects
        self.healing_effects=HealingEffects()
        self.effects=BattleEffects()
        self.tax=0
        self.weapon='pistol';self.swing_remaining=0
        self.free_buy=False;self.turret_gaps={};self.enemy_target_index=None;self.indexed_enemies=()
        self.structures=[];self.structures_built=0
        self.drones=[]
        self.units=[]
        self.beams=[];self.bombs=[];self.blasts=[];self.enemy_bombs=[]
        self.rockets=[];self.flame_charge=0;self.flames=[]

    def nearest_enemy(self,x,y):
        if self.enemy_target_index is not None:
            index,_=self.enemy_target_index.nearest((x,y,x,y));enemy=self.indexed_enemies[index]
            if enemy.health>0:return enemy
        return min((enemy for enemy in self.enemies if enemy.health>0),key=lambda enemy:(enemy.x-x)**2+(enemy.y-y)**2,default=None)

    def build_turret(self,x,y,blocked):
        return self.build_structure(x,y,blocked,'turret')

    def build_structure(self,x,y,blocked,kind='turret'):
        if kind not in STRUCTURES:return False
        if kind=='command' and any(t.kind=='command' and t.health>0 for t in self.structures):return False
        cost=STRUCTURES[kind]['price']
        if (not self.free_buy and self.money<cost) or blocked(x,y,32) or any((x-t.x)**2+(y-t.y)**2<60**2 for t in self.structures):return False
        self.money-=0 if self.free_buy else cost
        self.structures.append(Turret(x,y,health=STRUCTURES[kind]['health'],radius=37 if kind=='generator' else 20,kind=kind,uid=self.structures_built+1))
        if kind in ('pistol_factory','axe_factory'):
            self.structures[-1].timer=2
            self.structures[-1].parts=[[math.ceil(self.rng.random()*40)-20,math.ceil(self.rng.random()*40)-20] for _ in range(20)]
        if kind=='boss_factory':self.structures[-1].piles=19;self.structures[-1].arm_angle=33
        self.structures_built+=1
        self.events.append('PlaceStructure');return True

    def sell_turret(self,x,y,hit_test=None):
        for turret in reversed(self.structures):
            hit=hit_test(turret,x,y) if hit_test else (x-turret.x)**2+(y-turret.y)**2<=turret.radius**2
            if turret.health>0 and hit:
                self.effects.death(turret,STRUCTURES[turret.kind]['top'])
                for drone in self.drones:
                    if drone.owner_uid==turret.uid:self.effects.death(drone,'MiteTank')
                self.structures.remove(turret);self.money+=STRUCTURES[turret.kind]['refund']
                self.drones=[d for d in self.drones if d.owner_uid!=turret.uid]
                if turret.kind=='boss_factory':
                    for u in self.units:
                        if u.kind=='boss_robot' and u.owner_uid==turret.uid:u.health=0
                    self.resolve_units()
                self.events.extend(('CashPickup','Hit02'));return True
        return False

    def resolve_units(self):
        remaining=[];children=[]
        for unit in self.units:
            if unit.expired:continue
            scatter=unit.kind in ('boss_scatter','boss_small_scatter')
            if unit.health>0 and not (scatter and unit.scatter_speed<=0):remaining.append(unit);continue
            if unit.health<=0:
                self.events.append('Hit02')
                if unit.kind not in ('boss_small','deployed_robot','boss_scatter','boss_small_scatter'):
                    if unit.expired:self.effects.smear(unit,UNIT_TYPES[unit.kind]['sprite'])
                    else:self.effects.death(unit,UNIT_TYPES[unit.kind]['sprite'])
            elif not scatter:self.effects.smear(unit,UNIT_TYPES[unit.kind]['sprite'])
            if unit.kind in ('boss_robot','boss_medium'):
                kind='boss_scatter' if unit.kind=='boss_robot' else 'boss_small_scatter'
                for _ in range(5):children.append(BossRobot(unit.x,unit.y,unit.x if unit.kind=='boss_robot' else unit.home_x,unit.y if unit.kind=='boss_robot' else unit.home_y,health=50,kind=kind,scatter_speed=750,scatter_heading=self.rng.uniform(0,360),radius=16 if kind=='boss_scatter' else 8))
            elif scatter:
                kind='boss_medium' if unit.kind=='boss_scatter' else 'boss_small'
                children.append(BossRobot(unit.x,unit.y,unit.home_x,unit.home_y,health=UNIT_TYPES[kind]['health'],kind=kind,radius=16 if kind=='boss_medium' else 8,patrol_speed=self.rng.uniform(25,125)))
        self.units=remaining+children

    def update_commands(self,player,mouse,dt,collisions=None):
        for tower in self.structures:
            if tower.kind!='command':continue
            distance=math.hypot(player.x-tower.x,player.y-tower.y)
            if player.health>0 and player.vx==0 and player.vy==0 and distance<=player.radius+10:
                player.x,player.y=tower.x,tower.y
            occupied=player.health>0 and tower.health>0 and (collisions.command_occupied(tower,player) if collisions else math.hypot(player.x-tower.x,player.y-tower.y)<=player.radius)
            if not occupied:
                tower.command_active=0;tower.pulse=0;tower.pulse_timer=0;tower.pulse_alpha=.5
                continue
            if not tower.command_active:
                tower.command_active=1;tower.pulse=1;tower.pulse_timer=1
            tower.target_x,tower.target_y=mouse
            tower.pulse_alpha=max(0,min(1,tower.pulse_alpha+(-.5 if tower.pulse==1 else .5)*dt))
            tower.pulse_timer-=dt
            if tower.pulse_timer<=1e-9:tower.pulse=3-tower.pulse;tower.pulse_timer=2

    def control_vehicle(self,player,mouse,horizontal,vertical,dt,blocked,collisions=None,walls=None):
        player.mount_cooldown=max(0,player.mount_cooldown-dt)
        vehicle=next((t for t in self.structures if t.kind in ('buggy','light_tank','juggernaut') and t.uid==player.vehicle_uid and t.health>0),None)
        if player.vehicle_uid and (not vehicle or horizontal or vertical or player.health<=0):
            player.vehicle_uid=0;player.mount_cooldown=.5;self.events.append('TouchBase02');vehicle=None
        if not vehicle and not horizontal and not vertical and player.health>0 and player.vx==0 and player.vy==0 and player.mount_cooldown<=0:
            for t in self.structures:
                if t.kind not in ('buggy','light_tank','juggernaut') or t.health<=0:continue
                sx,sy=offset(t,-77 if t.kind=='juggernaut' else -45)
                if collisions.command_circle(player,sx,sy,10) if collisions else math.hypot(player.x-sx,player.y-sy)<=player.radius+10:
                    vehicle=t;player.vehicle_uid=t.uid;vehicle.seat_timer=1;vehicle.seat_pulse=1;self.events.append('TouchBase');break
        for t in self.structures:
            if t.kind in ('buggy','light_tank','juggernaut') and t is not vehicle:t.seat_alpha=.5
        if vehicle is None:return False
        desired=math.degrees(math.atan2(vehicle.y-mouse[1],mouse[0]-vehicle.x))%360
        delta=(desired-vehicle.angle+180)%360-180
        if abs(delta)<90:vehicle.wheel_angle=desired
        distance=collisions.marker_gap(vehicle,*mouse) if collisions else math.hypot(mouse[0]-vehicle.x,mouse[1]-vehicle.y)
        old_angle=vehicle.angle;move_x=move_y=0
        tank=vehicle.kind=='light_tank';heavy=vehicle.kind=='juggernaut'
        if heavy and vehicle.door_state==0:vehicle.angle=turn(vehicle.angle,desired,25*dt)
        if tank:vehicle.angle=turn(vehicle.angle,desired,100*dt)
        if distance>=(200 if tank else 10) and (not heavy or vehicle.door_state==0):
            if not tank and not heavy:vehicle.angle=turn(vehicle.angle,desired,250*dt)
            speed=min(100 if heavy else 125 if tank else 250,distance*(.2 if heavy else .25 if tank else .5));a=math.radians(vehicle.angle)
            nx,ny=vehicle.x+speed*dt*math.cos(a),vehicle.y-speed*dt*math.sin(a)
            move_x,move_y=nx-vehicle.x,ny-vehicle.y
            if walls is None:vehicle.x,vehicle.y=nx,ny
        if walls is not None and collisions:
            target_angle=vehicle.angle;vehicle.angle=old_angle
            collisions.move_vehicle(vehicle,move_x,move_y,target_angle,walls)
        player.x,player.y=offset(vehicle,-77 if heavy else -45);player.angle=vehicle.angle;player.vx=player.vy=0
        vehicle.seat_alpha=max(0,min(1,vehicle.seat_alpha+(.5 if vehicle.seat_pulse else -.5)*dt))
        vehicle.seat_timer-=dt
        if vehicle.seat_timer<=1e-9:vehicle.seat_timer=2;vehicle.seat_pulse=1-vehicle.seat_pulse
        return True

    def hold_fire(self,player,dt):
        if player.vehicle_uid:return False
        if self.weapon=='flamethrower':
            if not self.equipped or not self.flamethrower_owned or self.flamethrower_ammo<=0 or player.health<=0:return False
            a=math.radians(player.angle)
            for kind,muzzle in ((0,45),(1,50)):
                self.flames.append(Flame(player.x+muzzle*math.cos(a),player.y-muzzle*math.sin(a),player.angle+self.rng.uniform(-10,10),kind))
            if self.flame_charge>=10:
                self.flames.append(Flame(player.x+50*math.cos(a),player.y-47.5*math.sin(a),player.angle,2));self.flame_charge=0
            self.flame_charge+=1;self.flamethrower_ammo-=1;return True
        if self.weapon in ('axe','repair'):return self.fire(player)
        name=self.weapon
        if name not in ('machinegun','minigun') or not self.equipped or not getattr(self,name+'_owned') or getattr(self,name+'_ammo')<=0 or player.health<=0:return False
        cfg=self.data[name];fired=False
        charge=getattr(self,name+'_charge')
        if charge+1e-9>=cfg['interval']:
            a=math.radians(player.angle)
            x,y=player.x+math.cos(a)*cfg['muzzle'],player.y-math.sin(a)*cfg['muzzle']
            a=math.radians(player.angle+math.ceil(self.rng.random()*cfg['spread']-cfg['spread']/2))
            self.bullets.append(Bullet(x,y,math.cos(a)*cfg['speed'],-math.sin(a)*cfg['speed'],cfg['lifetime'],damage=cfg['damage'],kind=int(name=='minigun')))
            setattr(self,name+'_ammo',getattr(self,name+'_ammo')-1);charge=0;self.events.append('Fire03');fired=True
        setattr(self,name+'_charge',min(cfg['interval'],charge+dt))
        return fired

    def fire(self,player,target=None):
        if player.vehicle_uid:
            heavy=next((t for t in self.structures if t.uid==player.vehicle_uid and t.kind=='juggernaut' and t.health>0),None)
            if heavy:
                if heavy.door_state in (0,1):
                    heavy.door_state=2 if heavy.door_state==0 else 3;heavy.door_timer=.9;heavy.deploy_timer=2 if heavy.door_state==2 else 0;return True
                return False
            vehicle=next((t for t in self.structures if t.uid==player.vehicle_uid and t.kind=='light_tank' and t.health>0),None)
            if vehicle and vehicle.charge<=1e-9:
                x,y=offset(vehicle,100)
                self.rockets.append(Rocket(x,y,vehicle.angle,speed=375,kind=2));vehicle.charge=.48;self.events.append('TurretSound');return True
            return False
        if self.equipped and player.health>0 and self.weapon not in ('axe','repair') and self.weapons[self.weapon].ammo<=0:self.events.append('OOA')
        if self.weapon in ('flamethrower','minigun'):return False
        if self.weapon=='rpg':
            if not self.equipped or not self.rpg_owned or self.rpg_ammo<=0 or self.rpg_cooldown>1e-9 or player.health<=0:return False
            cfg=self.data['rpg'];a=math.radians(player.angle)
            self.rockets.append(Rocket(player.x+cfg['muzzle']*math.cos(a),player.y-cfg['muzzle']*math.sin(a),player.angle))
            self.rpg_ammo-=1;self.rpg_cooldown=cfg['cooldown'];self.events.append('Fire06');return True
        if self.weapon=='pipebomb':
            if not self.equipped or not self.pipebomb_owned or player.health<=0:return False
            if self.bombs:
                for bomb in self.bombs:bomb.detonate=1
                return True
            if self.pipebomb_ammo<=0:return False
            a=math.radians(player.angle);m=self.data['pipebomb']['muzzle']
            x,y=player.x+m*math.cos(a),player.y-m*math.sin(a)
            tx,ty=target if target is not None else (x+300*math.cos(a),y-300*math.sin(a))
            # GM distance_to_object measures the landing sprite's bounds.
            distance=math.hypot(max(0,abs(tx-x)-17),max(0,abs(ty-y)-17))
            self.bombs.append(PipeBomb(x,y,tx,ty,distance));self.pipebomb_ammo-=1
            self.events.append('Fire06');return True
        if self.weapon=='railgun':
            if not self.equipped or not self.railgun_owned or self.railgun_ammo<=0 or self.railgun_cooldown>1e-9 or player.health<=0:return False
            cfg=self.data['railgun'];angle=math.radians(player.angle)
            self.beams.append(RailBeam(player.x+cfg['muzzle']*math.cos(angle),player.y-cfg['muzzle']*math.sin(angle),player.angle,cfg['range'],damage=cfg['damage']))
            self.railgun_ammo-=1;self.railgun_cooldown=cfg['cooldown'];self.events.append('RailgunSound')
            return True
        if self.weapon in ('axe','repair'):
            if not self.owns(self.weapon) or not self.equipped or self.swing_remaining>1e-9 or player.health<=0:return False
            self.swing_remaining=.4;self.events.append('Fire05')
            return True
        if self.weapon=='machinegun':return False
        if self.weapon=='shotgun':
            if not self.equipped or not self.shotgun_owned or self.shotgun_ammo<=0 or self.shotgun_cooldown>1e-9 or player.health<=0:return False
            p=self.data['shotgun'];a=math.radians(player.angle)
            x,y=player.x+math.cos(a)*p['muzzle'],player.y-math.sin(a)*p['muzzle']
            for _ in range(p['pellets']):
                angle=math.radians(player.angle+math.ceil(self.rng.random()*p['spread']-p['spread']/2))
                self.bullets.append(Bullet(x,y,math.cos(angle)*p['speed'],-math.sin(angle)*p['speed'],p['lifetime'],damage=p['damage']))
            self.shotgun_ammo-=1;self.shotgun_cooldown=p['cooldown'];self.events.append('Fire04')
            return True
        if not self.equipped or self.ammo<=0 or player.health<=0:return False
        p=self.data['pistol'];angle=math.radians(player.angle)
        dx,dy=math.cos(angle),-math.sin(angle)
        self.bullets.append(Bullet(player.x+dx*p['muzzle'],player.y+dy*p['muzzle'],dx*p['speed'],dy*p['speed'],p['lifetime'],damage=p['damage']))
        self.ammo-=1
        self.events.append('Fire01')
        return True

    def spawn(self,x,y,kind='axebot'):
        enemy=Enemy(x,y,self.data[kind]['health'],kind=kind)
        enemy.uid=max((e.uid for e in self.enemies),default=0)+1
        if kind in ('scatter','scatter_parent','pistol_scatter'):
            enemy.scatter_speed=self.data[kind]['speed']
            enemy.scatter_heading=self.rng.uniform(0,2*math.pi)
        if kind=='railgun_enemy':enemy.dodge_angle=100 if self.rng.random()<.5 else -100
        if kind=='mega_flame':
            enemy.fire_timer=self.data[kind]['rail_delay']
            enemy.dodge_angle=100 if self.rng.random()<.5 else -100
        if kind=='mega_juggernaut':
            enemy.turret_health=self.data[kind]['turret_health'];enemy.side_charges=[0.]*10
            enemy.turn_direction=self.data[kind]['turn_speed']*(1 if self.rng.random()>=.5 else -1)
        if kind=='mega_unit':enemy.move_speed=self.rng.uniform(25,125)
        if kind=='mega_driver':enemy.dodge_angle=90 if self.rng.random()<.5 else -90
        if kind in ('bomber','heavy_apc_unit'):
            enemy.fire_timer=self.data[kind]['interval']
            if kind=='heavy_apc_unit':enemy.move_speed=self.rng.uniform(25,125)
        self.enemies.append(enemy)
        if kind=='enemy_tank':
            self.spawn(*offset(enemy,-45),'enemy_driver')
            driver=self.enemies[-1];driver.owner_uid=enemy.uid
        if kind=='mega_juggernaut':
            driver=self.spawn(*offset(enemy,self.data[kind]['driver_offset']),'mega_driver')
            driver.owner_uid=enemy.uid
        return enemy

    def step(self,player,dt,blocked,collisions=None):
        from . import armor
        armor.step(player,self,dt,collisions)
        self.player_barriers=armor.barriers(player)
        state=self.weapons[self.weapon]
        state.ammo_peak=max(state.ammo_peak,state.ammo)
        if self.equipped and self.weapon not in ('repair','axe') and state.ammo_peak and state.ammo<state.ammo_peak/4 and not state.low_ammo_notified:
            state.low_ammo_notified=True;self.events.append('low_ammo')
        self.enemy_flame_sound=False
        self.healing_effects.step(dt)
        self.effects.step(dt)
        components=[VehicleTurret(t) for t in self.structures if t.kind=='juggernaut' and t.health>0 and t.turret_health>0]
        for mite in self.mites:mite.step(self,dt,collisions,self.permanent_mines)
        allies=[*self.structures,*self.drones,*self.units,*self.mites,*components]
        mounted=next((t for t in self.structures if t.uid==player.vehicle_uid and t.kind=='juggernaut' and t.health>0),None)
        if mounted and self.equipped and self.owns('repair') and self.weapon=='repair' and self.swing_remaining<=0 and player.health>0:
            self.swing_remaining=.4;self.events.append('Fire05')
        self.rpg_cooldown=max(0,self.rpg_cooldown-dt)
        self.railgun_cooldown=max(0,self.railgun_cooldown-dt)
        if self.swing_remaining>0:
            self.swing_remaining=max(0,self.swing_remaining-dt)
            if self.swing_remaining<1e-9:
                self.swing_remaining=0
                if self.weapon=='repair' and player.health>0:
                    # Player overrides the inherited Bullet07 collision with
                    # Health = Health, so a repair swing never heals its owner.
                    for target in [*self.structures,*self.units,*self.mites]:
                        if target.health>0 and (target is mounted or (collisions.repair(player,target) if collisions else math.hypot(target.x-player.x,target.y-player.y)<=37+target.radius)):
                            maximum=STRUCTURES[target.kind]['health'] if isinstance(target,Turret) else UNIT_TYPES[target.kind]['health'] if isinstance(target,PistolRobot) else self.data['player']['health']
                            target.health=min(maximum,target.health+5);self.events.append('RepairSound')
                            width=collisions.assets.image(collisions.ally_name(target)).get_width() if collisions else target.radius*2
                            self.healing_effects.repair(target.x,target.y,width)
                            if isinstance(target,Turret) and target.kind=='juggernaut' and target.turret_health>0:target.turret_health=min(500,target.turret_health+5)
                            if isinstance(target,Turret) and target.kind=='juggernaut' and target.turret_health>0:
                                self.healing_effects.repair(*offset(target,-176),40)
                if self.weapon=='axe' and player.health>0:
                    for enemy in self.enemies:
                        hit=collisions.player_axe(enemy,player) if collisions else math.hypot(enemy.x-player.x,enemy.y-player.y)<=55+self.data[enemy.kind]['radius']
                        if hit:
                            enemy.health-=self.data['axe']['damage'];self.events.append('Hit01')
                        if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0 and collisions and collisions.player_axe(enemy,player,1):
                            enemy.turret_health=max(0,enemy.turret_health-self.data['axe']['damage']);self.events.append('Hit01')
        self.shotgun_cooldown=max(0,self.shotgun_cooldown-dt)
        reinforcements=[]
        self.generator_grid={(round(t.x/75),round(t.y/75)):t for t in self.structures if t.kind=='generator' and t.health>0}
        self.healing_effects.generators(self.generator_grid,dt)
        self.turret_gaps={}
        self.indexed_enemies=tuple(e for e in self.enemies if e.health>0)
        from .config import PARALLEL
        if len(self.indexed_enemies)>=PARALLEL['spatial_minimum_targets'] and len(self.indexed_enemies)*(len(self.structures)+len(self.units))>=PARALLEL['spatial_minimum_pairs']:
            from .spatial import SpatialTargets
            self.enemy_target_index=SpatialTargets(tuple((e.x,e.y) for e in self.indexed_enemies),points=True)
        if collisions:
            firing_turrets=[t for t in self.structures if t.health>0 and t.kind in ('turret','minigun_turret')]
            enemies=[e for e in self.enemies if e.health>0]
            if firing_turrets and enemies:
                def rect_values(rect):return rect.left,rect.top,rect.right,rect.bottom
                enemy_boxes=tuple(rect_values(collisions.bounds(collisions.names[e.kind],e.x,e.y,e.angle)) for e in enemies)
                turret_boxes=tuple(rect_values(collisions.bounds(collisions.ally_name(t),t.x,t.y,t.angle)) for t in firing_turrets)
                self.turret_gaps={id(t):gap for t,gap in zip(firing_turrets,self.workers.gaps(turret_boxes,enemy_boxes))}
        for turret in self.structures:turret.step(self,dt,collisions)
        self.turret_gaps.clear()
        for drone in self.drones:drone.step(self,dt)
        self.unit_gaps={}
        def coordinates(rect):return rect.left,rect.top,rect.right,rect.bottom
        if collisions and self.units:
            enemies=[e for e in self.enemies if e.health>0]
            enemy_bounds=tuple(coordinates(collisions.bounds(collisions.names[e.kind],e.x,e.y,e.angle)) for e in enemies)
            unit_bounds=tuple(coordinates(collisions.bounds(collisions.ally_name(u),u.x,u.y,u.angle)) for u in self.units)
            gaps=self.workers.gaps(unit_bounds,enemy_bounds)
            self.unit_gaps={id(unit):gap for unit,gap in zip(self.units,gaps)}
        for unit in self.units:
            lifetime=UNIT_TYPES[unit.kind].get('lifetime')
            if lifetime:
                unit.age+=dt
                if unit.age>=lifetime-1e-9:unit.health=0;unit.expired=1
            unit.step(self,dt,collisions)
        self.unit_gaps.clear()
        self.enemy_target_index=None;self.indexed_enemies=()
        original_player=player
        cfg=self.data['axebot']
        initial_targets=[target for target in [original_player,*self.structures,*self.drones,*self.units,*self.mites,*components] if target.health>0]
        nearest=self.workers.nearest(tuple((e.x,e.y) for e in self.enemies),tuple((t.x,t.y) for t in initial_targets))
        target_gaps={}
        if collisions and initial_targets:
            querying=[e for e in self.enemies if self.data[e.kind].get('ai') in ('ranged','railgun') or e.attack>0 and 'attack_gap' in self.data[e.kind]]
            enemy_bounds=tuple(coordinates(collisions.bounds(collisions.names[e.kind],e.x,e.y,e.angle)) for e in querying)
            target_bounds=tuple(coordinates(collisions.bounds(collisions.ally_name(t),t.x,t.y,t.angle)) for t in initial_targets)
            target_gaps={id(enemy):gap for enemy,gap in zip(querying,self.workers.gaps(enemy_bounds,target_bounds))}
        for enemy_index,enemy in enumerate(tuple(self.enemies)):
            targets=[target for target in initial_targets if target.health>0]
            candidate=initial_targets[nearest[enemy_index]] if nearest else None
            # Earlier enemies may kill a target. Re-select using current health
            # so parallel queries retain the original sequential damage order.
            player=candidate if candidate is not None and candidate.health>0 else min(targets,key=lambda t:(t.x-enemy.x)**2+(t.y-enemy.y)**2) if targets else original_player
            cfg=self.data[enemy.kind]
            if enemy.health<=0:continue
            enemy.age+=dt
            if cfg.get('ai') in ('mega_flame','mega_juggernaut','mega_driver'):
                from .bosses import step_boss
                step_boss(self,enemy,player,targets,dt,collisions)
                continue
            if enemy.kind=='mega_unit' and enemy.age<cfg['deploy_time']:
                enemy.x,enemy.y=offset(enemy,enemy.move_speed*dt)
                continue
            if cfg.get('ai') in ('bomber','cannon','tank','driver','heavy_apc'):
                from .explosives import step_enemy
                step_enemy(self,enemy,player,targets,original_player,dt,collisions)
                continue
            if cfg.get('ai') in ('ranged','railgun'):
                from .ranged import step_ranged
                gap=target_gaps.get(id(enemy)) if len(targets)==len(initial_targets) else None
                step_ranged(self,enemy,player,targets,original_player,dt,collisions,gap)
                continue
            dx,dy=player.x-enemy.x,player.y-enemy.y
            distance=math.hypot(dx,dy)
            if enemy.kind=='apc':
                if not enemy.deployed:
                    gap=collisions.gap(enemy,player) if collisions else distance-cfg['body_radius']-player.radius
                    if gap>cfg['stop_distance']:
                        enemy.angle=turn(enemy.angle,math.degrees(math.atan2(-dy,dx)),cfg['turn_speed']*dt)
                        nx,ny=offset(enemy,cfg['speed']*dt)
                        if not blocked(nx,ny,cfg['body_radius']):enemy.x,enemy.y=nx,ny
                    else:enemy.deployed=1;enemy.spawn_timer=2
                else:
                    enemy.door_angle=min(150,enemy.door_angle+100*dt)
                    enemy.spawn_timer-=dt
                    if enemy.spawn_timer<=0:
                        heading=enemy.angle+self.rng.uniform(-20,20)
                        a=math.radians(heading)
                        reinforcements.append((enemy.x+40*math.cos(a),enemy.y-40*math.sin(a),heading))
                        enemy.spawn_timer+=4
                if enemy.turret_health>0 and player.health>0:
                    tx,ty=offset(enemy,self.data[enemy.kind].get('turret_offset',-104))
                    target=math.degrees(math.atan2(ty-player.y,player.x-tx))%360
                    enemy.turret_angle=turn(enemy.turret_angle,target,250*dt)
                    if math.hypot(player.x-tx,player.y-ty)<500 and abs((target-enemy.turret_angle+180)%360-180)<1:
                        enemy.fire_timer+=dt
                        if enemy.fire_timer>=.1:
                            a=math.radians(enemy.turret_angle+math.ceil(self.rng.uniform(-2.5,2.5)))
                            self.bullets.append(Bullet(tx,ty,500*math.cos(a),-500*math.sin(a),4,hostile=1,damage=2.5))
                            enemy.fire_timer-=.1;self.events.append('Fire03')
                continue
            if enemy.kind=='apc_unit' and enemy.age<2:
                a=math.radians(enemy.angle)
                enemy.x+=math.cos(a)*enemy.scatter_speed*dt;enemy.y-=math.sin(a)*enemy.scatter_speed*dt
                continue
            if enemy.kind in ('scatter','scatter_parent','pistol_scatter'):
                enemy.angle=math.degrees(math.atan2(-dy,dx))%360
                enemy.scatter_speed=max(0,enemy.scatter_speed-cfg['deceleration']*dt)
                enemy.x+=math.cos(enemy.scatter_heading)*enemy.scatter_speed*dt
                enemy.y-=math.sin(enemy.scatter_heading)*enemy.scatter_speed*dt
                continue
            if enemy.attack>0:
                gap=target_gaps.get(id(enemy)) if len(targets)==len(initial_targets) else None
                if gap is None:gap=min(collisions.gap(enemy,t) for t in targets) if collisions and targets else distance-cfg['radius']-player.radius
                if gap>cfg['attack_gap'] and distance:
                    # All source axe Steps chase outside range even mid-swing.
                    # Once resumed, GM speed persists until the next activation.
                    enemy.melee_vx=dx/distance*cfg['speed'];enemy.melee_vy=dy/distance*cfg['speed']
                nx=enemy.x+enemy.melee_vx*dt;ny=enemy.y+enemy.melee_vy*dt
                if not blocked(nx,enemy.y,cfg['radius']):enemy.x=nx
                if not blocked(enemy.x,ny,cfg['radius']):enemy.y=ny
                enemy.angle=(enemy.angle+360*dt/cfg['attack_duration'])%360
                enemy.attack=max(0,enemy.attack-dt)
                if enemy.attack<1e-9:
                    enemy.attack=0
                    self.events.append('Fire05')
                    for target in targets:
                        if target.health<=0:continue
                        hit=collisions.melee(enemy,target) if collisions else math.hypot(target.x-enemy.x,target.y-enemy.y)<=cfg['attack_radius']+target.radius
                        if hit:
                            target.health=max(0,target.health-cfg['damage'])
                            self.events.append('Hit01')
            elif player.health>0:
                target_angle=math.degrees(math.atan2(-dy,dx))%360
                enemy.angle=turn(enemy.angle,target_angle,cfg.get('turn_speed',50)*dt) if enemy.kind in ('apc_unit','mega_unit') else target_angle
                gap=collisions.gap(enemy,player) if collisions else distance-cfg['radius']-player.radius
                if gap<=cfg['attack_gap']:
                    enemy.attack=cfg['attack_duration']
                    enemy.melee_vx=enemy.melee_vy=0
                elif distance:
                    a=math.radians(enemy.angle)
                    nx=enemy.x+math.cos(a)*cfg['speed']*dt
                    ny=enemy.y-math.sin(a)*cfg['speed']*dt
                    if not blocked(nx,enemy.y,cfg['radius']):enemy.x=nx
                    if not blocked(enemy.x,ny,cfg['radius']):enemy.y=ny
        player=original_player
        from .explosives import step_projectiles
        step_projectiles(self,player,allies,dt,blocked,collisions)
        from .bosses import step_fire
        step_fire(self,[player,*allies],dt,blocked,collisions)
        flames=[]
        for flame in self.flames:
            flame.age+=dt
            if flame.age>=1:continue
            flame.speed=max(0,flame.speed-self.rng.random()*250*dt)
            a=math.radians(flame.angle);flame.x+=flame.speed*dt*math.cos(a);flame.y-=flame.speed*dt*math.sin(a)
            scale=.1+5*flame.age
            if blocked(flame.x,flame.y,2):continue
            consumed=False
            if flame.kind:
                for enemy in self.enemies:
                    if enemy.health<=0:continue
                    for component in range(2 if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0 else 1):
                        tx,ty=offset(enemy,self.data[enemy.kind].get('turret_offset',-104)) if component else (enemy.x,enemy.y)
                        hit=collisions.flame_hit(enemy,flame,component) if collisions else math.hypot(tx-flame.x,ty-flame.y)<=25*scale+self.data[enemy.kind]['radius']
                        if hit:
                            damage=2.5 if flame.kind==1 else 200*dt
                            if component:enemy.turret_health=max(0,enemy.turret_health-damage)
                            else:enemy.health-=damage
                            if flame.kind==1:consumed=True;break
                    if consumed:break
            if not consumed:flames.append(flame)
        self.flames=flames
        rockets=[]
        for rocket in self.rockets:
            if rocket.kind==0:self.effects.rocket_smoke(rocket.x,rocket.y,dt)
            if rocket.hostile:
                rockets.append(rocket);continue
            if rocket.pending:
                if rocket.kind in (1,2):self.blasts.append(Blast(rocket.x,rocket.y,scale=2,damage=50))
                else:self.blasts.extend((Blast(rocket.x,rocket.y),Blast(rocket.x,rocket.y,scale=2.5,damage=100)))
                self.events.append('ExplosionSound');continue
            rocket.age+=dt
            if rocket.age>=(6 if rocket.kind in (1,2) else self.data['rpg']['lifetime']):continue
            if rocket.kind==0:rocket.speed+=self.data['rpg']['acceleration']*dt
            a=math.radians(rocket.angle);dx,dy=rocket.speed*dt*math.cos(a),-rocket.speed*dt*math.sin(a)
            hits=[]
            for index,enemy in enumerate(self.enemies):
                if enemy.health<=0:continue
                for component in range(2 if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0 else 1):
                    tx,ty=offset(enemy,self.data[enemy.kind].get('turret_offset',-104)) if component else (enemy.x,enemy.y)
                    hit=collisions.rocket_hit(enemy,rocket,dx,dy,component) if collisions else segment_hit(rocket.x,rocket.y,dx,dy,tx,ty,18 if component else self.data[enemy.kind]['radius'])
                    if hit is not None:hits.append((hit,index,component))
            wall=None;samples=max(1,math.ceil(math.hypot(dx,dy)))
            for n in range(samples+1):
                if blocked(rocket.x+dx*n/samples,rocket.y+dy*n/samples,2):wall=n/samples;break
            if collisions:
                for enemy in self.enemies:
                    if enemy.kind not in ('enemy_tank','mega_juggernaut') or enemy.health<=0:continue
                    barrier=collisions.enemy_rocket_barrier_hit(enemy,rocket,dx,dy)
                    if barrier is not None and (wall is None or barrier<wall):wall=barrier
            hit=min(hits,default=None)
            if wall is not None and (hit is None or wall<=hit[0]):
                self.events.append('BarrierSound');continue
            travel=hit[0] if hit else 1
            rocket.x+=dx*travel;rocket.y+=dy*travel
            if hit:
                enemy=self.enemies[hit[1]]
                if rocket.kind==0:
                    if hit[2]:enemy.turret_health=max(0,enemy.turret_health-self.data['rpg']['damage'])
                    else:enemy.health-=self.data['rpg']['damage']
                    self.events.append('Hit01')
                rocket.pending=1
            rockets.append(rocket)
        self.rockets=rockets
        bombs=[]
        for bomb in self.bombs:
            bomb.age+=dt
            if bomb.age>=self.data['pipebomb']['lifetime']:continue
            dx,dy=bomb.target_x-bomb.x,bomb.target_y-bomb.y;distance=math.hypot(dx,dy)
            gap=math.hypot(max(0,abs(dx)-17),max(0,abs(dy)-17))
            landed=gap<=10
            if not landed:
                if gap>bomb.start_distance/2:bomb.size+=.5*dt
                elif gap<bomb.start_distance/2:bomb.size-=.5*dt
                bomb.angle=(bomb.angle+500*dt)%360
                travel=min(distance,bomb.start_distance*.5*dt)
                if distance:bomb.x+=dx/distance*travel;bomb.y+=dy/distance*travel
            if bomb.detonate:
                self.blasts.append(Blast(bomb.x,bomb.y));self.events.append('ExplosionSound')
            else:bombs.append(bomb)
        self.bombs=bombs
        for blast in self.blasts:
            if not blast.applied and not blast.kind:self.effects.explode(blast.x,blast.y)
            if not blast.applied:
                if blast.hostile:
                    for target in [player,*allies]:
                        if target.health<=0:continue
                        hit=collisions.ally_blast_hit(target,blast) if collisions else math.hypot(target.x-blast.x,target.y-blast.y)<=37*blast.scale+target.radius
                        if hit:target.health=max(0,target.health-blast.damage)
                    blast.applied=1
                for enemy in self.enemies:
                    if blast.hostile:break
                    if enemy.health<=0:continue
                    hit=collisions.blast_hit(enemy,blast) if collisions else math.hypot(enemy.x-blast.x,enemy.y-blast.y)<=37*blast.scale+self.data[enemy.kind]['radius']
                    if hit:enemy.health-=blast.damage;self.events.append('Hit01')
                    if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0 and collisions and collisions.blast_hit(enemy,blast,1):enemy.turret_health=max(0,enemy.turret_health-blast.damage)
                blast.applied=1
            blast.age+=dt
        self.blasts=[b for b in self.blasts if b.age<.3]
        for beam in self.beams:
            if not beam.applied:
                if collisions:
                    barriers=[*self.structures,*(self.player_barriers if beam.hostile else []),*(e for e in self.enemies if e.kind in ('enemy_tank','mega_juggernaut'))]
                    distance=collisions.rail_barrier_distance(beam.x,beam.y,beam.angle,beam.length,barriers)
                    if distance is not None:
                        beam.length=max(.01,distance);self.events.append('BarrierSound')
                a=math.radians(beam.angle);dx,dy=beam.length*math.cos(a),-beam.length*math.sin(a)
                if beam.hostile:
                    for target in [original_player,*allies]:
                        if target.health<=0:continue
                        hit=collisions.rail_ally_hit(target,beam) if collisions else segment_hit(beam.x,beam.y,dx,dy,target.x,target.y,target.radius) is not None
                        if hit:target.health=max(0,target.health-beam.damage);self.events.append('Hit01')
                for enemy in self.enemies:
                    if beam.hostile:break
                    if enemy.health<=0:continue
                    hit=collisions.rail_hit(enemy,beam) if collisions else segment_hit(beam.x,beam.y,dx,dy,enemy.x,enemy.y,self.data[enemy.kind]['radius']) is not None
                    if hit:enemy.health-=beam.damage;self.events.append('Hit01')
                    if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0 and collisions and collisions.rail_hit(enemy,beam,1):
                        enemy.turret_health=max(0,enemy.turret_health-beam.damage);self.events.append('Hit01')
                beam.applied=1
            beam.age+=dt
        self.beams=[b for b in self.beams if b.age<1]
        # Rebuild a spatial grid once per step; bullets query only nearby cells.
        grid={};cell=128
        for index,enemy in enumerate(self.enemies):
            r=max(self.data[enemy.kind]['radius']+2,200 if enemy.kind in ('apc','heavy_apc','mega_juggernaut') else 100 if collisions else 0)
            for gx in range(math.floor((enemy.x-r)/cell),math.floor((enemy.x+r)/cell)+1):
                for gy in range(math.floor((enemy.y-r)/cell),math.floor((enemy.y+r)/cell)+1):
                    grid.setdefault((gx,gy),[]).append(index)
        alive=[]
        for bullet in self.bullets:
            unlimited=bullet.life<0
            elapsed=dt if unlimited else min(dt,bullet.life)
            dx,dy=bullet.vx*elapsed,bullet.vy*elapsed
            candidates=set()
            for gx in range(math.floor(min(bullet.x,bullet.x+dx)/cell),math.floor(max(bullet.x,bullet.x+dx)/cell)+1):
                for gy in range(math.floor(min(bullet.y,bullet.y+dy)/cell),math.floor(max(bullet.y,bullet.y+dy)/cell)+1):
                    candidates.update(grid.get((gx,gy),()))
            hits=[]
            for index in candidates if not bullet.hostile else ():
                enemy=self.enemies[index]
                if enemy.health<=0:continue
                radius=self.data[enemy.kind].get('body_radius',self.data[enemy.kind]['radius'])
                t=segment_hit(bullet.x,bullet.y,dx,dy,enemy.x,enemy.y,radius+2)
                if collisions:t=collisions.enemy_hit(enemy,bullet.x,bullet.y,dx,dy,projectile_kind=bullet.kind)
                if t is not None:hits.append((t,index,0))
                if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0:
                    tx,ty=offset(enemy,self.data[enemy.kind].get('turret_offset',-104))
                    t=segment_hit(bullet.x,bullet.y,dx,dy,tx,ty,18)
                    if collisions:t=collisions.enemy_hit(enemy,bullet.x,bullet.y,dx,dy,1,projectile_kind=bullet.kind)
                    if t is not None:hits.append((t,index,1))
            if bullet.hostile and player.health>0:
                t=segment_hit(bullet.x,bullet.y,dx,dy,player.x,player.y,player.radius+2)
                if collisions:t=collisions.player_hit(player,bullet.x,bullet.y,dx,dy,bullet.kind)
                if t is not None:hits.append((t,-1,0))
            if bullet.hostile:
                for index,turret in enumerate(allies):
                    if turret.health<=0:continue
                    t=collisions.player_hit(turret,bullet.x,bullet.y,dx,dy,bullet.kind) if collisions else segment_hit(bullet.x,bullet.y,dx,dy,turret.x,turret.y,turret.radius+2)
                    if t is not None:hits.append((t,-2-index,0))
            hit=min(hits,default=None)
            # Pixel-mask walls occlude targets even between simulation frames.
            wall=None
            samples=max(1,math.ceil(math.hypot(dx,dy)))
            for n in range(samples+1):
                t=n/samples
                if blocked(bullet.x+dx*t,bullet.y+dy*t,2):wall=t;break
            if bullet.hostile and collisions:
                for vehicle in [*self.structures,*self.player_barriers]:
                    if vehicle.health<=0:continue
                    barrier=collisions.vehicle_barrier_hit(vehicle,bullet.x,bullet.y,dx,dy)
                    if barrier is not None and (wall is None or barrier<wall):wall=barrier
            elif collisions:
                for enemy in self.enemies:
                    if enemy.kind not in ('enemy_tank','mega_juggernaut') or enemy.health<=0:continue
                    barrier=collisions.enemy_barrier_hit(enemy,bullet.x,bullet.y,dx,dy,bullet.kind)
                    if barrier is not None and (wall is None or barrier<wall):wall=barrier
            if hit is not None and (wall is None or hit[0]<wall):
                if bullet.hostile:
                    target=player if hit[1]==-1 else allies[-hit[1]-2]
                    target.health=max(0,target.health-bullet.damage)
                elif hit[2]:self.enemies[hit[1]].turret_health=max(0,self.enemies[hit[1]].turret_health-bullet.damage)
                else:self.enemies[hit[1]].health-=bullet.damage
                self.events.append('Hit01')
            elif wall is not None:
                self.events.append('BarrierSound')
            elif wall is None:
                bullet.x+=dx;bullet.y+=dy
                if not unlimited:bullet.life-=dt
                if unlimited or bullet.life>0:alive.append(bullet)
        self.bullets=alive
        if any(c.health<=0 for c in components):self.events.append('Hit02')
        if any(t.health<=0 for t in self.structures):self.events.append('Hit02')
        for t in self.structures:
            if t.health<=0:self.effects.death(t,STRUCTURES[t.kind]['top'])
        for mite in self.mites:
            if mite.health<=0:self.effects.death(mite,'MiteTank02')
        for drone in self.drones:
            if drone.health<=0:self.effects.death(drone,'MiteTank')
        self.structures=[t for t in self.structures if t.health>0]
        factories={t.uid for t in self.structures if t.kind=='factory'}
        for drone in self.drones:
            if drone.health>0 and drone.owner_uid not in factories:self.effects.smear(drone,'MiteTank')
        self.drones=[d for d in self.drones if d.health>0 and d.owner_uid in factories]
        self.mites=[m for m in self.mites if m.health>0]
        boss_factories={t.uid for t in self.structures if t.kind=='boss_factory'}
        for u in self.units:
            if u.kind=='boss_robot' and u.owner_uid and u.owner_uid not in boss_factories:u.health=0
        self.resolve_units()
        remaining=[];children=[]
        for enemy in self.enemies:
            cfg=self.data[enemy.kind]
            if enemy.health<=0:
                self.events.append('Hit02')
                if enemy.kind not in ('child','scatter','pistol_child','pistol_scatter','scatter_parent','mega_unit'):self.effects.death(enemy,ENEMY_TYPES[enemy.kind]['sprite'],hostile=True)
                for _ in range(cfg['coin_count']):
                    spread=35 if enemy.kind in ('axe_boss','pistol_boss') else 10
                    self.coins.append(Coin(enemy.x+self.rng.uniform(-spread,spread),enemy.y+self.rng.uniform(-spread,spread),value=cfg['coin_value']))
                if enemy.kind=='splitter':children.extend((enemy.x,enemy.y,'scatter') for _ in range(5))
                if enemy.kind=='pistol_splitter':children.extend((enemy.x,enemy.y,'pistol_scatter') for _ in range(5))
                if enemy.kind=='splitter_boss':
                    children.extend((enemy.x,enemy.y,'scatter_parent') for _ in range(5))
                    for value in (50,250):self.coins.append(Coin(enemy.x+self.rng.uniform(-35,35),enemy.y+self.rng.uniform(-35,35),value=value))
                for value in cfg.get('extra_coins',[]):self.coins.append(Coin(enemy.x+self.rng.uniform(-35,35),enemy.y+self.rng.uniform(-35,35),value=value))
                if enemy.kind=='enemy_tank':
                    for driver in self.enemies:
                        if driver.kind=='enemy_driver' and driver.owner_uid==enemy.uid:driver.health=0
                if enemy.kind=='mega_juggernaut':
                    for driver in self.enemies:
                        if driver.kind=='mega_driver' and driver.owner_uid==enemy.uid:driver.health=0
            elif enemy.age<cfg['lifetime'] and not (enemy.kind in ('scatter','scatter_parent','pistol_scatter') and enemy.scatter_speed<=0):remaining.append(enemy)
            elif enemy.kind not in ('child','scatter','pistol_child','pistol_scatter','scatter_parent','mega_unit'):self.effects.smear(enemy,ENEMY_TYPES[enemy.kind]['sprite'])
            if enemy.kind in ('scatter','scatter_parent') and (enemy.health<=0 or enemy.scatter_speed<=0 or enemy.age>=cfg['lifetime']):
                children.append((enemy.x,enemy.y,'splitter' if enemy.kind=='scatter_parent' else 'child'))
            if enemy.kind=='pistol_scatter' and (enemy.health<=0 or enemy.scatter_speed<=0 or enemy.age>=cfg['lifetime']):children.append((enemy.x,enemy.y,'pistol_child'))
        self.enemies=remaining
        for x,y,kind in children:self.spawn(x,y,kind)
        for x,y,heading in reinforcements:
            self.spawn(x,y,'apc_unit');unit=self.enemies[-1]
            unit.angle=heading;unit.scatter_speed=self.rng.uniform(25,125)
        coins=[];cc=self.data['coin']
        for coin in self.coins:
            coin.age+=dt;dx,dy=player.x-coin.x,player.y-coin.y;distance=math.hypot(dx,dy)
            if player.health>0 and distance<(250 if coin.permanent else cc['magnet_radius']):
                coin.speed+=(2500 if coin.permanent else cc['acceleration'])*dt
                travel=min(distance,coin.speed*dt)
                if distance:coin.x+=dx/distance*travel;coin.y+=dy/distance*travel
                if distance-travel<=player.radius+6:
                    self.money+=round(coin.value*(1-self.tax));self.events.append('CashPickup');continue
            if coin.permanent or coin.age<cc['lifetime']:coins.append(coin)
        self.coins=coins
        if player.health>0:
            cfg=armor.ARMOR[str(player.armor)]
            player.health=min(cfg['health'],player.health+cfg['regeneration']*dt)
