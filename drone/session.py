"""Versioned checkpoints and native melee/ranged arena scenarios."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from .combat import Combat, Enemy, Bullet, Coin,RailBeam,PipeBomb,Blast,Rocket,Flame,EnemyBomb
from .model import Player
from .structures import Turret,Drone,STRUCTURES,PistolRobot,AxeRobot,BossRobot,DeployRobot,UNIT_TYPES
from .config import ARENAS,ENEMY_TYPES
from .mites import MoneyMite
from .bosses import EnemyFlame,FireZone

from .paths import SAVE_DIR

SAVE_PATH=SAVE_DIR/'checkpoint.json'
COMBAT_FIELDS=('money','owned','equipped','ammo','tax','weapon','shotgun_owned','shotgun_ammo','shotgun_cooldown','machinegun_owned','machinegun_ammo','machinegun_charge','axe_owned','swing_remaining','structures_built','railgun_owned','railgun_ammo','railgun_cooldown')
COMBAT_FIELDS+=('pipebomb_owned','pipebomb_ammo')
COMBAT_FIELDS+=('rpg_owned','rpg_ammo','rpg_cooldown')
COMBAT_FIELDS+=('flamethrower_owned','flamethrower_ammo','flame_charge')
COMBAT_FIELDS+=('minigun_owned','minigun_ammo','minigun_charge')
COMBAT_FIELDS+=('repair_owned',)


@dataclass
class Waves:
    arena: int=1
    number: int=0
    countdown: float=30
    elapsed: float=0
    pending: int=0
    kind: str='axebot'
    complete: int=0
    clear_pending: int=0
    notification_timer: float=-1
    notification_kind: int=0
    return_ready: int=0
    difficulty: float=.05
    practice: int=0
    spawn_pool: float|None=None

    def start(self,combat):
        if self.number>=60 or self.complete:return
        definition=ARENAS[str(self.arena)]
        if self.number==59 and definition.get('final_bosses'):
            self.number=60;self.pending=0;self.spawn_pool=0;self.countdown=0;self.clear_pending=2
            self.spawn_final(combat)
            return
        kinds=definition['waves']
        self.kind=combat.rng.choice(kinds)[0]
        # Spawner01–06 Alarm 1: time increases once a second, and the
        # selected type spends its pool one enemy per Step, not all at once.
        self.spawn_pool=self.difficulty*(combat.rng.random()+.5)*(definition.get('initial_time',300)+math.floor(self.elapsed))
        self.update_pending()
        self.number+=1
        self.countdown=60 if self.number in (20,40) else 30
        if self.number in (20,40,60):self.clear_pending=2 if self.number==60 else 1

    def spawn_final(self,combat):
        width,height=combat.room_size
        for kind,side in ARENAS[str(self.arena)].get('final_bosses',[]):
            combat.spawn(width*side,combat.rng.uniform(0,height),kind)

    def update_pending(self):
        definition=ARENAS[str(self.arena)]
        _,cost,minimum=next(entry for entry in definition['waves'] if entry[0]==self.kind)
        self.pending=max(0,math.floor((self.spawn_pool-minimum)/cost))
        if not self.pending and self.kind in definition.get('reroll_when_exhausted',[]):
            # Keep the wave active while another source branch can still
            # spend the remaining pool. Never reroll repeatedly in one Step.
            self.pending=int(any(self.spawn_pool-c>=m for _,c,m in definition['waves']))

    def step(self,combat,room,dt):
        events=[]
        if self.notification_timer>=0:
            self.notification_timer-=dt
            if self.notification_timer<=0:
                self.notification_timer=-1
                if self.notification_kind==1:events.append('checkpoint')
                else:self.return_ready=1;events.append('return')
        self.elapsed+=dt;self.countdown-=dt
        if self.countdown<=0 and self.number<60:self.start(combat)
        if self.pending:
            if self.spawn_pool is None:
                # Checkpoints made before native pool accounting retain
                # their already calculated count until the next wave.
                spawn=True;self.pending-=1
            else:
                definition=ARENAS[str(self.arena)]
                _,cost,minimum=next(entry for entry in definition['waves'] if entry[0]==self.kind)
                spawn=self.spawn_pool-cost>=minimum
                if spawn:self.spawn_pool-=cost
                elif self.kind in definition.get('reroll_when_exhausted',[]):self.kind=combat.rng.choice(definition['waves'])[0]
                self.update_pending()
            if spawn:
                side=combat.rng.randrange(4)
                if side<2:x=0 if side==0 else room['width'];y=combat.rng.uniform(0,room['height'])
                else:x=combat.rng.uniform(0,room['width']);y=0 if side==2 else room['height']
                combat.spawn(x,y,self.kind)
        if (self.clear_pending or self.number==60 and not self.complete) and not self.pending and not combat.enemies:
            self.notification_kind=self.clear_pending or 2
            self.clear_pending=0;self.notification_timer=5
            if self.notification_kind==2:self.complete=1;events.append('area_clear')
            else:events.append('level_clear')
        return events

    def skip(self,combat):
        if self.number>=60 or self.clear_pending or self.complete:
            combat.events.append('AccessDenied');return
        combat.events.append('Pickup')
        self.elapsed+=max(0,self.countdown)
        self.start(combat)


def save_game(game,path=SAVE_PATH):
    combat=game.combat
    data={'version':2,'room':game.room_name,'player':asdict(game.player),'waves':asdict(game.waves),
          'combat':{key:getattr(combat,key) for key in COMBAT_FIELDS},
          'enemies':[asdict(e) for e in combat.enemies],'bullets':[asdict(b) for b in combat.bullets],
          'coins':[asdict(c) for c in combat.coins],'random_state':combat.rng.getstate()}
    data['weapon_belt']=[name for name,state in combat.weapons.items() if state.enabled]
    data['structures']=[asdict(t) for t in combat.structures]
    data['drones']=[asdict(d) for d in combat.drones]
    data['units']=[asdict(u) for u in combat.units]
    data['beams']=[asdict(b) for b in combat.beams]
    data['bombs']=[asdict(b) for b in combat.bombs]
    data['blasts']=[asdict(b) for b in combat.blasts]
    data['rockets']=[asdict(r) for r in combat.rockets]
    data['flames']=[asdict(f) for f in combat.flames]
    data['enemy_bombs']=[asdict(b) for b in combat.enemy_bombs]
    data['mites']=[asdict(m) for m in combat.mites]
    data['enemy_flames']=[asdict(f) for f in combat.enemy_flames]
    data['fire_zones']=[asdict(z) for z in combat.fire_zones]
    data['death_marks']=[asdict(mark) for mark in combat.effects.marks]
    if game.tutorial:data['tutorial']=game.tutorial.state()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf8')
    temporary.replace(path)


def load_game(game,path=SAVE_PATH):
    data=json.loads(Path(path).read_text(encoding='utf8'))
    if data.get('version') not in (1,2):raise ValueError('Unsupported checkpoint version')
    if data['room'] not in ('room1','room2',*[arena['room'] for arena in ARENAS.values()]):raise ValueError('Unsupported checkpoint room')
    from .tutorial import Tutorial
    tutorial=Tutorial(data['tutorial']) if data['room']=='room2' else None
    # Build everything before replacing the current session.
    player=Player(**data['player']);waves=Waves(**data['waves']);combat=Combat(game.rules)
    for key in ('money','owned','equipped','ammo'):setattr(combat,key,data['combat'][key])
    combat.tax=data['combat'].get('tax',0)
    for key in COMBAT_FIELDS:
        if key in data['combat']:setattr(combat,key,data['combat'][key])
    if 'repair_owned' not in data['combat'] and combat.weapon=='repair' and combat.equipped:combat.repair_owned=True
    if type(combat.repair_owned) is not bool:raise ValueError('Invalid spanner ownership')
    belt=data.get('weapon_belt',[name for name in combat.weapons if combat.owns(name)])
    if not isinstance(belt,list) or any(not isinstance(name,str) or name not in combat.weapons or not combat.owns(name) for name in belt) or len(belt)!=len(set(belt)):raise ValueError('Invalid weapon belt')
    for name in belt:combat.weapons[name].enabled=True
    if combat.equipped and combat.owns(combat.weapon):combat.weapons[combat.weapon].enabled=True
    if combat.weapon not in ('pistol','shotgun','machinegun','axe','repair','railgun','pipebomb','rpg','flamethrower','minigun') or type(combat.shotgun_owned) is not bool or type(combat.shotgun_ammo) is not int or combat.shotgun_ammo<0 or type(combat.shotgun_cooldown) not in (int,float) or not 0<=combat.shotgun_cooldown<=.48:
        raise ValueError('Invalid shotgun state')
    if type(combat.machinegun_owned) is not bool or type(combat.machinegun_ammo) is not int or combat.machinegun_ammo<0 or type(combat.machinegun_charge) not in (int,float) or not 0<=combat.machinegun_charge<=.1:raise ValueError('Invalid machinegun state')
    if type(combat.axe_owned) is not bool or type(combat.swing_remaining) not in (int,float) or not 0<=combat.swing_remaining<=.4:raise ValueError('Invalid axe state')
    if type(combat.railgun_owned) is not bool or type(combat.railgun_ammo) is not int or combat.railgun_ammo<0 or type(combat.railgun_cooldown) not in (int,float) or not 0<=combat.railgun_cooldown<=.18:raise ValueError('Invalid railgun state')
    if type(combat.pipebomb_owned) is not bool or type(combat.pipebomb_ammo) is not int or combat.pipebomb_ammo<0:raise ValueError('Invalid pipebomb state')
    if type(combat.flamethrower_owned) is not bool or type(combat.flamethrower_ammo) is not int or combat.flamethrower_ammo<0 or type(combat.flame_charge) is not int or not 0<=combat.flame_charge<=10:raise ValueError('Invalid flame inventory')
    if type(combat.minigun_owned) is not bool or type(combat.minigun_ammo) is not int or combat.minigun_ammo<0 or type(combat.minigun_charge) not in (int,float) or not 0<=combat.minigun_charge<=.04:raise ValueError('Invalid minigun state')
    if type(combat.rpg_owned) is not bool or type(combat.rpg_ammo) is not int or combat.rpg_ammo<0 or type(combat.rpg_cooldown) not in (int,float) or not 0<=combat.rpg_cooldown<=.98:raise ValueError('Invalid RPG state')
    if type(combat.tax) not in (int,float) or combat.tax not in (-.2,0,.2,.4,.6,.8):raise ValueError('Invalid tax')
    combat.enemies=[Enemy(**e) for e in data['enemies']]
    combat.bullets=[Bullet(**b) for b in data['bullets']]
    if data['version']==1:
        for bullet in combat.bullets:
            if bullet.hostile:bullet.damage=2.5
    combat.coins=[Coin(**c) for c in data['coins']]
    combat.structures=[Turret(**t) for t in data.get('structures',[])]
    combat.drones=[Drone(**d) for d in data.get('drones',[])]
    combat.units=[(DeployRobot if u.get('kind')=='deployed_robot' else BossRobot if u.get('kind','').startswith('boss_') else AxeRobot if u.get('kind')=='axe_robot' else PistolRobot)(**u) for u in data.get('units',[])]
    combat.beams=[RailBeam(**b) for b in data.get('beams',[])]
    combat.bombs=[PipeBomb(**b) for b in data.get('bombs',[])]
    combat.blasts=[Blast(**b) for b in data.get('blasts',[])]
    combat.rockets=[Rocket(**r) for r in data.get('rockets',[])]
    combat.flames=[Flame(**f) for f in data.get('flames',[])]
    combat.enemy_bombs=[EnemyBomb(**b) for b in data.get('enemy_bombs',[])]
    combat.mites=[MoneyMite(**m) for m in data.get('mites',[])]
    combat.enemy_flames=[EnemyFlame(**f) for f in data.get('enemy_flames',[])]
    combat.fire_zones=[FireZone(**z) for z in data.get('fire_zones',[])]
    from .effects import DeathMark
    combat.effects.marks=[DeathMark(**mark) for mark in data.get('death_marks',[])]
    for mark in combat.effects.marks:
        if mark.sprite not in game.assets.sprites or any(type(v) not in (int,float) or not math.isfinite(v) for v in (mark.x,mark.y,mark.angle)):raise ValueError('Invalid death mark')
        if type(mark.age) not in (int,float) or not 0<=mark.age<20 or type(mark.scale) not in (int,float) or not 0<mark.scale<=10:raise ValueError('Invalid death mark age or scale')
    if len(combat.bombs)>1:raise ValueError('Invalid active bomb count')
    if type(combat.structures_built) is not int or combat.structures_built<len(combat.structures):raise ValueError('Invalid build counter')
    def check_finite(value):
        if isinstance(value,dict):
            for item in value.values():check_finite(item)
        elif isinstance(value,list):
            for item in value:check_finite(item)
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            if not math.isfinite(value):raise ValueError('Non-finite checkpoint value')
    check_finite(data)
    for key in ('money','ammo'):
        value=getattr(combat,key)
        if type(value) is not int or value<0:raise ValueError('Invalid inventory')
    owned=combat.owns(combat.weapon)
    if type(combat.owned) is not bool or type(combat.equipped) is not bool or combat.equipped and not owned:
        raise ValueError('Invalid weapon state')
    for record in (player,waves,*combat.enemies,*combat.bullets,*combat.coins,*combat.structures,*combat.drones,*combat.units,*combat.beams,*combat.bombs,*combat.blasts,*combat.rockets,*combat.flames,*combat.enemy_bombs,*combat.mites,*combat.enemy_flames,*combat.fire_zones):
        fields=asdict(record)
        if isinstance(record,Coin) and (type(record.permanent) is not int or record.permanent not in (0,1)):raise ValueError('Invalid coin')
        if isinstance(record,MoneyMite):
            if fields.pop('kind')!='money_mite' or not 0<record.health<=100 or record.state not in (0,1,2,3) or record.forearm_state not in (0,1,2) or not 10<=record.arm_angle<=30 or not 40<=record.forearm_angle<=80 or not 0<=record.mine_alpha<=1 or not 0<=record.speed<=50:raise ValueError('Invalid money mite')
        if isinstance(record,Bullet) and (type(record.kind) is not int or record.kind not in (0,1,2,3) or record.hostile not in (0,1) or record.damage<=0):raise ValueError('Invalid projectile kind')
        if isinstance(record,Flame) and (not 0<=record.age<1 or not 0<=record.speed<=375 or record.kind not in (0,1,2)):raise ValueError('Invalid flame')
        if isinstance(record,EnemyFlame) and (record.kind not in (0,1,2) or not 0<=record.age<record.duration or record.duration not in (.5,1.2,1.3) or not 0<=record.speed<=375 or record.start_scale not in (.02,.1) or record.growth not in (2,5) or record.alpha not in (.5,.65) or record.damage not in (0,2.5)):raise ValueError('Invalid enemy flame')
        if isinstance(record,FireZone) and (not 0<=record.age<record.duration or record.duration!=21.6 or record.damage!=.25):raise ValueError('Invalid fire zone')
        if isinstance(record,PipeBomb) and (not 0<=record.age<10 or record.start_distance<0 or not 0<record.size<=2 or record.detonate not in (0,1)):raise ValueError('Invalid bomb')
        if isinstance(record,EnemyBomb) and (not 0<=record.age<2 or record.start_distance<0 or record.speed<0 or not .01<=record.size<=2):raise ValueError('Invalid enemy bomb')
        if isinstance(record,Blast):
            allowed=((0,1,50),(0,2,25)) if record.hostile else ((0,5,50),(0,2.5,100),(0,2,50),(1,1.5,5),(1,2,50),(1,.5,2.5))
            if record.hostile not in (0,1) or not 0<=record.age<.3 or record.applied not in (0,1) or (record.kind,record.scale,record.damage) not in allowed:raise ValueError('Invalid blast')
        if isinstance(record,Rocket) and (record.hostile not in (0,1) or record.hostile and record.kind not in (1,2) or record.kind not in (0,1,2) or not 0<=record.age<(5 if record.hostile else 6 if record.kind in (1,2) else 4) or not 0<=record.speed<=10000 or record.pending not in (0,1)):raise ValueError('Invalid rocket')
        if isinstance(record,RailBeam) and (not 0<record.length<=3000 or not 0<=record.age<1 or record.applied not in (0,1) or record.hostile not in (0,1) or record.damage not in (10,25)):raise ValueError('Invalid beam')
        if isinstance(record,Turret):
            kind=fields.pop('kind')
            parts=fields.pop('parts')
            charges=fields.pop('side_charges')
            if not isinstance(charges,list) or len(charges)!=10 or any(type(v) not in (int,float) or not 0<=v<=2 for v in charges):raise ValueError('Invalid side guns')
            if not 0<=record.turret_health<=500:raise ValueError('Invalid vehicle turret health')
            if record.door_state not in (0,1,2,3) or not 0<=record.door_angle<=90 or not 0<=record.door_timer<=.9 or not 0<=record.deploy_timer<=2:raise ValueError('Invalid doors')
            if not isinstance(parts,list) or len(parts) not in (0,20) or any(not isinstance(p,list) or len(p)!=2 or any(type(v) is not int or not -20<=v<=20 for v in p) for p in parts):raise ValueError('Invalid factory parts')
            if type(record.parts_visible) is not int or not 0<=record.parts_visible<(1<<20) or not 0<record.parts_timer<=4:raise ValueError('Invalid part phase')
            if kind not in STRUCTURES or not 0<record.health<=STRUCTURES[kind]['health'] or record.radius<=0:raise ValueError('Invalid structure')
            if kind=='light_tank' and not 0<=record.charge<=.48:raise ValueError('Invalid tank cooldown')
            if kind in ('buggy','light_tank','juggernaut') and (not 0<=record.charge<=(.48 if kind=='light_tank' else .04 if kind=='juggernaut' else .1) or not 0<=record.seat_alpha<=1 or not 0<record.seat_timer<=2 or record.seat_pulse not in (0,1)):raise ValueError('Invalid buggy state')
            if kind=='minigun_turret' and not 0<=record.charge<=.04:raise ValueError('Invalid minigun turret state')
            if kind=='cannon' and not 0<=record.charge<=3:raise ValueError('Invalid cannon state')
            if kind in ('pistol_factory','axe_factory') and (type(record.piles) is not int or not 0<=record.piles<=4 or not 0<record.timer<=4 or not 0<=record.assembly_alpha<=1 or record.factory_age<0):raise ValueError('Invalid robot assembly')
            if kind=='command' and (record.command_active not in (0,1) or record.pulse not in (0,1,2) or not 0<=record.pulse_alpha<=1 or not 0<=record.pulse_timer<=2 or bool(record.command_active)!=bool(record.pulse)):raise ValueError('Invalid command state')
            if kind=='boss_factory' and (type(record.piles) is not int or not 0<=record.piles<=20 or not 0<record.timer<=2 or not 0<=record.assembly_alpha<=1 or not 0<=record.ghost_health<=500 or record.arm_state not in (0,2) or record.arm_up not in (0,1) or record.part_visible not in (0,1) or not 0<record.animation_timer<=1):raise ValueError('Invalid boss assembly')
            if kind=='laser' and (record.laser_active not in (0,1) or not 0<=record.charge<=.1):raise ValueError('Invalid laser state')
            if kind=='factory' and (not 0<=record.assembly_alpha<=1 or record.arm_state not in (0,1,2) or record.arm_up not in (0,1) or record.part_visible not in (0,1) or record.base_on not in (0,1)):raise ValueError('Invalid assembly phase')
        if isinstance(record,Drone):
            if fields.pop('kind')!='drone' or not 0<record.health<=5:raise ValueError('Invalid drone')
        if isinstance(record,PistolRobot):
            kind=fields.pop('kind')
            if kind not in UNIT_TYPES or not 0<record.health<=UNIT_TYPES[kind]['health'] or record.roam not in (0,1) or not 25<=record.patrol_speed<=125 or not 0<=record.charge<=.5 or record.radius<=0:raise ValueError('Invalid robot')
            if isinstance(record,BossRobot) and (kind not in ('boss_robot','boss_medium','boss_small','boss_scatter','boss_small_scatter') or type(record.owner_uid) is not int or record.owner_uid<0 or not 0<=record.scatter_speed<=750 or not 0<=record.scatter_age<=.61):raise ValueError('Invalid boss robot')
            if isinstance(record,AxeRobot) and (record.swing_active not in (0,1) or not 0<=record.swing_progress<360):raise ValueError('Invalid axe swing')
        if isinstance(record,DeployRobot) and (not 0<=record.deploy_age<100 or not 0<=record.move_speed<=250):raise ValueError('Invalid deployed robot')
        if isinstance(record,Waves):
            fields.pop('spawn_pool')
            if type(record.arena) is not int or str(record.arena) not in ARENAS:raise ValueError('Invalid arena')
            if fields.pop('kind') not in [entry[0] for entry in ARENAS[str(record.arena)]['waves']]:raise ValueError('Invalid wave kind')
        if isinstance(record,Enemy):
            if fields.pop('kind') not in ENEMY_TYPES:raise ValueError('Invalid enemy kind')
            charges=fields.pop('side_charges')
            if not isinstance(charges,list) or len(charges)!=(10 if record.kind=='mega_juggernaut' else 0) or any(type(v) not in (int,float) or not 0<=v<=2 for v in charges):raise ValueError('Invalid enemy side guns')
            if record.phase not in (0,1,2) or not 0<=record.phase_timer<=5 or record.door_state not in (0,1,2,3) or not 0<=record.door_timer<=.9:raise ValueError('Invalid boss phase')
        if any(type(value) not in (int,float) for value in fields.values()):raise ValueError('Invalid entity field')
    factory_ids={t.uid for t in combat.structures if t.kind=='factory'}
    boss_ids={t.uid for t in combat.structures if t.kind=='boss_factory'}
    owners=[u.owner_uid for u in combat.units if u.kind=='boss_robot']
    if len(owners)!=len(set(owners)) or any(owner not in boss_ids for owner in owners):raise ValueError('Invalid boss ownership')
    if sum(t.kind=='command' for t in combat.structures)>1:raise ValueError('Duplicate command tower')
    if len(factory_ids)!=sum(t.kind=='factory' for t in combat.structures) or any(d.owner_uid not in factory_ids for d in combat.drones) or len({d.owner_uid for d in combat.drones})!=len(combat.drones):raise ValueError('Invalid factory links')
    if type(player.vehicle_uid) is not int or player.vehicle_uid<0 or not 0<=player.mount_cooldown<=.5 or player.vehicle_uid and sum(t.kind in ('buggy','light_tank','juggernaut') and t.uid==player.vehicle_uid for t in combat.structures)!=1:raise ValueError('Invalid mounted vehicle')
    from .armor import ARMOR
    if type(player.armor) is not int or str(player.armor) not in ARMOR or type(player.armor_owned) is not int or not 0<=player.armor_owned<=14 or player.armor and not player.armor_owned&(1<<player.armor):raise ValueError('Invalid armor')
    if not 0<=player.armor_cooldown<=40 or not 0<=player.shield_time<=10 or not -1<=player.scorch_age<=21.6 or not 0<=player.warp_time<=1:raise ValueError('Invalid armor timers')
    if not 0<=player.health<=ARMOR[str(player.armor)]['health'] or player.radius<=0:raise ValueError('Invalid player')
    if type(waves.number) is not int or type(waves.pending) is not int or min(waves.number,waves.pending,waves.elapsed)<0:
        raise ValueError('Invalid wave state')
    if waves.arena not in range(1,7) or waves.kind not in {entry[0] for entry in ARENAS[str(waves.arena)]['waves']}:raise ValueError('Invalid wave type')
    if waves.spawn_pool is not None and (type(waves.spawn_pool) not in (int,float) or not math.isfinite(waves.spawn_pool) or waves.spawn_pool<0):raise ValueError('Invalid spawn pool')
    if waves.difficulty not in (.03,.05,.07) or waves.practice not in (0,1):raise ValueError('Invalid scenario')
    if data['room'] not in ('room1','room2') and data['room']!=ARENAS[str(waves.arena)]['room']:raise ValueError('Arena and room mismatch')
    combat.permanent_mines=ARENAS[str(waves.arena)].get('permanent_mines',False)
    def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,list) else value
    combat.rng.setstate(tuples(data['random_state']))
    combat.free_buy=getattr(game,'free_buy',False)
    game.combat.workers.close()
    game.set_room(data['room'])
    game.player=player;game.waves=waves;game.combat=combat;game.paused=False;game.building=False;game.selling=False
    game.tutorial=tutorial
    if tutorial:tutorial.install(game)
    game.menu.open=False;game.block_fire=True
    game.death_marked=player.health<=0
    game.transition=None
    game.resize(game.screen)
