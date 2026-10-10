"""Persistent campaign progress, separate from a rewindable combat checkpoint."""
from dataclasses import dataclass,field
import json
from pathlib import Path

from .paths import SAVE_DIR

PROFILE_PATH=SAVE_DIR/'profile.json'
ARENA_SUFFIXES={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six'}


@dataclass
class Profile:
    arena_one_cleared: bool=False
    no_weapons_one: bool=False
    path: Path=field(default=PROFILE_PATH,repr=False)
    no_structures_one: bool=False
    arena_two_cleared: bool=False
    no_weapons_two: bool=False
    no_structures_two: bool=False
    arena_three_cleared: bool=False
    no_weapons_three: bool=False
    no_structures_three: bool=False
    arena_four_cleared: bool=False
    no_weapons_four: bool=False
    no_structures_four: bool=False
    arena_five_cleared: bool=False
    no_weapons_five: bool=False
    no_structures_five: bool=False
    arena_six_cleared: bool=False
    no_weapons_six: bool=False
    no_structures_six: bool=False
    tutorial_complete: bool=False

    def cleared(self,arena):
        return getattr(self,f'arena_{ARENA_SUFFIXES[arena]}_cleared')

    @classmethod
    def load(cls,path=PROFILE_PATH):
        path=Path(path)
        if not path.exists():return cls(path=path)
        data=json.loads(path.read_text(encoding='utf8'))
        if data.get('version')!=1:raise ValueError('Invalid profile')
        if any(type(data.get(key)) is not bool for key in ('arena_one_cleared','no_weapons_one')):raise ValueError('Invalid profile')
        if type(data.get('no_structures_one',False)) is not bool:raise ValueError('Invalid profile')
        second={key:data.get(key,False) for suffix in tuple(ARENA_SUFFIXES.values())[1:] for key in (f'arena_{suffix}_cleared',f'no_weapons_{suffix}',f'no_structures_{suffix}')}
        second['tutorial_complete']=data.get('tutorial_complete',False)
        if any(type(value) is not bool for value in second.values()):raise ValueError('Invalid profile')
        return cls(arena_one_cleared=data['arena_one_cleared'],no_weapons_one=data['no_weapons_one'],path=path,no_structures_one=data.get('no_structures_one',False),**second)

    def save(self):
        data={'version':1,'arena_one_cleared':self.arena_one_cleared,'no_weapons_one':self.no_weapons_one,'no_structures_one':self.no_structures_one}
        data.update({key:getattr(self,key) for suffix in tuple(ARENA_SUFFIXES.values())[1:] for key in (f'arena_{suffix}_cleared',f'no_weapons_{suffix}',f'no_structures_{suffix}')})
        data['tutorial_complete']=self.tutorial_complete
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,indent=2),encoding='utf8');temporary.replace(self.path)

    def victory(self,owned_weapon,practice=False,structures_built=None,arena=1):
        if practice:return False
        if arena not in ARENA_SUFFIXES:raise ValueError('Invalid arena')
        suffix=ARENA_SUFFIXES[arena]
        keys=(f'arena_{suffix}_cleared',f'no_weapons_{suffix}',f'no_structures_{suffix}')
        old=tuple(getattr(self,key) for key in keys)
        setattr(self,keys[0],True)
        setattr(self,keys[1],getattr(self,keys[1]) or not owned_weapon)
        setattr(self,keys[2],getattr(self,keys[2]) or structures_built==0)
        try:self.save()
        except OSError:
            for key,value in zip(keys,old):setattr(self,key,value)
            raise
        return True
