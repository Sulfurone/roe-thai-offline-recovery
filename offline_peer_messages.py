"""Thai remote actor weapon and firing messages, original-codec checked."""
import math
import struct
from offline_weapons import WEAPONS


def uid(value):
    if type(value) is not int or not 0<value<2**64:raise ValueError('Invalid peer/item UID')


def peer_equipment(actor,weapon,template=10201,slot=1,magazine=30):
    uid(actor);uid(weapon)
    spec=WEAPONS.get(template)
    if (spec is None or slot not in spec.slots or type(magazine) is not int
            or not 0<=magazine<=spec.capacity):raise ValueError('Invalid remote loadout')
    # 547 is a compact remote-equipment record, not the own 5FB inventory.
    # Its order is template, item UID, slot, flag, bounded attachment rows,
    # seven attribute DWORDs and two opaque DWORDs. Row 7 carries loaded ammo.
    attributes=(30000 if 10401<=template<=10403 else 100000,0,0,0,20,spec.capacity,0)
    row=struct.pack('>IQIBI',template,weapon,slot,0,1)
    row+=struct.pack('>III',7,spec.ammunition,magazine)
    row+=struct.pack('>9I',*attributes,0,0)
    return 0x547,struct.pack('>QI',actor,1)+row+struct.pack('>IB',slot,0)


def peer_fire(actor,origin,target,stop=False):
    uid(actor)
    if (len(origin)!=3 or len(target)!=3 or type(stop) is not bool
            or any(not math.isfinite(v) or abs(v)>=2000000 for v in (*origin,*target))
            or math.dist(origin,target)<1):raise ValueError('Invalid peer shot')
    # 11D4: UID, origin XYZ floats, target XYZ floats, stop byte. The C2S
    # 11D3 extra DWORD is absent from this S2C counterpart.
    return 0x11d4,struct.pack('>Q6fB',actor,*origin,*target,int(stop))
