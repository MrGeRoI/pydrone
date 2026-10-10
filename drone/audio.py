"""Original WAV playback through pyglet; only the main thread owns players."""
import pyglet
import weakref

def _release_players(players,loops,sounds):
    # Retain players until the audio driver has detached its worker callbacks.
    for player in [*loops.values(),*players]:player.delete()
    loops.clear();players.clear();sounds.clear()

class Audio:
    def __init__(self,assets):
        self.assets=assets;self.cache={};self.muted=False;self.music_enabled=True;self.loops={};self.players=set();self.volume=.5;self.music_volume=.5;self.player_sounds={}
        self.finalizer=weakref.finalize(self,_release_players,self.players,self.loops,self.player_sounds)
    def source(self,name):
        if name=='Music01':
            definition=self.assets.manifest['sounds'].get(name)
            if not definition:return None
            try:return pyglet.media.load(str(self.assets.root/definition['file']),streaming=True)
            except (OSError,pyglet.media.MediaException):return None
        if name not in self.cache:
            definition=self.assets.manifest['sounds'].get(name)
            if not definition:return None
            try:self.cache[name]=pyglet.media.load(str(self.assets.root/definition['file']),streaming=False)
            except (OSError,pyglet.media.MediaException):return None
        return self.cache[name]
    def stop(self):
        _release_players(self.players,self.loops,self.player_sounds)
    def loop(self,name,active):
        if not active or (not self.music_enabled if name=='Music01' else self.muted):
            player=self.loops.pop(name,None)
            if player:player.delete()
            return
        if name in self.loops:return
        source=self.source(name)
        if source:
            player=pyglet.media.Player();player.volume=(self.music_volume if name=='Music01' else self.volume)*self.assets.manifest['sounds'][name]['volume'];player.queue(source);player.loop=True;player.play();self.loops[name]=player
    def play(self,name):
        if self.muted:return
        source=self.source(name)
        if source:
            player=pyglet.media.Player()
            player.volume=self.volume*self.assets.manifest['sounds'][name]['volume']
            player_ref=weakref.ref(player);audio_ref=weakref.ref(self)
            def finished():
                player=player_ref();audio=audio_ref()
                if player is None:return
                if audio is not None:audio.players.discard(player);audio.player_sounds.pop(player,None)
                player.delete()
            player.push_handlers(on_player_eos=finished)
            self.players.add(player);self.player_sounds[player]=name
            player.queue(source);player.play()

    def refresh_volumes(self):
        for name,player in self.loops.items():
            volume=self.music_volume if name=='Music01' else 0 if self.muted else self.volume
            player.volume=volume*self.assets.manifest['sounds'][name]['volume']
        for player,name in self.player_sounds.items():
            player.volume=(0 if self.muted else self.volume)*self.assets.manifest['sounds'][name]['volume']
