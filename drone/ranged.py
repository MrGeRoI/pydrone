"""Enemy02/03/0401/0402/Boss02/06 Step behavior, in native time units."""
import math


def step_ranged(combat,enemy,target,targets,player,dt,collisions,gap=None):
    from .combat import Bullet,RailBeam
    cfg=combat.data[enemy.kind]
    if not targets:return
    if gap is None:gap=min(collisions.gap(enemy,t) for t in targets) if collisions else min(max(0,math.hypot(t.x-enemy.x,t.y-enemy.y)-cfg['radius']-t.radius) for t in targets)
    angle=math.degrees(math.atan2(enemy.y-target.y,target.x-enemy.x))%360
    old_angle=enemy.move_angle
    if gap>cfg['stop_gap']:
        enemy.move_speed=cfg['speed'];enemy.move_angle=angle
        enemy.angle=old_angle if enemy.kind=='pistol_boss' else angle
    elif gap<cfg['stop_gap'] or enemy.kind!='pistol_splitter':
        enemy.move_speed=0;enemy.angle=angle
    if cfg['ai']=='railgun':
        enemy.angle=angle;enemy.dodge_timer-=dt
        if enemy.dodge_timer<=1e-9:
            enemy.dodge_timer+=1
            enemy.dodge_angle=90 if combat.rng.random()<.5 else -90
        if gap<=cfg['stop_gap'] and getattr(target,'kind',None)!='generator':
            distance=math.hypot(target.x-enemy.x,target.y-enemy.y)
            a=math.radians(target.angle)
            cx,cy=target.x+distance*math.cos(a),target.y-distance*math.sin(a)
            dodging=collisions.enemy_circle(enemy,cx,cy,cfg['dodge_radius']) if collisions else math.hypot(cx-enemy.x,cy-enemy.y)<=cfg['dodge_radius']+cfg['radius']
            if dodging:enemy.move_speed=cfg['dodge_speed'];enemy.move_angle=angle+enemy.dodge_angle
    if gap<=cfg['fire_range']:
        enemy.angle=angle
        if enemy.fire_timer+1e-9>=cfg['interval']:
            enemy.fire_timer=0
            a=math.radians(angle+(math.ceil(combat.rng.uniform(-cfg['spread']/2,cfg['spread']/2)) if cfg['spread'] else 0))
            x,y=enemy.x+cfg['muzzle']*math.cos(a),enemy.y-cfg['muzzle']*math.sin(a)
            if cfg['ai']=='railgun':
                barrier=collisions.rail_barrier_distance(enemy.x,enemy.y,angle,cfg['beam_length'],combat.structures) if collisions else None
                # The original barrier branch creates friendly Bullet0602.
                hostile=barrier is None
                length=cfg['beam_length'] if hostile else max(0,barrier-cfg['muzzle'])
                if length>0:combat.beams.append(RailBeam(x,y,angle,length,hostile=int(hostile),damage=cfg['beam_damage'] if hostile else combat.data['railgun']['damage']))
                if not hostile:combat.events.append('BarrierSound')
            else:
                combat.bullets.append(Bullet(x,y,cfg['bullet_speed']*math.cos(a),-cfg['bullet_speed']*math.sin(a),cfg['bullet_lifetime'],hostile=1,damage=cfg['bullet_damage'],kind=cfg['bullet_kind']))
            combat.events.append(cfg['sound'])
        enemy.fire_timer=min(cfg['interval'],enemy.fire_timer+dt)
    retreat_target=player if cfg.get('retreat_target')=='player' else target
    retreat_gap=collisions.gap(enemy,retreat_target) if collisions else max(0,math.hypot(retreat_target.x-enemy.x,retreat_target.y-enemy.y)-cfg['radius']-retreat_target.radius)
    inside=0<enemy.x<combat.room_size[0] and 0<enemy.y<combat.room_size[1]
    if retreat_gap<cfg['retreat_gap'] and (inside or cfg.get('retreat_target')=='player'):
        enemy.move_speed=75
        enemy.move_angle=180+math.degrees(math.atan2(enemy.y-retreat_target.y,retreat_target.x-enemy.x))
    a=math.radians(enemy.move_angle)
    enemy.x+=enemy.move_speed*dt*math.cos(a);enemy.y-=enemy.move_speed*dt*math.sin(a)
