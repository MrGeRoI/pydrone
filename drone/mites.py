"""The large friendly money-producing mites (PUMite0101–0106)."""
from dataclasses import dataclass
import math
from .combat import Coin,turn


@dataclass
class MoneyMite:
    x: float
    y: float
    mine_x: float
    mine_y: float
    health: float=100
    angle: float=0
    radius: float=48
    state: int=0
    arm_angle: float=20
    forearm_angle: float=40
    forearm_state: int=0
    mine_alpha: float=1
    mine_rotation: float=0
    speed: float=0
    kind: str='money_mite'

    def step(self,combat,dt,collisions=None,permanent_mine=False):
        if self.health<=0:return
        if self.state==1:
            self.arm_angle=max(10,self.arm_angle-5*dt)
            if self.arm_angle<=10+1e-9:self.state=2;self.forearm_state=1
        elif self.state==2:
            self.arm_angle=min(30,self.arm_angle+15*dt)
            if self.arm_angle>=30-1e-9:
                self.state=3
                for _ in range(5):combat.coins.append(Coin(self.x+combat.rng.uniform(-35,35),self.y+combat.rng.uniform(-35,35),value=50))
        elif self.state==3:
            self.arm_angle=max(20,self.arm_angle-10*dt)
            if self.arm_angle<=20+1e-9:self.state=0
        if self.forearm_state==1:
            self.forearm_angle=min(80,self.forearm_angle+40*dt)
            if self.forearm_angle>=80-1e-9:self.forearm_state=2
        elif self.forearm_state==2:
            self.forearm_angle=max(40,self.forearm_angle-40*dt)
            if self.forearm_angle<=40+1e-9:self.forearm_state=0
        if self.mine_alpha<=0:
            w,h=combat.room_size
            self.mine_x=combat.rng.uniform(250,w-250);self.mine_y=combat.rng.uniform(250,h-250)
            self.mine_alpha=1
        if collisions:
            bounds=collisions.bounds('Crosshairs01',self.mine_x,self.mine_y,0)
            dx=max(bounds.left-self.x,0,self.x-bounds.right)
            dy=max(bounds.top-self.y,0,self.y-bounds.bottom)
            contact=dx*dx+dy*dy<=25
            overlap=collisions.overlap(collisions.mask('MiteTank02',angle=self.angle),self.x,self.y,collisions.mask('Crosshairs01'),self.mine_x,self.mine_y)
        else:
            contact=math.hypot(self.mine_x-self.x,self.mine_y-self.y)<=20
            overlap=math.hypot(self.mine_x-self.x,self.mine_y-self.y)<=self.radius+20
        if contact:
            self.speed=0
            if self.state==0:self.state=1
        else:
            desired=math.degrees(math.atan2(self.y-self.mine_y,self.mine_x-self.x))%360
            self.angle=turn(self.angle,desired,25*dt)
            if abs((self.angle-desired+180)%360-180)<1e-9:self.speed=50
        if overlap and not permanent_mine:self.mine_alpha=max(0,self.mine_alpha-.05*dt)
        self.mine_rotation=(self.mine_rotation+50*dt)%360
        a=math.radians(self.angle)
        self.x+=self.speed*dt*math.cos(a);self.y-=self.speed*dt*math.sin(a)
        self.health=min(100,self.health+.5*dt)
