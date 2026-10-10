"""Room fade in simulation time, independent of rendering frequency."""
from dataclasses import dataclass


@dataclass
class Transition:
    target: int|str
    phase: str='out'
    alpha: float=0

    def step(self,dt):
        if self.phase=='out':
            self.alpha=min(1,self.alpha+.5*dt)
            if self.alpha>=1-1e-9:
                self.phase='in';self.alpha=1.25
                return 'switch'
        else:
            self.alpha=max(0,self.alpha-.5*dt)
            if self.alpha<=1e-9:return 'done'
        return None
