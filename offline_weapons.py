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

# WeaponInfo suffix +444/+448 and WeaponParams +1E8; original float32 values.
RELOAD_TIMINGS={
    10101:(3.1700000762939453,1.0,0),
    10102:(3.4000000953674316,1.0,0),
    10103:(3.1700000762939453,1.0,0),
    10104:(2.130000114440918,1.0,0),
    10105:(2.6700000762939453,1.0,0),
    10201:(1.899999976158142,1.0,0),
    10202:(2.25,1.0,0),
    10203:(1.5,1.0,0),
    10204:(1.600000023841858,1.0,0),
    10205:(2.25,1.0,0),
    10207:(1.7000000476837158,1.0,0),
    10301:(1.899999976158142,1.0,0),
    10302:(1.9333300590515137,1.0,0),
    10303:(1.399999976158142,1.0,0),
    10401:(1.2599999904632568,0.699999988079071,1),
    10402:(1.9700000286102295,1.0,0),
    10403:(1.6299999952316284,1.0,0),
    20001:(1.2699999809265137,1.0,0),
    20002:(1.2699999809265137,1.0,0),
    20003:(1.899999976158142,1.0,0),
}


def reload_duration(template,amount):
    spec=WEAPONS[template]
    if type(amount) is not int or not 1<=amount<=spec.capacity:
        raise ValueError("Reload transfer must fit the firearm capacity")
    base,extra,mode=RELOAD_TIMINGS[template]
    # Original 12D6466..12D64A1: type 1 adds time for each further shell.
    return base+(amount-1)*extra if mode==1 else base
