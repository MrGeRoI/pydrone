"""Cosmetic healing particles; randomness never changes combat outcomes."""
from dataclasses import dataclass
import math
import random
import json
from pathlib import Path

_SPRITES=json.loads((Path(__file__).resolve().parents[1]/'data/assets/manifest.json').read_text(encoding='utf8'))['sprites']


@dataclass
class HealParticle:
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    kind: int=0
    age: float=0

    @property
    def scale(self):return .5 if self.kind else .05+2.5*self.age
    @property
    def alpha(self):return .25 if self.kind else max(0,.5-.5*self.age)


class HealingEffects:
    def __init__(self):
        self.rng=random.Random()
        self.particles=[]
        self.emitters=[]
        self.generator_clock=0

    def repair(self,x,y,width):
        self.emitters.append([x,y,width,0.0])

    def step(self,dt):
        for p in self.particles:
            p.age+=dt;p.x+=p.vx*dt;p.y+=p.vy*dt
        self.particles=[p for p in self.particles if p.age<p.lifetime]
        remaining=[]
        for x,y,width,age in self.emitters:
            end=min(.2,age+dt)
            for _ in range(max(0,int((end+1e-9)*50)-int((age+1e-9)*50))):
                a=self.rng.uniform(0,2*math.pi);speed=self.rng.uniform(0,50)
                self.particles.append(HealParticle(x+self.rng.uniform(-width/2,width/2),y+self.rng.uniform(-width/2,width/2),speed*math.cos(a),-speed*math.sin(a),1))
            if end<.2-1e-9:remaining.append([x,y,width,end])
        self.emitters=remaining

    def generators(self,grid,dt):
        self.generator_clock+=dt
        while self.generator_clock>=.02-1e-9:
            self.generator_clock=max(0,self.generator_clock-.02)
            for (cx,cy),generator in grid.items():
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        if not (dx or dy) or (cx+dx,cy+dy) not in grid:continue
                        if self.rng.random()>=.05:continue
                        x=generator.x+dx*15+(self.rng.uniform(-5,5) if not dx or dy else 0)
                        y=generator.y+dy*15+(self.rng.uniform(-5,5) if not dy or dx else 0)
                        a=math.atan2(dy,dx);speed=self.rng.uniform(50,100)
                        self.particles.append(HealParticle(x,y,speed*math.cos(a),speed*math.sin(a),44/speed,kind=1))


@dataclass
class DeathMark:
    x: float
    y: float
    sprite: str
    angle: float=0
    age: float=0
    scale: float=1


@dataclass
class ExplosionParticle:
    x: float
    y: float
    vx: float
    vy: float
    age: float=0


@dataclass
class SmokeParticle:
    x: float
    y: float
    vx: float
    vy: float
    age: float=0

class BattleEffects:
    def __init__(self):
        self.rng=random.Random();self.marks=[];self.bursts=[];self.particles=[];self.gibs=[];self.smoke=[];self.shake=0

    def smear(self,actor,sprite):
        width=_SPRITES[sprite]['frames'][0]['width']
        self.marks.append(DeathMark(actor.x,actor.y,'BlastSprite01',self.rng.uniform(0,360),scale=self.rng.uniform(1,1.5)*width/100))

    def death(self,actor,sprite,hostile=False):
        self.smear(actor,sprite)
        big=sprite.startswith(('TankBig','Jugger','Boss','APC'))
        for _ in range(20 if big else 10):
            angle=self.rng.uniform(0,360);speed=self.rng.uniform(250,1250)
            self.gibs.append([actor.x,actor.y,angle,speed,self.rng.uniform(0,speed),self.rng.uniform(0,360),self.rng.uniform(-1250,1250),self.rng.random(),self.rng.random(),0,big,hostile])
        self.explode(actor.x,actor.y)

    def rocket_smoke(self,x,y,dt):
        for _ in range(max(1,round(dt*50))):
            angle=self.rng.uniform(0,2*math.pi)
            self.smoke.append(SmokeParticle(x,y,5*math.cos(angle),-5*math.sin(angle)))

    def explode(self,x,y):self.bursts.append([x,y,0.0]);self.shake=.4

    def step(self,dt):
        for particle in self.smoke:particle.age+=dt;particle.x+=particle.vx*dt;particle.y+=particle.vy*dt
        self.smoke=[particle for particle in self.smoke if particle.age<.5]
        self.shake=max(0,self.shake-dt)
        for mark in self.marks:mark.age+=dt
        self.marks=[mark for mark in self.marks if mark.age<20]
        for gib in self.gibs:
            gib[9]+=dt;gib[5]+=gib[6]*dt
            gib[3]=max(0,gib[3]-gib[4]*50*dt);gib[4]*=.9**(50*dt)
            angle=math.radians(gib[2]);gib[0]+=gib[3]*dt*math.cos(angle);gib[1]-=gib[3]*dt*math.sin(angle)
        self.gibs=[gib for gib in self.gibs if gib[9]<1]
        for p in self.particles:
            p.age+=dt;p.x+=p.vx*dt;p.y+=p.vy*dt
        self.particles=[p for p in self.particles if p.age<.4]
        bursts=[]
        for x,y,age in self.bursts:
            end=min(.5,age+dt)
            # Explosion01 emits three low-opacity Explosion02 particles
            # per 50 Hz frame. Cosmetic randomness is separate from combat.
            for _ in range(3*max(0,int((end+1e-9)*50)-int((age+1e-9)*50))):
                a=self.rng.uniform(0,2*math.pi);speed=self.rng.uniform(50,100)
                self.particles.append(ExplosionParticle(x+self.rng.uniform(-10,10),y+self.rng.uniform(-10,10),speed*math.cos(a),speed*math.sin(a)))
            if end<.5:bursts.append([x,y,end])
        self.bursts=bursts
