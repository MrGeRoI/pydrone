"""Native movement; distances in pixels, time in seconds."""
from dataclasses import dataclass
import math


@dataclass
class Player:
    x: float
    y: float
    top_speed: float
    acceleration: float
    health: float
    radius: float
    vx: float=0
    vy: float=0
    angle: float=0
    vehicle_uid: int=0
    mount_cooldown: float=0
    armor: int=0
    armor_owned: int=0
    armor_cooldown: float=0
    shield_time: float=0
    shield_angle: float=0
    scorch_x: float=0
    scorch_y: float=0
    scorch_age: float=-1
    warp_x: float=0
    warp_y: float=0
    warp_time: float=0
    warp_angle: float=0

    def step(self,horizontal,vertical,mouse,blocked,dt=0.02):
        if blocked(self.x,self.y,self.radius):
            # Recover positions already embedded by an older checkpoint or warp.
            escaped=False
            for distance in range(1,math.ceil(self.radius*2)+1):
                for angle in range(0,360,45):
                    a=math.radians(angle);x=self.x+distance*math.cos(a);y=self.y+distance*math.sin(a)
                    if not blocked(x,y,self.radius):self.x=x;self.y=y;escaped=True;break
                if escaped:break
        for attr,axis in (('vx',horizontal),('vy',vertical)):
            speed=getattr(self,attr)
            if axis:
                speed=max(-self.top_speed,min(self.top_speed,speed+axis*self.acceleration*dt))
            else:
                speed=math.copysign(max(0,abs(speed)-self.acceleration*dt),speed)
            setattr(self,attr,speed)
        # Test each axis from the position already reached on the other axis.
        # Independent tests let diagonal movement enter a protruding corner.
        steps=max(1,math.ceil(max(abs(self.vx*dt),abs(self.vy*dt))/max(1,self.radius/2)))
        for _ in range(steps):
            if blocked(self.x+self.vx*dt/steps,self.y,self.radius):self.vx=0
            else:self.x+=self.vx*dt/steps
            if blocked(self.x,self.y+self.vy*dt/steps,self.radius):self.vy=0
            else:self.y+=self.vy*dt/steps
        self.angle=math.degrees(math.atan2(self.y-mouse[1],mouse[0]-self.x))%360
