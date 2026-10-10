"""Native Enemy07, EnemyBoss04, EnemyVehicle01 and their projectiles."""
import math
from .config import STRUCTURES


def gap_to(combat,enemy,target,collisions):
    if collisions:return collisions.gap(enemy,target)
    return max(0,math.hypot(target.x-enemy.x,target.y-enemy.y)-combat.data[enemy.kind]['radius']-target.radius)


def step_enemy(combat,enemy,target,targets,player,dt,collisions):
    from .combat import EnemyBomb,Rocket,offset,turn
    cfg=combat.data[enemy.kind]
    enemy.reload_timer=max(0,enemy.reload_timer-dt)
    if cfg['ai']=='driver':
        tank=next((e for e in combat.enemies if e.kind=='enemy_tank' and e.uid==enemy.owner_uid and e.health>0),None)
        if tank is None:enemy.health=0;return
        x,y=offset(tank,-45)
        distance=math.hypot(x-enemy.x,y-enemy.y)
        if not enemy.driving:
            enemy.angle=math.degrees(math.atan2(enemy.y-y,x-enemy.x))%360
            travel=min(distance,cfg['speed']*dt)
            if distance:enemy.x+=(x-enemy.x)*travel/distance;enemy.y+=(y-enemy.y)*travel/distance
            if math.hypot(x-enemy.x,y-enemy.y)<5:enemy.driving=1
        if enemy.driving:
            enemy.x,enemy.y=x,y;enemy.angle=tank.angle
        return
    if enemy.kind=='heavy_apc_unit' and enemy.age<cfg['deploy_time']:
        a=math.radians(enemy.angle)
        enemy.x+=enemy.move_speed*dt*math.cos(a);enemy.y-=enemy.move_speed*dt*math.sin(a)
        return
    if not targets:return
    if cfg['ai']=='heavy_apc':
        preferred=[t for t in targets if getattr(t,'kind',None) not in ('drone','money_mite')]
        if not preferred:preferred=targets
        nearest=min(preferred,key=lambda t:(t.x-enemy.x)**2+(t.y-enemy.y)**2)
        gap=min(gap_to(combat,enemy,t,collisions) for t in preferred)
        if not enemy.deployed:
            if gap>cfg['stop_gap']:
                desired=math.degrees(math.atan2(enemy.y-nearest.y,nearest.x-enemy.x))%360
                enemy.angle=turn(enemy.angle,desired,cfg['turn_speed']*dt)
                enemy.x,enemy.y=offset(enemy,cfg['speed']*dt)
            else:enemy.deployed=1;enemy.spawn_timer=2
        else:
            enemy.door_angle=min(150,enemy.door_angle+100*dt)
            enemy.spawn_timer-=dt
            if enemy.spawn_timer<=1e-9:
                heading=enemy.angle+combat.rng.uniform(-20,20)
                a=math.radians(heading)
                unit=combat.spawn(enemy.x+40*math.cos(a),enemy.y-40*math.sin(a),'heavy_apc_unit')
                unit.angle=heading;enemy.spawn_timer+=4
        if enemy.turret_health>0:
            tx,ty=offset(enemy,-104)
            turret_target=min(targets,key=lambda t:(t.x-tx)**2+(t.y-ty)**2)
            distance=math.hypot(turret_target.x-tx,turret_target.y-ty)
            desired=math.degrees(math.atan2(ty-turret_target.y,turret_target.x-tx))%360
            if distance<cfg['turret_range']:
                aligned=desired-5<enemy.turret_angle<desired+5
                enemy.turret_angle=turn(enemy.turret_angle,desired,cfg['turret_turn_speed']*dt)
                if aligned:
                    if enemy.fire_timer+1e-9>=cfg['interval']:
                        a=math.radians(enemy.turret_angle)
                        combat.rockets.append(Rocket(tx+cfg['muzzle']*math.cos(a),ty-cfg['muzzle']*math.sin(a),enemy.turret_angle,speed=375,kind=1,hostile=1))
                        enemy.fire_timer=0;combat.events.append('TurretSound')
                    enemy.fire_timer=min(cfg['interval'],enemy.fire_timer+dt)
            elif gap>1000:enemy.turret_angle=desired
        return
    gap=min(gap_to(combat,enemy,t,collisions) for t in targets)
    angle=math.degrees(math.atan2(enemy.y-target.y,target.x-enemy.x))%360
    if cfg['ai']=='bomber':
        enemy.angle=turn(enemy.angle,angle,50*dt) if enemy.kind=='heavy_apc_unit' and gap>cfg['stop_gap'] else angle
        enemy.move_speed=cfg['speed'] if gap>cfg['stop_gap'] else 0
        enemy.move_angle=enemy.angle
        if gap<=cfg['stop_gap']:
            if enemy.fire_timer+1e-9>=cfg['interval'] and enemy.reload_timer<=1e-9:
                a=math.radians(angle);tx,ty=target.x,target.y
                # PUG2 structures are overshot by 200 pixels when the player
                # is outside range; the source still aims at nearest PUG.
                player_gap=gap_to(combat,enemy,player,collisions)
                structures=[t for t in targets if getattr(t,'kind',None) in STRUCTURES]
                if player_gap>400 and structures and min(gap_to(combat,enemy,t,collisions) for t in structures)<=400:
                    tx+=200*math.cos(a);ty-=200*math.sin(a)
                distance=math.hypot(tx-enemy.x,ty-enemy.y)
                x,y=offset(enemy,cfg['muzzle'])
                combat.enemy_bombs.append(EnemyBomb(x,y,tx,ty,distance,distance/2))
                enemy.fire_timer=0;enemy.reload_timer=cfg['reload'];combat.events.append('Fire06')
                return  # original break skips this step's timer/retreat
            enemy.fire_timer=min(cfg['interval'],enemy.fire_timer+dt)
        if gap<cfg['retreat_gap'] and 0<enemy.x<combat.room_size[0] and 0<enemy.y<combat.room_size[1]:
            enemy.move_speed=75;enemy.move_angle=angle+180
    else:
        if cfg['ai']=='tank':
            driver=next((e for e in combat.enemies if e.kind=='enemy_driver' and e.owner_uid==enemy.uid and e.health>0),None)
            if driver is None:
                # A dead driver's replacement walks in from a random edge.
                side=combat.rng.randrange(4);w,h=combat.room_size
                x=0 if side==0 else w if side==1 else combat.rng.uniform(0,w)
                y=0 if side==2 else h if side==3 else combat.rng.uniform(0,h)
                driver=combat.spawn(x,y,'enemy_driver');driver.owner_uid=enemy.uid
            if not driver.driving:enemy.move_speed=0;return
        # Source checks the previous image_angle for alignment, then turns.
        aligned=angle-10<enemy.angle<angle+10
        enemy.angle=turn(enemy.angle,angle,cfg['turn_speed']*dt)
        enemy.move_angle=enemy.angle
        if gap>cfg['stop_gap']:
            if cfg['ai']=='tank':enemy.move_speed=min(cfg['speed'],enemy.move_speed+cfg['acceleration']*dt)
            else:enemy.move_speed=cfg['speed']
        else:
            enemy.move_speed=0
            if aligned:
                if enemy.fire_timer+1e-9>=cfg['interval']:
                    x,y=offset(enemy,cfg['muzzle'])
                    combat.rockets.append(Rocket(x,y,enemy.angle,speed=cfg['projectile_speed'],kind=2,hostile=1))
                    enemy.fire_timer=0;combat.events.append('TurretSound')
                enemy.fire_timer=min(cfg['interval'],enemy.fire_timer+dt)
    a=math.radians(enemy.move_angle)
    enemy.x+=enemy.move_speed*dt*math.cos(a);enemy.y-=enemy.move_speed*dt*math.sin(a)


