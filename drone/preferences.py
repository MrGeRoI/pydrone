"""Persistent display and audio preferences, independent of checkpoints."""
import json
from pathlib import Path

from .paths import SAVE_DIR

SETTINGS_PATH=SAVE_DIR/'settings.json'

class Preferences:
    def __init__(self,path=SETTINGS_PATH):
        self.path=Path(path);self.sound=True;self.music=True;self.fullscreen=False;self.size=(1440,900)
        self.language='english';self.theme='silver';self.volume=.5;self.music_volume=.5;self.ui_scale=1.;self.vsync=True;self.minimap=True;self.camera_shake=True
        self.difficulty=1;self.world_zoom=1.;data={}
        try:
            data=json.loads(self.path.read_text(encoding='utf8'))
            for name in ('sound','music','fullscreen','vsync','minimap','camera_shake'):
                if type(data.get(name)) is bool:setattr(self,name,data[name])
            size=data.get('size')
            if isinstance(size,list) and len(size)==2 and all(type(v) is int and 320<=v<=16384 for v in size):self.size=tuple(size)
            for name in ('language','theme'):
                if isinstance(data.get(name),str):setattr(self,name,data[name])
            for name in ('volume','music_volume'):
                if type(data.get(name)) in (int,float) and 0<=data[name]<=1:setattr(self,name,data[name])
            if data.get('ui_scale') in (.75,1,1.25):self.ui_scale=data['ui_scale']
            if type(data.get('difficulty')) is int and data['difficulty'] in (0,1,2):self.difficulty=data['difficulty']
            if type(data.get('world_zoom')) in (int,float) and .5<=data['world_zoom']<=2:self.world_zoom=data['world_zoom']
        except (OSError,ValueError,TypeError):pass
        if not self.sound:self.volume=0
        if not self.music:self.music_volume=0
        self.migrate_profile_settings(data)

    def migrate_profile_settings(self,settings):
        profile_path=self.path.with_name('profile.json')
        try:
            profile=json.loads(profile_path.read_text(encoding='utf8'))
            legacy={key:profile[key] for key in ('difficulty','world_zoom') if key in profile}
            if not legacy:return
            for key,value in legacy.items():
                valid=(type(value) is int and value in (0,1,2)) if key=='difficulty' else (type(value) in (int,float) and .5<=value<=2)
                if key not in settings and valid:setattr(self,key,value)
            # Persist settings before removing anything from the old profile.
            self.save()
            for key in legacy:profile.pop(key)
            temporary=profile_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(profile,indent=2),encoding='utf8');temporary.replace(profile_path)
        except (OSError,ValueError,TypeError,AttributeError):pass

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({name:getattr(self,name) for name in ('sound','music','fullscreen','size','language','theme','volume','music_volume','ui_scale','vsync','minimap','camera_shake','difficulty','world_zoom')}),encoding='utf8')
        temporary.replace(self.path)
