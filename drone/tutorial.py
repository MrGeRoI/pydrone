"""The original twenty-box tutorial, with native progression and doors."""
import json
from .config import DATA
from . import backend as ui
from .combat import Coin

DEFINITION=json.loads((DATA/'tutorial.json').read_text(encoding='utf8'))
BOXES={box['index']:box for box in DEFINITION['boxes']}
DOORS={3:'left',10:'top',12:'right',14:'top',17:'right',18:'right'}

class Tutorial:
    def __init__(self,state=None):
        self.stage=1;self.revealed={};self.opened=[]
        if state is not None:
            stage=state.get('stage');opened=state.get('opened');revealed=state.get('revealed')
            if type(stage) is not int or not 1<=stage<=21 or not isinstance(opened,list) or any(type(i) is not int or i not in DOORS for i in opened) or not isinstance(revealed,dict):raise ValueError('Invalid tutorial')
            for k,v in revealed.items():
                if not str(k).isdigit() or not 1<=int(k)<=20 or type(v) not in (int,float) or not 0<=v<=1:raise ValueError('Invalid tutorial fog')
            self.stage=stage;self.opened=opened;self.revealed={int(k):v for k,v in revealed.items()}

    def state(self):return {'stage':self.stage,'opened':self.opened,'revealed':self.revealed}

    def doors(self):
        for index,side in DOORS.items():
            if index in self.opened:continue
            box=BOXES[index];x,y=box['x'],box['y']
            for d in (-68,-34,0,34,68):
                yield x+(-170 if side=='left' else 170 if side=='right' else d),y+(-170 if side=='top' else d)

    def install(self,game):
        game.walls=game.walls[:1]
        mask,origin=game.collisions.mask('Giblet03')
        for x,y in self.doors():
            game.walls.append(({'sprite':'Giblet03','x':x,'y':y},mask,ui.Rect(round(x+origin[0]),round(y+origin[1]),*mask.get_size())))

    def open(self,game,index,stage,sound=True):
        if index not in self.opened:self.opened.append(index);self.install(game)
        self.stage=stage
        if sound:game.combat.events.append('PlaceStructure')

    def start(self,game):
        self.install(game);game.combat.money=0;game.combat.equipped=False
        box=BOXES[11]
        for _ in range(10):game.combat.coins.append(Coin(box['x']+game.combat.rng.uniform(-25,25),box['y']+game.combat.rng.uniform(-25,25),permanent=1))

    def contains(self,index,player):
        box=BOXES[index];x,y=box['x'],box['y'];l=t=r=b=170
        if index==11:t=510
        if index==10:b=510
        if index in (3,8):r=510
        if index==14:l=510
        return x-l-player.radius<=player.x<=x+r+player.radius and y-t-player.radius<=player.y<=y+b+player.radius

    def step(self,game,dt):
        p=game.player;c=game.combat
        for index in BOXES:
            if self.contains(index,p):self.revealed.setdefault(index,1)
        for index in self.revealed:self.revealed[index]=max(0,self.revealed[index]-5*dt)
        if self.stage==2:self.open(game,17,3,False)
        if self.stage==3 and c.equipped and c.weapon=='axe':self.stage=4
        if self.stage==4:self.open(game,18,5,False)
        if self.stage==5 and c.weapon=='axe' and c.equipped:self.stage=6
        if self.stage==6 and self.contains(10,p):
            self.stage=7;box=BOXES[10];c.spawn(box['x'],box['y'],'pistol_enemy')
        if self.stage==8:self.open(game,10,9)
        if self.stage==9 and self.contains(3,p):
            self.stage=10;box=BOXES[3]
            for dy in (-85,0,85):c.spawn(box['x'],box['y']+dy,'axebot')
        if self.stage==13:self.open(game,3,14)
        if self.stage==16:self.open(game,12,17)
        if self.stage==17 and self.contains(14,p):
            self.stage=18;box=BOXES[14];c.spawn(box['x'],box['y'],'axe_boss')
        if self.stage==19:self.open(game,14,20)
        if self.stage==20 and self.contains(8,p):
            self.stage=21;game.show_message(game.t('message.tutorial_complete'));game.waves.return_ready=1
            if not game.profile_error:
                try:game.profile.tutorial_complete=True;game.profile.save()
                except OSError:game.notice=game.t('notice.tutorial_save_error')

    def deaths(self,game,previous):
        c=game.combat
        for e in previous:
            if e.health>0:continue
            extra=0
            if self.stage==7 and e.kind=='pistol_enemy':self.stage=8;extra=2
            elif 10<=self.stage<=12 and e.kind=='axebot':self.stage+=1;extra=3
            elif self.stage==18 and e.kind=='axe_boss':self.stage=19
            for _ in range(extra):c.coins.append(Coin(e.x+c.rng.uniform(-10,10),e.y+c.rng.uniform(-10,10),value=50))

    def action_allowed(self,action):
        kind=action[0]
        if kind in ('close','back','quit','credits','denied','tab','page','key','leave_area','music','fullscreen','setting','sound','volume','ui_scale','language','select_language','theme','god_mode','free_buy','reset_checkpoint'):return True
        if kind in ('weapon','purchase') and action[1]=='axe' and self.stage in (1,3):return True
        return kind=='build' and action[1]=='turret' and self.stage==14

    def draw(self,game):
        cfg=game.assets.manifest['fonts']['Font04']
        font=ui.font.SysFont(cfg['family'],max(1,round(cfg['size']*96/72*game.scale)),bool(cfg['bold']))
        for index,box in BOXES.items():
            x,y=game.point(box['x'],box['y']);rows=game.t(f'tutorial.{index}').splitlines()
            for row,line in enumerate(rows):
                text=font.render(line,True,'black');text.set_alpha(191)
                game.screen.blit(text,text.get_rect(center=(round(x),round(y+(row-(len(rows)-1)/2)*24*game.scale))))
            alpha=self.revealed.get(index,1)
            if alpha:ui.draw.rect(game.screen,(0,0,0,round(255*alpha)),ui.Rect(round(x-170*game.scale),round(y-170*game.scale),round(340*game.scale),round(340*game.scale)))