def step_projectiles(combat,player,allies,dt,blocked,collisions):
    from .combat import Blast,segment_hit
    bombs=[]
    for bomb in combat.enemy_bombs:
        bomb.age+=dt
        if bomb.age>=2-1e-9:
            combat.blasts.append(Blast(bomb.x,bomb.y,scale=2,damage=25,hostile=1))
            combat.events.append('ExplosionSound');continue
        dx,dy=bomb.target_x-bomb.x,bomb.target_y-bomb.y;distance=math.hypot(dx,dy)
        if distance>bomb.start_distance/2:bomb.size+=.5*dt
        elif distance<bomb.start_distance/2:bomb.size-=.5*dt
        bomb.size=max(.01,bomb.size);bomb.angle=(bomb.angle+500*dt)%360
        travel=min(distance,bomb.speed*dt)
        if distance:bomb.x+=dx/distance*travel;bomb.y+=dy/distance*travel
        bombs.append(bomb)
    combat.enemy_bombs=bombs
    rockets=[]
    for rocket in combat.rockets:
        if not rocket.hostile:rockets.append(rocket);continue
        if rocket.pending:
            combat.blasts.append(Blast(rocket.x,rocket.y,scale=1,damage=50,hostile=1))
            combat.events.append('ExplosionSound');continue
        rocket.age+=dt
        if rocket.age>=5:continue
        a=math.radians(rocket.angle);dx,dy=rocket.speed*dt*math.cos(a),-rocket.speed*dt*math.sin(a)
        hits=[]
        for target in [player,*allies]:
            if target.health<=0:continue
            hit=collisions.ally_rocket_hit(target,rocket,dx,dy) if collisions else segment_hit(rocket.x,rocket.y,dx,dy,target.x,target.y,target.radius)
            if hit is not None:hits.append(hit)
        wall=None;samples=max(1,math.ceil(math.hypot(dx,dy)))
        for n in range(samples+1):
            if blocked(rocket.x+dx*n/samples,rocket.y+dy*n/samples,2):wall=n/samples;break
        if collisions:
            for vehicle in [*combat.structures,*getattr(combat,'player_barriers',[])]:
                if vehicle.health<=0:continue
                hit=collisions.ally_rocket_barrier_hit(vehicle,rocket,dx,dy)
                if hit is not None and (wall is None or hit<wall):wall=hit
        hit=min(hits,default=None)
        if wall is not None and (hit is None or wall<=hit):combat.events.append('BarrierSound');continue
        travel=hit if hit is not None else 1
        rocket.x+=dx*travel;rocket.y+=dy*travel
        if hit is not None:rocket.pending=1
        rockets.append(rocket)
    combat.rockets=rockets
