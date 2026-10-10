"""Named PNG resources; transformations are performed by the GPU."""
import json,math
from pathlib import Path
from . import backend
ASSETS=Path(__file__).resolve().parents[1]/'data/assets'
class Resources:
    def __init__(self,root=ASSETS):
        self.root=Path(root);self.manifest=json.loads((self.root/'manifest.json').read_text(encoding='utf8'));self.sprites=self.manifest['sprites'];self.cache={}
    def image(self,name,frame=0):
        sprite=self.sprites[name];frame%=len(sprite['frames']);key=name,frame
        if key not in self.cache:self.cache[key]=backend.image.load(self.root/sprite['frames'][frame]['file'])
        return self.cache[key]
    def draw_sprite(self,target,name,frame,x,y,sx=1,sy=1,angle=0,color=(255,255,255),alpha=1):
        if alpha<=0:return
        image=self.image(name,frame);definition=self.sprites[name]
        # Conservative culling includes arbitrary GameMaker origins.
        radius=math.hypot(image.width*abs(sx),image.height*abs(sy))
        if x+radius<0 or y+radius<0 or x-radius>target.width or y-radius>target.height:return
        target.commands.append(('sprite',image,x,y,sx,sy,angle,tuple(color),alpha,definition['origin_x'],definition['origin_y']))
