"""Persistent pyglet sprites, labels and shapes, with original draw ordering."""
import pyglet
from pyglet import shapes
from collections import defaultdict

class Renderer:
    def __init__(self,window):
        self.window=window;self.batch=pyglet.graphics.Batch();self.slots=[];self.images={};self.groups={}
        from pyglet.text.layout.base import layout_vertex_source,layout_fragment_source
        # Scale world glyphs on the GPU, preserving labels and glyph atlases during zoom.
        source=layout_vertex_source.replace('void main()', 'uniform float world_scale;\n    void main()').replace('vec4(position + view_translation + v_anchor, 1.0)', 'vec4((position + view_translation + v_anchor) * world_scale, 1.0)')
        self.world_text_program=pyglet.graphics.shader.ShaderProgram(pyglet.graphics.shader.Shader(source,'vertex'),pyglet.graphics.shader.Shader(layout_fragment_source,'fragment'))
    def texture(self,image,ox=0,oy=0):
        key=id(image),ox,oy
        if key not in self.images:
            data=pyglet.image.ImageData(image.width,image.height,'RGBA',image.pixels.tobytes(),pitch=-image.width*4)
            texture=data.get_texture();texture.anchor_x=ox;texture.anchor_y=image.height-oy
            self.images[key]=texture
        return self.images[key]
    def flatten(self,commands,dx=0,dy=0,layer=0):
        for cmd in commands:
            local=layer
            if cmd[0]=='layer':local=layer+cmd[1];cmd=cmd[2]
            if cmd[0]=='group':yield from self.flatten(cmd[1],dx+cmd[2],dy+cmd[3],local)
            else:yield cmd,dx,dy,local
    def draw(self,surface):
        h=self.window.height;available=defaultdict(list);active=[]
        for signature,obj in reversed(self.slots):available[signature].append(obj)
        world_scale=None
        for index,(cmd,dx,dy,layer) in enumerate(self.flatten(surface.commands)):
            kind=cmd[0]
            group=self.groups.get(layer)
            if group is None:group=pyglet.graphics.Group(order=layer);self.groups[layer]=group
            signature=(kind,layer)
            match kind:
                case 'rect'|'circle'|'ellipse':signature=(kind,layer,cmd[-1]>0)
                case 'text':signature=(kind,layer,cmd[1].font.family,cmd[1].font.size,cmd[1].font.bold,cmd[1].font.italic,cmd[1].font.world)
                case 'polygon':signature=(kind,layer,tuple(cmd[2]),dx,dy,h)
            obj=available[signature].pop() if available[signature] else None
            common=dict(batch=self.batch,group=group)
            match kind:
                case 'sprite'|'image':
                    image=cmd[1]
                    if kind=='sprite':
                        _,_,x,y,sx,sy,angle,color,alpha,ox,oy=cmd
                    else:
                        _,_,x,y,w,hh=cmd;sx=w/image.width;sy=hh/image.height;angle=0;color=(255,255,255);alpha=1;ox=oy=0
                    texture=self.texture(image,ox,oy)
                    if obj is None:obj=pyglet.sprite.Sprite(texture,subpixel=True,**common)
                    elif obj.image is not texture:obj.image=texture
                    if (obj.x,obj.y,obj.rotation,obj.scale_x,obj.scale_y)!=(x+dx,h-y-dy,-angle,sx,sy):obj.update(x=x+dx,y=h-y-dy,rotation=-angle,scale_x=sx,scale_y=sy)
                    if obj.color[:3]!=tuple(color[:3]):obj.color=color
                    opacity=round(255*alpha)
                    if obj.opacity!=opacity:obj.opacity=opacity
                case 'text':
                    _,text,x,y=cmd;f=text.font
                    if f.world and world_scale!=f.scale:
                        self.world_text_program['world_scale']=f.scale;world_scale=f.scale
                    if obj is None:obj=pyglet.text.Label(font_name=f.family,font_size=f.size*72/96,weight='bold' if f.bold else 'normal',italic=f.italic,anchor_y='top',program=self.world_text_program if f.world else None,**common)
                    if obj.text!=text.text:obj.text=text.text
                    if obj.x!=x+dx:obj.x=x+dx
                    if obj.y!=h-y-dy:obj.y=h-y-dy
                    color=(*text.color[:3],text.opacity)
                    if obj.color!=color:obj.color=color
                case 'rect':
                    _,color,r,width=cmd
                    if obj is None:obj=(shapes.Box(r.x+dx,h-r.bottom-dy,r.w,r.h,thickness=width,color=color,**common) if width else shapes.Rectangle(r.x+dx,h-r.bottom-dy,r.w,r.h,color=color,**common))
                    for attr,value in (('x',r.x+dx),('y',h-r.bottom-dy),('width',r.w),('height',r.h),('color',color)):
                        if getattr(obj,attr)!=value:setattr(obj,attr,value)
                    if width and obj.thickness!=width:obj.thickness=width
                case 'circle':
                    _,color,(x,y),radius,width=cmd
                    if obj is None:obj=(shapes.Arc(x+dx,h-y-dy,radius,thickness=width,color=color,**common) if width else shapes.Circle(x+dx,h-y-dy,radius,color=color,**common))
                    for attr,value in (('x',x+dx),('y',h-y-dy),('radius',radius),('color',color)):
                        if getattr(obj,attr)!=value:setattr(obj,attr,value)
                    if width and obj.thickness!=width:obj.thickness=width
                case 'line':
                    _,color,a,b,width=cmd
                    if obj is None:obj=shapes.Line(a[0]+dx,h-a[1]-dy,b[0]+dx,h-b[1]-dy,thickness=width,color=color,**common)
                    obj.x=a[0]+dx;obj.y=h-a[1]-dy;obj.x2=b[0]+dx;obj.y2=h-b[1]-dy;obj.thickness=width;obj.color=color
                case 'ellipse':
                    _,color,r,width=cmd
                    if obj is None:obj=shapes.Ellipse(r.centerx+dx,h-r.centery-dy,r.w/2,r.h/2,color=color,**common)
                    obj.x=r.centerx+dx;obj.y=h-r.centery-dy;obj.a=r.w/2;obj.b=r.h/2;obj.color=color
                case 'polygon':
                    _,color,points=cmd
                    if obj is None:obj=shapes.Polygon(*[(x+dx,h-y-dy) for x,y in points],color=color,**common)
                    obj.color=color
                case _:raise ValueError(kind)
            if not obj.visible:obj.visible=True
            active.append((signature,obj))
        cached=0
        for signature,objects in available.items():
            for obj in objects:
                if signature[0]=='polygon' or cached>=2048:obj.delete();continue
                if obj.visible:obj.visible=False
                active.append((signature,obj));cached+=1
        self.slots=active
        self.batch.draw()
    def close(self):
        for _,obj in self.slots:obj.delete()
        self.slots.clear()
