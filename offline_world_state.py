"""Atomic local profile containing both inventory and finite ground loot."""
import json
import os
from pathlib import Path
from offline_inventory import OfflineInventory
from offline_ground_loot import OfflineGroundLoot
from offline_weapons import is_weapon

MAX_WORLD_BYTES=128*1024


def snapshot(inventory,ground,magazine,selected_slot):
    return {'format':'roe-thai-offline-world','version':2,'map_id':16006,
            'inventory':inventory.snapshot(magazine,selected_slot),'ground':ground.snapshot()}


def restore(data):
    if (not isinstance(data,dict) or set(data)!={'format','version','map_id','inventory','ground'}
            or data['format']!='roe-thai-offline-world' or type(data['version']) is not int
            or data['version'] not in (1,2) or type(data['map_id']) is not int or data['map_id']!=16006):
        raise ValueError('Unknown Thai offline world profile format/version/map')
    inventory=OfflineInventory.restore(data['inventory'])
    ground=OfflineGroundLoot.restore(data['ground'],inventory)
    if not any(is_weapon(x) for x in inventory.items.values()) and data['inventory']['magazine']!=0:
        raise ValueError('Magazine cannot remain in inventory when its weapon is on the ground')
    return inventory,ground,data['inventory']['magazine'],data['inventory']['selected_slot']


def read(path):
    path=Path(path)
    if path.stat().st_size>MAX_WORLD_BYTES:
        raise ValueError('Offline world profile exceeds 128 KiB')
    return restore(json.loads(path.read_text(encoding='utf-8')))


def write_atomic(path,payload):
    encoded=payload.encode('utf-8')
    if len(encoded)>MAX_WORLD_BYTES:
        raise ValueError('Offline profile exceeds its write bound')
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('wb') as destination:
        destination.write(encoded)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)
