"""Native stationary machinegun turret."""
from dataclasses import dataclass,field
import math

from .config import STRUCTURES,UNIT_TYPES


@dataclass
class Turret:
    x: float
    y: float
    health: float=STRUCTURES['turret']['health']
    angle: float=0
    charge: float=0
    radius: float=20
    kind: str='turret'
    uid: int=0
    timer: float=1
    piles: int=4
    assembly_alpha: float=0
    arm_angle: float=70
    arm_state: int=0
    arm_up: int=0
    part_visible: int=1
    animation_timer: float=.02
    base_on: int=0
    laser_active: int=0
    target_x: float=0
    target_y: float=0
    command_active: int=0
    pulse: int=0
    pulse_timer: float=0
    pulse_alpha: float=.5
    factory_age: float=0
    parts: list=field(default_factory=list)
    parts_visible: int=1048560
    parts_timer: float=4
    ghost_health: float=0
    second_arm_angle: float=327
    turret_angle: float=0
    wheel_angle: float=0
    seat_alpha: float=.5
    seat_timer: float=1
    seat_pulse: int=1

    turret_health: float=STRUCTURES['minigun_turret']['health']
    door_state: int=0
    door_angle: float=0
    door_timer: float=0
    deploy_timer: float=0
    side_charges: list=field(default_factory=lambda:[0.0]*10)

    def step(self,combat,dt,collisions=None):
        match self.kind:
            case 'juggernaut':
                from .combat import Bullet,Rocket,turn,offset,segment_hit
                if self.health<=0:return
                if self.door_state in (2,3):
                    self.door_angle=max(0,min(90,self.door_angle+(100 if self.door_state==2 else -100)*dt))
                    self.door_timer-=dt
                    if self.door_timer<=1e-9:self.door_timer=0;self.door_state=1 if self.door_state==2 else 0
                if self.deploy_timer>0:
                    self.deploy_timer-=dt
                    if self.deploy_timer<=1e-9:
                        self.deploy_timer=.2
                        if sum(u.kind=='deployed_robot' for u in combat.units)<100:
                            for sign in (-1,1):
                                angle=self.angle+sign*combat.rng.uniform(15,45);a=math.radians(angle)
                                combat.units.append(DeployRobot(self.x+150*math.cos(a),self.y-150*math.sin(a),self.x,self.y,angle=angle,radius=8,patrol_speed=combat.rng.uniform(25,125),deploy_heading=angle,move_speed=combat.rng.uniform(25,125)))
                targets=[e for e in combat.enemies if e.health>0]
                tx,ty=offset(self,-176)
                enemy=combat.nearest_enemy(tx,ty)
                desired=math.degrees(math.atan2(ty-enemy.y,enemy.x-tx))%360 if enemy and math.hypot(enemy.x-tx,enemy.y-ty)<750 else self.angle
                self.turret_angle=turn(self.turret_angle,desired,300*dt)
                if self.turret_health>0 and enemy and math.hypot(enemy.x-tx,enemy.y-ty)<750 and abs((desired-self.turret_angle+180)%360-180)<5:
                    if self.charge+1e-9>=.04:
                        a=math.radians(self.turret_angle+math.ceil(combat.rng.random()*5-2.5))
                        combat.bullets.append(Bullet(tx,ty,1000*math.cos(a),-1000*math.sin(a),.8,damage=3.75,kind=1));self.charge=0;combat.events.append('Fire03')
                    self.charge=min(.04,self.charge+dt)
                for i in range(10):
                    side=-79 if i<5 else 79;gx,gy=offset(self,(-66,-33,0,33,66)[i%5],side)
                    angle=self.angle+(90 if i<5 else -90);a=math.radians(angle)
                    if any((collisions.enemy_line(e,gx,gy,angle,2000) if collisions else segment_hit(gx,gy,2000*math.cos(a),-2000*math.sin(a),e.x,e.y,combat.data[e.kind]['radius']) is not None) for e in targets):
                        if self.side_charges[i]+1e-9>=2:
                            combat.rockets.append(Rocket(gx,gy,angle,speed=375,kind=2));self.side_charges[i]=0;combat.events.append('TurretSound')
                        self.side_charges[i]=min(2,self.side_charges[i]+dt)
                return
            case 'light_tank':
                self.charge=max(0,self.charge-dt);return
            case 'buggy':
                from .combat import Bullet,turn,offset
                targets=[e for e in combat.enemies if e.health>0]
                if self.health<=0:return
                tx,ty=offset(self,8)
                if not targets:self.turret_angle=self.angle;return
                enemy=combat.nearest_enemy(tx,ty)
                desired=math.degrees(math.atan2(ty-enemy.y,enemy.x-tx))%360
                self.turret_angle=turn(self.turret_angle,desired,250*dt)
                distance=math.hypot(enemy.x-tx,enemy.y-ty)
                if distance<500 and abs((desired-self.turret_angle+180)%360-180)<5:
                    if self.charge+1e-9>=.1:
                        a=math.radians(self.turret_angle+math.ceil(combat.rng.random()*5-2.5))
                        combat.bullets.append(Bullet(tx,ty,500*math.cos(a),-500*math.sin(a),1.5,damage=2.5))
                        self.charge=0;combat.events.append('Fire03')
                    self.charge=min(.1,self.charge+dt)
                return
            case 'boss_factory':
                if self.health<=0:return
                boss=next((u for u in combat.units if u.kind=='boss_robot' and u.owner_uid==self.uid and u.health>0),None)
                if boss is None:self.assembly_alpha=min(1,self.assembly_alpha+.05*dt)
                if self.arm_state!=2:
                    direction=1 if self.arm_up else -1
                    self.arm_angle=(self.arm_angle+direction*70*dt)%360
                    self.second_arm_angle=(self.second_arm_angle-direction*70*dt)%360
                self.animation_timer-=dt
                if self.animation_timer<=1e-9:
                    self.animation_timer=1
                    inside=(collisions.command_occupied(self,boss) if collisions else math.hypot(boss.x-self.x,boss.y-self.y)<=boss.radius) if boss else False
                    if boss is None or inside and boss.health<UNIT_TYPES['boss_robot']['health']:
                        self.arm_state=0;self.part_visible=1-self.part_visible;self.arm_up=self.part_visible
                        if self.part_visible:
                            if boss:boss.health=min(UNIT_TYPES['boss_robot']['health'],boss.health+25)
                            else:self.ghost_health+=25
                    else:self.arm_state=2;self.arm_angle=33;self.second_arm_angle=327;self.part_visible=1
                self.timer-=dt
                if self.timer<=1e-9:
                    self.timer=1
                    if boss is None:
                        if self.piles==20:self.animation_timer=.02
                        if self.piles>0:self.piles-=1;self.timer=2
                        else:
                            self.piles=20;self.assembly_alpha=0;self.ghost_health=0;self.part_visible=1;self.arm_up=1
                            combat.units.append(BossRobot(self.x,self.y,self.x,self.y,owner_uid=self.uid,radius=37))
                return
            case 'pistol_factory' | 'axe_factory':
                if self.health<=0:return
                self.factory_age+=dt;self.assembly_alpha=min(1,self.assembly_alpha+.1*dt)
                self.timer-=dt
                if self.timer<=1e-9:
                    self.timer=4
                    if self.piles>0:self.piles-=1
                    else:
                        self.piles=4;self.assembly_alpha=0
                        self.parts_visible=(1<<20)-1
                        for dx,dy in ((-40,-40),(-40,40),(40,-40),(40,40)):
                            angle=math.degrees(math.atan2(-dy,dx))%360
                            unit_type=AxeRobot if self.kind=='axe_factory' else PistolRobot
                            combat.units.append(unit_type(self.x+dx,self.y+dy,self.x,self.y,angle=angle,patrol_speed=combat.rng.uniform(25,125)))
                self.parts_timer-=dt
                if self.parts_timer<=1e-9:
                    self.parts_timer=4
                    group=4-self.piles
                    self.parts_visible&=~(15<<(group*4))
                return
            case 'command':return
            case 'cannon':
                from .combat import Rocket,turn
                targets=[e for e in combat.enemies if e.health>0]
                if self.health<=0 or not targets:return
                enemy=max(targets,key=lambda e:(e.x-self.x)**2+(e.y-self.y)**2)
                desired=math.degrees(math.atan2(self.y-enemy.y,enemy.x-self.x))%360
                self.angle=turn(self.angle,desired,50*dt)
                if abs((desired-self.angle+180)%360-180)<5:
                    if self.charge+1e-9>=3:
                        a=math.radians(self.angle)
                        combat.rockets.append(Rocket(self.x+45*math.cos(a),self.y-45*math.sin(a),self.angle,speed=375,kind=1))
                        self.charge=0;combat.events.append('TurretSound')
                    self.charge=min(3,self.charge+dt)
                return
            case 'laser':
                from .combat import Bullet,turn
                self.laser_active=0
                targets=[e for e in combat.enemies if e.health>0]
                if self.health<=0 or not targets:return
                enemy=max(targets,key=lambda e:(e.x-self.x)**2+(e.y-self.y)**2)
                desired=math.degrees(math.atan2(self.y-enemy.y,enemy.x-self.x))%360
                self.angle=turn(self.angle,desired,25*dt)
                if abs((desired-self.angle+180)%360-180)<1:
                    self.laser_active=1;self.target_x,self.target_y=enemy.x,enemy.y
                    if self.charge+1e-9>=.1:
                        combat.bullets.append(Bullet(enemy.x,enemy.y,0,0,.2,damage=4,kind=2))
                        self.charge=0;combat.events.append('LaserSound')
                    self.charge=min(.1,self.charge+dt)
                return
            case 'factory':
                if self.health<=0:return
                drone_present=any(d.owner_uid==self.uid and d.health>0 for d in combat.drones)
                if not drone_present:self.assembly_alpha=min(1,self.assembly_alpha+.1*dt)
                if self.animation_timer>=0:
                    self.animation_timer-=dt
                    if self.animation_timer<=1e-9:
                        self.animation_timer=1
                        if not drone_present:
                            self.part_visible=1-self.part_visible
                            self.arm_up=self.part_visible
                            self.arm_state=self.arm_up
                if self.arm_state!=2:self.arm_angle=(self.arm_angle+(60 if self.arm_state else -60)*dt)%360
                self.timer-=dt
                if self.timer>1e-9:return
                self.timer=1
                if drone_present:return
                if self.piles==5:self.animation_timer=.02;self.base_on=0
                if self.piles>0:self.piles-=1;self.timer=2
                else:
                    self.piles=5
                    self.arm_state=2;self.arm_angle=70;self.assembly_alpha=0
                    self.animation_timer=-1;self.part_visible=1;self.base_on=1
                    combat.drones.append(Drone(self.x+53,self.y+2,self.uid,self.x+53,self.y+2))
                return
            case 'generator':
                if self.health<=0:return
                cell=(round(self.x/75),round(self.y/75))
                count=sum((cell[0]+dx,cell[1]+dy) in combat.generator_grid for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy)
                self.health=min(STRUCTURES['generator']['health'],self.health+count*1.5*dt)
                return
            case _:
                from .combat import Bullet,turn
                targets=[enemy for enemy in combat.enemies if enemy.health>0]
                if self.health<=0 or not targets:return
                enemy=combat.nearest_enemy(self.x,self.y)
                mini=self.kind=='minigun_turret'
                gap=combat.turret_gaps.get(id(self))
                if gap is None:gap=min(collisions.gap(e,self) for e in targets) if collisions else math.hypot(enemy.x-self.x,enemy.y-self.y)
                if gap>=(750 if mini else 500):return
                desired=math.degrees(math.atan2(self.y-enemy.y,enemy.x-self.x))%360
                self.angle=turn(self.angle,desired,300*dt)
                if abs((desired-self.angle+180)%360-180)<5:
                    interval=.04 if mini else .1
                    if self.charge+1e-9>=interval:
                        a=math.radians(self.angle+math.ceil(combat.rng.uniform(-2.5,2.5)))
                        speed=1000 if mini else 500
                        combat.bullets.append(Bullet(self.x,self.y,speed*math.cos(a),-speed*math.sin(a),.8 if mini else 1.5,damage=3.75 if mini else 2.5,kind=int(mini)))
                        self.charge=0;combat.events.append('Fire03')
                    self.charge=min(interval,self.charge+dt)

