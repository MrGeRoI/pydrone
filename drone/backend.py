"""Top-left geometry and draw commands consumed by the pyglet renderer."""
from types import SimpleNamespace
from PIL import Image, ImageDraw
import math

SRCALPHA=1
KEYDOWN=1
MOUSEBUTTONDOWN=2
for _name in ('TAB','ESCAPE','PAUSE','F5','F6','F8','F9','F11','SPACE','LEFT','RIGHT','UP','DOWN','h','n','e','q','r','b','w','a','s','d','z','f'):
    globals()['K_'+_name]=_name.lower()

def rgba(value):
    if isinstance(value,str):return {'black':(0,0,0,255),'white':(255,255,255,255),'red':(255,0,0,255)}[value]
    return tuple(value) if len(value)==4 else (*value,255)

class Rect:
    def __init__(self,*args):
        if len(args)==1:
            args=args[0]
            if isinstance(args,Rect):args=(args.x,args.y,args.w,args.h)
        self.x,self.y,self.w,self.h=map(int,args)
    width=property(lambda s:s.w)
    height=property(lambda s:s.h)
    left=property(lambda s:s.x)
    right=property(lambda s:s.x+s.w)
    top=property(lambda s:s.y)
    bottom=property(lambda s:s.y+s.h)
    size=property(lambda s:(s.w,s.h))
    topleft=property(lambda s:(s.x,s.y),lambda s,v:s.update_position(v))
    centerx=property(lambda s:s.x+s.w//2)
    centery=property(lambda s:s.y+s.h//2)
    center=property(lambda s:(s.centerx,s.centery),lambda s,v:s.update_position((v[0]-s.w//2,v[1]-s.h//2)))
    def update_position(self,v):self.x,self.y=map(int,v)
    def move(self,x,y):return Rect(self.x+x,self.y+y,self.w,self.h)
    def collidepoint(self,*point):
        x,y=point[0] if len(point)==1 else point
        return self.left<=x<self.right and self.top<=y<self.bottom
    def colliderect(self,r):return self.left<r.right and r.left<self.right and self.top<r.bottom and r.top<self.bottom
    def contains(self,r):return self.left<=r.left and self.top<=r.top and self.right>=r.right and self.bottom>=r.bottom
    def unionall(self,rects):
        xs=[self,*rects];l=min(r.left for r in xs);t=min(r.top for r in xs)
        return Rect(l,t,max(r.right for r in xs)-l,max(r.bottom for r in xs)-t)
    def clipline(self,a,b):
        x,y=a;dx=b[0]-x;dy=b[1]-y;lo=0;hi=1
        for p,q in ((-dx,x-self.left),(dx,self.right-1-x),(-dy,y-self.top),(dy,self.bottom-1-y)):
            if p==0:
                if q<0:return ()
            elif p<0:lo=max(lo,q/p)
            else:hi=min(hi,q/p)
        return () if lo>hi else ((x+lo*dx,y+lo*dy),(x+hi*dx,y+hi*dy))

class Vector2:
    def __init__(self):self.x=self.y=0
    def update(self,x,y):self.x=x;self.y=y

class CommandList(list):
    def __init__(self,owner):super().__init__();self.owner=owner
    def append(self,command):
        layer=getattr(self.owner,'layer',0)+(1 if command[0]=='text' else 0)
        super().append(('layer',layer,command))

class Surface:
    def __init__(self,size,flags=0,pixels=None):
        self.width,self.height=map(int,size);self.commands=CommandList(self);self.layer=0;self.pixels=pixels;self.opacity=255
    def get_size(self):return self.width,self.height
    def get_width(self):return self.width
    def get_height(self):return self.height
    def get_pitch(self):return self.width*4
    def get_rect(self,**kwargs):
        r=Rect(0,0,self.width,self.height)
        for k,v in kwargs.items():setattr(r,k,v)
        return r
    def set_alpha(self,a):self.opacity=a
    def convert(self):return self
    def convert_alpha(self):return self
    def copy(self):
        s=Surface(self.get_size(),pixels=self.pixels.copy() if self.pixels else None);s.commands=list(self.commands);return s
    def fill(self,color):
        self.commands.clear();self.commands.append(('rect',rgba(color),Rect(0,0,self.width,self.height),0))
        if self.pixels:self.pixels.paste(rgba(color),(0,0,self.width,self.height))
    def blit(self,source,pos,area=None):
        x,y=pos.topleft if isinstance(pos,Rect) else pos
        if isinstance(source,Text):
            if x+source.width<=0 or y+source.height<=0 or x>=self.width or y>=self.height:return
            self.commands.append(('text',source,x,y))
        elif source.pixels is not None:
            if self.pixels is not None:
                if area:self.pixels.paste(source.pixels.crop((area.left,area.top,area.right,area.bottom)),(int(x),int(y)))
                else:self.pixels.paste(source.pixels,(int(x),int(y)))
            else:self.commands.append(('image',source,x,y,source.width,source.height))
        else:self.commands.append(('group',list(source.commands),x,y,self.opacity))

class Text:
    def __init__(self,font,text,color):
        self.font=font;self.text=text;self.color=rgba(color);self.opacity=255
        # Accurate cached font metrics; no OpenGL context needed here.
        import pyglet
        self.metrics=pyglet.font.load(font.family,font.size*72/96,weight='bold' if font.bold else 'normal',italic=font.italic)
        self.width=sum(g.advance for g in self.metrics.get_glyphs(text)[0]);self.height=round(font.size*1.25)
    def get_width(self):return self.width
    def get_rect(self,**kwargs):
        r=Rect(0,0,self.width,self.height)
        for k,v in kwargs.items():setattr(r,k,v)
        return r
    def set_alpha(self,a):self.opacity=a
class Font:
    def __init__(self,family,size,bold=False,italic=False):self.family=family;self.size=size;self.bold=bold;self.italic=italic;self.cache={};self.scale=1.;self.world=False
    def render(self,text,antialias,color):
        key=str(text),rgba(color)
        if key not in self.cache:
            if len(self.cache)>512:self.cache.clear()
            self.cache[key]=Text(self,str(text),color)
        original=self.cache[key]
        result=object.__new__(Text);result.__dict__=original.__dict__.copy()
        result.width=original.width*self.scale;result.height=original.height*self.scale
        return result
from functools import lru_cache

@lru_cache(maxsize=128)
def system_font(family,size,bold=False,italic=False):
    import pyglet
    if not pyglet.font.have_font(family):family='Arial'
    return Font(family,size,bold,italic)

font=SimpleNamespace(SysFont=system_font)

class Draw:
    def rect(self,s,color,rect,width=0,**kwargs):s.commands.append(('rect',rgba(color),Rect(rect),width))
    def circle(self,s,color,center,radius,width=0):s.commands.append(('circle',rgba(color),center,radius,width))
    def ellipse(self,s,color,rect,width=0):s.commands.append(('ellipse',rgba(color),Rect(rect),width))
    def polygon(self,s,color,points):s.commands.append(('polygon',rgba(color),points))
    def line(self,s,color,a,b,width=1):s.commands.append(('line',rgba(color),a,b,width))
draw=Draw()

class Mask:
    def __init__(self,size,fill=False,rows=None):self.width,self.height=size;self.rows=rows if rows is not None else [((1<<self.width)-1) if fill else 0]*self.height
    def get_size(self):return self.width,self.height
    def get_at(self,p):return (self.rows[p[1]]>>p[0])&1
    def overlap(self,other,offset):
        dx,dy=offset
        if dx>=self.width or dx+other.width<=0:return None
        for y in range(max(0,dy),min(self.height,dy+other.height)):
            bits=other.rows[y-dy]<<dx if dx>=0 else other.rows[y-dy]>>-dx
            hit=self.rows[y]&bits
            if hit:return ((hit&-hit).bit_length()-1,y)
        return None
    def get_bounding_rects(self):
        occupied=[(y,row) for y,row in enumerate(self.rows) if row]
        if not occupied:return []
        left=min((r&-r).bit_length()-1 for _,r in occupied);right=max(r.bit_length() for _,r in occupied)
        return [Rect(left,occupied[0][0],right-left,occupied[-1][0]-occupied[0][0]+1)]

def from_surface(surface,threshold=0):
    img=surface.pixels.copy() if surface.pixels else Image.new('RGBA',surface.get_size())
    painter=ImageDraw.Draw(img)
    for cmd in surface.commands:
        if cmd[0]=='layer':cmd=cmd[2]
        kind,color,*v=cmd
        if kind in ('rect','ellipse'):
            r=v[0];box=(r.left,r.top,r.right-1,r.bottom-1)
            (painter.rectangle if kind=='rect' else painter.ellipse)(box,fill=color)
        elif kind=='circle':
            (x,y),r=v[:2];painter.ellipse((x-r,y-r,x+r,y+r),fill=color)
        elif kind=='polygon':painter.polygon(v[0],fill=color)
    # Pillow packs alpha in native code; reverse bit order for our LSB-first rows.
    w,h=img.size
    packed=img.getchannel('A').point(lambda value:255 if value>threshold else 0).convert('1',dither=Image.Dither.NONE).tobytes()
    reverse=bytes(int(f'{value:08b}'[::-1],2) for value in range(256))
    packed=packed.translate(reverse);stride=(w+7)//8
    rows=[int.from_bytes(packed[y*stride:(y+1)*stride],'little') for y in range(h)]
    return Mask((w,h),rows=rows)
mask=SimpleNamespace(from_surface=from_surface)

def load(path):
    pixels=Image.open(path).convert('RGBA');return Surface(pixels.size,pixels=pixels)
image=SimpleNamespace(load=load)
def scale(surface,size):
    if surface.pixels is not None:return Surface(size,pixels=surface.pixels.resize(size,Image.Resampling.NEAREST))
    # Only background images use this path in the game.
    return Surface(size)
def rotate(surface,angle):
    pixels=surface.pixels
    if pixels is None:
        # Rasterise mask primitives before transforming them.
        m=from_surface(surface);pixels=Image.new('RGBA',m.get_size());data=bytearray(m.width*m.height*4)
        for y,row in enumerate(m.rows):
            for x in range(m.width):
                if (row>>x)&1:data[(y*m.width+x)*4:(y*m.width+x)*4+4]=b'\xff\xff\xff\xff'
        pixels=Image.frombytes('RGBA',m.get_size(),bytes(data))
    result=pixels.rotate(angle,Image.Resampling.NEAREST,expand=True);return Surface(result.size,pixels=result)
transform=SimpleNamespace(scale=scale,smoothscale=scale,rotate=rotate)
mouse=SimpleNamespace(position=(0,0),get_pos=lambda:mouse.position)
event=SimpleNamespace(Event=lambda kind,**kwargs:SimpleNamespace(type=kind,**kwargs))
# Test harness has no window; actual windows are owned exclusively by main.py.
display=SimpleNamespace(set_mode=lambda size,*args:Surface(size))
init=lambda:None
quit=lambda:None
