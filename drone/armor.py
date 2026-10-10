"""Native suit abilities and parameters from Player and inventory events."""
import json
import math
from types import SimpleNamespace
from .config import DATA

ARMOR=json.loads((DATA/'armor.json').read_text(encoding='utf8'))

def equip(player,number):
    old=ARMOR[str(player.armor)];cfg=ARMOR[str(number)]
    player.health=player.health/old['health']*cfg['health']
    player.armor=number;player.top_speed=cfg['speed'];player.acceleration=cfg['acceleration']
    player.shield_time=0

def buy(player,combat,number):
    if number not in (1,2,3):return False
    if not player.armor_owned&(1<<number):
        cost=ARMOR[str(number)]['price']
        if not getattr(combat,'free_buy',False) and combat.money<cost:combat.events.append('AccessDenied');return False
        if not getattr(combat,'free_buy',False):combat.money-=cost
        player.armor_owned|=1<<number;combat.events.append('Pickup')
    equip(player,0 if player.armor==number else number)
    return True

def activate(player,combat,room):
    if not player.armor or player.armor_cooldown>1e-9 or player.health<=0:return False
    if player.armor==1:
        a=math.radians(player.angle);x=player.x+500*math.cos(a);y=player.y-500*math.sin(a)
        if not (0<x<room['width'] and 0<y<room['height']):return False
        player.warp_x=player.x;player.warp_y=player.y;player.warp_time=.2;player.warp_angle=player.angle
        player.x=x;player.y=y;player.vehicle_uid=0;combat.events.append('WarpSound')
    elif player.armor==2:
        player.scorch_x=player.x;player.scorch_y=player.y;player.scorch_age=0
        combat.events.append('BurnSound')
    else:player.shield_time=10;combat.events.append('PlaceStructure')
    player.armor_cooldown=ARMOR[str(player.armor)]['cooldown']
    return True

def barriers(player):
    if player.shield_time<=0 or player.health<=0:return []
    result=[]
    for index in range(4):
        angle=player.shield_angle+index*90;a=math.radians(angle)
        result.append(SimpleNamespace(kind='armor_shield',x=player.x+70*math.cos(a),y=player.y-70*math.sin(a),angle=(angle-45)%360,health=1))
    return result

def step(player,combat,dt,collisions):
    before=player.armor_cooldown
    player.armor_cooldown=max(0,before-dt);player.shield_time=max(0,player.shield_time-dt)
    player.shield_angle=(player.shield_angle+100*dt)%360;player.warp_time=max(0,player.warp_time-dt)
    if before>0 and player.armor_cooldown==0:combat.events.append('Ready')
    if player.scorch_age>=0:
        player.scorch_age+=dt
        if player.scorch_age>=21.6:player.scorch_age=-1;return
        scale=min(1.5,.025+1.25*player.scorch_age)
        mask=collisions.mask('FireBall',scale) if collisions else None
        for enemy in combat.enemies:
            if enemy.health<=0:continue
            hit=collisions.overlap(mask,player.scorch_x,player.scorch_y,collisions.mask(collisions.names[enemy.kind],angle=enemy.angle),enemy.x,enemy.y) if collisions else math.hypot(enemy.x-player.scorch_x,enemy.y-player.scorch_y)<=250*scale
            if hit:enemy.health=max(0,enemy.health-25*dt)
            if enemy.kind in ('apc','heavy_apc','mega_juggernaut') and enemy.turret_health>0:
                from .combat import offset
                name,x,y,angle=collisions.enemy_turret_pose(enemy) if collisions else ('',*offset(enemy,combat.data[enemy.kind].get('turret_offset',-104)),0)
                hit=collisions.overlap(mask,player.scorch_x,player.scorch_y,collisions.mask(name,angle=angle),x,y) if collisions else math.hypot(x-player.scorch_x,y-player.scorch_y)<=250*scale+18
                if hit:enemy.turret_health=max(0,enemy.turret_health-25*dt)
        if player.scorch_age<=1.2:
            from .effects import ExplosionParticle
            for index in range(36):
                a=math.radians(index*10);distance=312.5*player.scorch_age
                combat.effects.particles.append(ExplosionParticle(player.scorch_x+distance*math.cos(a),player.scorch_y-distance*math.sin(a),0,0))