@dataclass
class Drone:
    x: float
    y: float
    owner_uid: int
    home_x: float
    home_y: float
    health: float=5
    angle: float=0
    radius: float=16
    kind: str='drone'

    def step(self,combat,dt):
        if self.health<=0:return
        coin=min(combat.coins,key=lambda c:(c.x-self.x)**2+(c.y-self.y)**2,default=None)
        x,y=(coin.x,coin.y) if coin else (self.home_x,self.home_y)
        dx,dy=x-self.x,y-self.y;distance=math.hypot(dx,dy)
        if coin is None and distance<=5:
            self.x,self.y=self.home_x,self.home_y;self.angle=0
            return
        if distance:
            travel=min(distance,250*dt)
            self.angle=math.degrees(math.atan2(-dy,dx))%360
            self.x+=dx/distance*travel;self.y+=dy/distance*travel
            if coin is None and distance-travel<=5:
                self.x,self.y=self.home_x,self.home_y;self.angle=0
        if coin and math.hypot(coin.x-self.x,coin.y-self.y)<=self.radius+6:
            combat.coins.remove(coin);combat.money+=round(coin.value*(1-combat.tax));combat.events.append('CashPickup')


@dataclass
class PistolRobot:
    x: float
    y: float
    home_x: float
    home_y: float
    health: float=UNIT_TYPES['pistol_robot']['health']
    angle: float=0
    radius: float=16
    kind: str='pistol_robot'
    patrol_speed: float=50
    charge: float=0
    roam: int=0
    age: float=0
    expired: int=0

    def step(self,combat,dt,collisions=None):
        from .combat import Bullet,turn
        if self.health<=0:return
        command=next((t for t in combat.structures if t.kind=='command' and t.command_active and t.health>0),None)
        if command:
            distance=math.hypot(command.target_x-self.x,command.target_y-self.y)
            near=collisions.command_circle(self,command.target_x,command.target_y,100) if collisions else distance<=100+self.radius
            far=collisions.command_circle(self,command.target_x,command.target_y,200) if collisions else distance<=200+self.radius
            if near:self.roam=1
            elif not far:self.roam=0
        else:self.roam=0
        target=combat.nearest_enemy(self.x,self.y)
        px,py=(command.target_x,command.target_y) if self.roam else (self.home_x,self.home_y)
        distance=math.hypot(px-self.x,py-self.y)
        speed=0;direction=self.angle
        if self.roam and distance>50:
            direction=turn(self.angle,math.degrees(math.atan2(self.y-py,px-self.x)),250*dt);speed=150
        elif target:
            gap=collisions.gap(target,self) if collisions else math.hypot(target.x-self.x,target.y-self.y)
            firing_gap=combat.unit_gaps[id(self)] if id(self) in combat.unit_gaps else min(collisions.gap(e,self) for e in combat.enemies if e.health>0) if collisions else gap
            desired=math.degrees(math.atan2(self.y-target.y,target.x-self.x))%360
            if firing_gap>450:direction=turn(self.angle,desired,250*dt);speed=150 if self.roam else 75
            else:
                direction=desired;interval=.26 if self.roam else .5
                if self.charge+1e-9>=interval:
                    a=math.radians(direction)
                    combat.bullets.append(Bullet(self.x,self.y,750*math.cos(a),-750*math.sin(a),4,damage=5))
                    combat.events.append('Fire01');self.charge=0
                self.charge=min(interval,self.charge+dt)
            self.angle=direction
            if gap<75:direction=(desired+180)%360;speed=75
        else:
            if distance>50:direction=turn(self.angle,math.degrees(math.atan2(self.y-py,px-self.x)),250*dt);speed=150 if self.roam else 75
            else:direction=(math.degrees(math.atan2(self.y-py,px-self.x))+90)%360;speed=self.patrol_speed*(2 if self.roam else 1)
        if target is None or self.roam and distance>50 or firing_gap>450:self.angle=direction
        a=math.radians(direction);self.x+=speed*dt*math.cos(a);self.y-=speed*dt*math.sin(a)


