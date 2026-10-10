"""Read-only battle calculations on free-threaded Python; ordered results."""
from concurrent.futures import ThreadPoolExecutor
import math
import os
import sys
from .config import PARALLEL
from .spatial import SpatialTargets


def nearest_batch(enemies,targets):
    if isinstance(targets,SpatialTargets):return [targets.nearest((x,y,x,y))[0] for x,y in enemies]
    # Each worker owns its numeric copy, avoiding shared-object reference-count
    # contention in the hot loop of free-threaded CPython.
    local=[(x+0.0,y+0.0) for x,y in targets]
    result=[]
    for x,y in enemies:
        best=math.inf;selected=0
        for index,(tx,ty) in enumerate(local):
            dx=tx-x;dy=ty-y;distance=dx*dx+dy*dy
            if distance<best:best=distance;selected=index
        result.append(selected)
    return result


def gap_batch(actors,targets):
    if isinstance(targets,SpatialTargets):return [targets.gap(box) for box in actors]
    local=[tuple(value+0.0 for value in rect) for rect in targets]
    hypot=math.hypot;result=[]
    for left,top,right,bottom in actors:
        best=math.inf;best_dx=best_dy=0.
        for tl,tt,tr,tb in local:
            dx=max(0,left-tr,tl-right);dy=max(0,top-tb,tt-bottom)
            distance=dx*dx+dy*dy
            if distance<best:best=distance;best_dx=dx;best_dy=dy
        result.append(hypot(best_dx,best_dy) if local else math.inf)
    return result


class BattleWorkers:
    def __init__(self):
        self.enabled=hasattr(sys,'_is_gil_enabled') and not sys._is_gil_enabled()
        self.count=min(PARALLEL['max_workers'],os.cpu_count() or 1)
        self.pool=None;self.parallel_batches=0

    def nearest(self,enemies,targets):
        if len(targets)>=PARALLEL['spatial_minimum_targets'] and len(enemies)*len(targets)>=PARALLEL['spatial_minimum_pairs']:targets=SpatialTargets(targets,points=True)
        return self.calculate(nearest_batch,enemies,targets,PARALLEL['minimum_enemies'])

    def gaps(self,actors,targets):
        if len(targets)>=PARALLEL['spatial_minimum_targets'] and len(actors)*len(targets)>=PARALLEL['spatial_minimum_pairs']:targets=SpatialTargets(targets)
        return self.calculate(gap_batch,actors,targets,PARALLEL['minimum_units'])

    def calculate(self,function,enemies,targets,minimum):
        if not enemies or not targets:return []
        if not self.enabled or self.count<2 or len(enemies)<minimum or len(enemies)*len(targets)<PARALLEL['minimum_pairs']:
            return function(enemies,targets)
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=self.count,thread_name_prefix='drone-battle')
        size=math.ceil(len(enemies)/self.count)
        futures=[self.pool.submit(function,enemies[start:start+size],targets) for start in range(0,len(enemies),size)]
        self.parallel_batches+=1
        return [index for future in futures for index in future.result()]

    def close(self):
        if self.pool is not None:self.pool.shutdown(wait=True);self.pool=None
