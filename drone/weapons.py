"""Player inventory with compatibility accessors for existing checkpoints."""
from dataclasses import dataclass

WEAPON_NAMES=('axe','pistol','shotgun','machinegun','pipebomb','railgun','flamethrower','repair','rpg','minigun')


@dataclass
class WeaponState:
    owned: bool=False
    enabled: bool=False
    ammo: int=0
    charge: float=0
    cooldown: float=0
    ammo_peak: int=0
    low_ammo_notified: bool=False


class WeaponInventory:
    def owns(self,name):return name in self.weapons and self.weapons[name].owned

    @property
    def has_weapons(self):return any(state.owned for name,state in self.weapons.items() if name!='repair')

    def equip(self,name):
        if not self.owns(name):return False
        self.weapons[name].enabled=True
        self.weapon=name;self.equipped=True
        self.weapons[name].ammo_peak=self.weapons[name].ammo
        self.weapons[name].low_ammo_notified=False
        return True

    def unequip(self,name):
        if name not in self.weapons:return False
        self.weapons[name].enabled=False
        if self.weapon==name:
            self.equipped=False
            start=WEAPON_NAMES.index(name)
            for offset in range(1,len(WEAPON_NAMES)):
                other=WEAPON_NAMES[(start+offset)%len(WEAPON_NAMES)]
                if self.owns(other) and self.weapons[other].enabled:self.equip(other);break
        return True

    def buy_weapon(self,name):
        if name not in self.weapons or self.owns(name):return False
        cost=self.data[name]['price']
        if not getattr(self,'free_buy',False) and self.money<cost:self.events.append('AccessDenied');return False
        if not getattr(self,'free_buy',False):self.money-=cost
        self.weapons[name].owned=True
        self.events.append('Pickup')
        return self.equip(name)

    def buy_ammo(self,name=None):
        name=name or self.weapon
        if not self.owns(name):return False
        cfg=self.data.get(name,{})
        if 'ammo_price' not in cfg or not getattr(self,'free_buy',False) and self.money<cfg['ammo_price']:self.events.append('AccessDenied');return False
        if not getattr(self,'free_buy',False):self.money-=cfg['ammo_price']
        self.weapons[name].ammo+=cfg['ammo_pack']
        self.weapons[name].ammo_peak=self.weapons[name].ammo
        self.weapons[name].low_ammo_notified=False
        self.events.append('Pickup')
        return True


def state_property(name,field):
    return property(lambda self:getattr(self.weapons[name],field),lambda self,value:setattr(self.weapons[name],field,value))


# Legacy names remain usable by firing code and version 1/2 checkpoints;
# all inventory values themselves live only in the weapons dictionary.
for name in WEAPON_NAMES:
    if name=='repair':continue
    for field in ('owned','ammo','charge','cooldown'):
        alias=field if name=='pistol' and field in ('owned','ammo') else name+'_'+field
        setattr(WeaponInventory,alias,state_property(name,field))
    setattr(WeaponInventory,'buy_'+name,lambda self,name=name:self.buy_weapon(name))

WeaponInventory.repair_owned=state_property('repair','owned')