@dataclass
class AxeRobot(PistolRobot):
    health: float=UNIT_TYPES['axe_robot']['health']
    kind: str='axe_robot'
    swing_progress: float=0
    swing_active: int=0
    swing_speed: float=0
    swing_direction: float=0

    def step(self,combat,dt,collisions=None):
        from .combat import Blast,turn
        if self.health<=0:return
        command=next((t for t in combat.structures if t.kind=='command' and t.command_active and t.health>0),None)
        if command:
            distance=math.hypot(command.target_x-self.x,command.target_y-self.y)
            near=collisions.command_circle(self,command.target_x,command.target_y,100) if collisions else distance<=100+self.radius
            far=collisions.command_circle(self,command.target_x,command.target_y,200) if collisions else distance<=200+self.radius
            if near:self.roam=1
            elif not far:self.roam=0
        else:self.roam=0
        if self.swing_active:
            target=combat.nearest_enemy(self.x,self.y)
            gap=combat.unit_gaps.get(id(self))
            if gap is None and target:gap=min(collisions.gap(e,self) for e in combat.enemies if e.health>0) if collisions else math.hypot(target.x-self.x,target.y-self.y)-self.radius-combat.data[target.kind]['radius']
            point=(command.target_x,command.target_y) if self.roam else (self.home_x,self.home_y)
            command_far=self.roam and math.hypot(point[0]-self.x,point[1]-self.y)>50
            if command_far or target and gap>(20 if self.kind=='boss_robot' else 2.5 if self.kind in ('boss_small','deployed_robot') else 15):
                tx,ty=point if command_far else (target.x,target.y)
                self.swing_direction=turn(self.swing_direction,math.degrees(math.atan2(self.y-ty,tx-self.x)),250*dt)
                self.swing_speed=250 if self.roam else 125;self.angle=self.swing_direction
            a=math.radians(self.swing_direction)
            self.x+=self.swing_speed*dt*math.cos(a);self.y-=self.swing_speed*dt*math.sin(a)
            rotation=(900 if self.roam else 450)*dt if self.kind=='boss_robot' else (1800 if self.roam else 900)*dt
            self.angle=(self.angle+rotation)%360;self.swing_progress+=rotation
            if self.swing_progress>=360-1e-9:
                scale,damage=(2,50) if self.kind=='boss_robot' else (.5,2.5) if self.kind in ('boss_small','deployed_robot') else (1.5,5)
                combat.blasts.append(Blast(self.x,self.y,scale=scale,damage=damage,kind=1))
                combat.events.append('Fire05');self.swing_active=0;self.swing_progress=0
            return
        target=combat.nearest_enemy(self.x,self.y)
        px,py=(command.target_x,command.target_y) if self.roam else (self.home_x,self.home_y)
        distance=math.hypot(px-self.x,py-self.y);speed=0
        if self.roam and distance>50:
            desired=math.degrees(math.atan2(self.y-py,px-self.x));speed=250
        elif target:
            desired=math.degrees(math.atan2(self.y-target.y,target.x-self.x))
            gap=combat.unit_gaps[id(self)] if id(self) in combat.unit_gaps else min(collisions.gap(e,self) for e in combat.enemies if e.health>0) if collisions else math.hypot(target.x-self.x,target.y-self.y)-self.radius-combat.data[target.kind]['radius']
            if gap<=(20 if self.kind=='boss_robot' else 2.5 if self.kind in ('boss_small','deployed_robot') else 15):
                self.swing_active=1
                self.swing_speed=0;self.swing_direction=self.angle
                # Source starts rotating in the same step as activation.
                self.step(combat,dt,collisions);return
            speed=250 if self.roam else 125
        else:
            desired=math.degrees(math.atan2(self.y-py,px-self.x))
            if self.kind=='boss_robot':
                if distance<=5:
                    if not self.roam:self.x,self.y=self.home_x,self.home_y;self.angle=0
                    return
                self.angle=turn(self.angle,desired,250*dt)
                a=math.radians(self.angle);speed=250 if self.roam else 125
                self.x+=speed*dt*math.cos(a);self.y-=speed*dt*math.sin(a)
                return
            if distance<=50:self.angle=(desired+90)%360;speed=self.patrol_speed*(2 if self.roam else 1)
            else:speed=250 if self.roam else 125
        if target or distance>50:self.angle=turn(self.angle,desired,250*dt)
        a=math.radians(self.angle);self.x+=speed*dt*math.cos(a);self.y-=speed*dt*math.sin(a)


