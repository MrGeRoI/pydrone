"""Exact nearest point/rectangle queries over an immutable bounding tree."""
import math


def squared_gap(a,b):
    dx=max(0,a[0]-b[2],b[0]-a[2]);dy=max(0,a[1]-b[3],b[1]-a[3])
    return dx*dx+dy*dy


class SpatialTargets:
    def __init__(self,targets,points=False):
        boxes=tuple((x,y,x,y) for x,y in targets) if points else tuple(tuple(box) for box in targets)
        self.root=self.build(tuple(enumerate(boxes)))
        self.boxes=boxes
        self.count=len(boxes)

    def __len__(self):return self.count

    @classmethod
    def build(cls,items):
        box=(min(b[0] for _,b in items),min(b[1] for _,b in items),max(b[2] for _,b in items),max(b[3] for _,b in items))
        first=min(index for index,_ in items)
        if len(items)<=8:return box,None,None,items,first
        axis=0 if box[2]-box[0]>=box[3]-box[1] else 1
        ordered=sorted(items,key=lambda item:item[1][axis]+item[1][axis+2]);middle=len(ordered)//2
        return box,cls.build(ordered[:middle]),cls.build(ordered[middle:]),None,first

    def nearest(self,box):
        best=math.inf;selected=math.inf;stack=[(0,self.root)]
        while stack:
            lower,node=stack.pop()
            if lower>best or lower==best and node[4]>=selected:continue
            _,left,right,items,_=node
            if items is not None:
                for index,target in items:
                    distance=squared_gap(box,target)
                    if distance<best or distance==best and index<selected:best=distance;selected=index
            else:
                dl=squared_gap(box,left[0]);dr=squared_gap(box,right[0])
                # Visit the closer subtree first to prune the other one early.
                if dl<dr:stack.extend(((dr,right),(dl,left)))
                else:stack.extend(((dl,left),(dr,right)))
        return selected,best

    def gap(self,box):
        index,_=self.nearest(box);target=self.boxes[index]
        return math.hypot(max(0,box[0]-target[2],target[0]-box[2]),max(0,box[1]-target[3],target[1]-box[3]))
