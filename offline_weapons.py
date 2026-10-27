"""Original Thai firearm capacities, ammunition and equipment categories.

Source: QSWeaponConfigTable v14 WeaponInfo/Params prefixes joined with the
fully decoded ItemTable and EntityTable. Recoil, damage and attachments are
not inferred from this small subset; see probes/extract_weapon_stat_prefixes.py.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class WeaponSpec:
    kind: int
    capacity: int
    ammunition: int
    slots: tuple

WEAPONS={ident:WeaponSpec(kind,capacity,ammo,(1,2) if kind==1 else (3,))
    for ident,kind,capacity,ammo in (
        (10101,1,5,30001),(10102,1,5,30002),(10103,1,5,30002),
        (10104,1,10,30002),(10105,1,5,30006),
        (10201,1,30,30001),(10202,1,30,30002),(10203,1,30,30002),
        (10204,1,30,30001),(10205,1,30,30002),(10207,1,30,30001),
        (10301,1,30,30003),(10302,1,25,30003),(10303,1,15,30005),
        (10401,1,5,30004),(10402,1,2,30004),(10403,1,5,30004),
        (20001,2,12,30005),(20002,2,17,30003),(20003,2,7,30006))}
AMMUNITION=frozenset(spec.ammunition for spec in WEAPONS.values())
AMMO_STACK_MAX=999  # Original ItemTable nPackMax for these ammunition items.

def is_weapon(item):
    spec=WEAPONS.get(item.template)
    return spec is not None and item.kind==spec.kind and item.count==1