@dataclass
class BossRobot(AxeRobot):
    health: float=UNIT_TYPES['boss_robot']['health']
    kind: str='boss_robot'
    owner_uid: int=0
    scatter_speed: float=0
    scatter_heading: float=0
    scatter_age: float=0

    def step(self,combat,dt,collisions=None):
        if self.kind in ('boss_scatter','boss_small_scatter'):
            if self.health<=0:return
            self.scatter_age+=dt;self.scatter_speed=max(0,self.scatter_speed-1250*dt)
            a=math.radians(self.scatter_heading)
            self.x+=self.scatter_speed*dt*math.cos(a);self.y-=self.scatter_speed*dt*math.sin(a)
            target=combat.nearest_enemy(self.x,self.y)
            if target:self.angle=math.degrees(math.atan2(self.y-target.y,target.x-self.x))%360
            return
        super().step(combat,dt,collisions)


@dataclass
class DeployRobot(AxeRobot):
    health: float=UNIT_TYPES['deployed_robot']['health']
    kind: str='deployed_robot'
    deploy_age: float=0
    deploy_heading: float=0
    move_speed: float=50

    def step(self,combat,dt,collisions=None):
        self.deploy_age+=dt
        if self.deploy_age>=100:self.health=0;return
        if self.deploy_age<2:
            a=math.radians(self.deploy_heading)
            self.x+=self.move_speed*dt*math.cos(a);self.y-=self.move_speed*dt*math.sin(a);return
        if not any(t.kind=='command' and t.command_active for t in combat.structures) and not any(e.health>0 for e in combat.enemies):
            from .combat import turn
            distance=math.hypot(self.home_x-self.x,self.home_y-self.y)
            desired=math.degrees(math.atan2(self.y-self.home_y,self.home_x-self.x))
            if distance>250:self.angle=turn(self.angle,desired,250*dt);self.move_speed=125
            elif distance<=200:self.angle=desired+90;self.move_speed=self.patrol_speed
            a=math.radians(self.angle);self.x+=self.move_speed*dt*math.cos(a);self.y-=self.move_speed*dt*math.sin(a);return
        super().step(combat,dt,collisions)


class VehicleTurret:
    """Live view of an independently damageable vehicle component."""
    kind='minigun_turret'
    radius=20

    def __init__(self,owner):self.owner=owner
    @property
    def x(self):
        from .combat import offset
        return offset(self.owner,-176)[0]
    @property
    def y(self):
        from .combat import offset
        return offset(self.owner,-176)[1]
    @property
    def angle(self):return self.owner.turret_angle
    @property
    def health(self):return self.owner.turret_health
    @health.setter
    def health(self,value):self.owner.turret_health=value
