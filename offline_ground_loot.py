"""Finite original-Thai firearm and ammunition single-item ground loot.

The original 0x821 entity-type 1/subtype 2 is one ground item. Container
loot has a separate slot-list protocol and is deliberately not encoded here.
"""
from dataclasses import dataclass,replace
import math
import struct
from offline_inventory import Item,MAX_AMMO
from offline_weapons import WEAPONS,AMMUNITION,is_weapon

MAX_GROUND_STACKS=128
PICKUP_DISTANCE=500  # Original client EntityTable.m_nMaxOpDistance, cm (both supported items).


@dataclass(frozen=True)
class GroundStack:
    entity: int
    position: tuple
    item: Item
    magazine: int = 0

    def spawn(self):
        # DCAC50 common entity: config, UID, three NUL strings, XYZ+flag,
        # rotation, entity kind, kind-specific union, four bools, state, owners.
        name=(b'LocalM4A1\0' if self.item.template==10201 else b'LocalWeapon\0') if is_weapon(self.item) else b'LocalAmmo\0'
        body=struct.pack('>IQI',self.item.template,self.entity,len(name))+name
        body+=struct.pack('>I',1)+b'\0'+struct.pack('>I',1)+b'\0'
        body+=struct.pack('>3iBfI',*self.position,0,0.,1)
        body+=struct.pack('>IQB5I',0,0,2,self.item.template,self.item.count,self.entity,0,0)
        body+=bytes(4)+struct.pack('>IB',0,0)
        return 0x821,body


class OfflineGroundLoot:
    def __init__(self):
        self.stacks={}
        self.next_entity=0x400001
        self.announced=False

    def snapshot(self):
        return {'next_entity':self.next_entity,'stacks':[
            {'entity':stack.entity,'position':list(stack.position),'magazine':stack.magazine,
             'item':{'kind':stack.item.kind,'template':stack.item.template,
                     'uid':stack.item.uid,'count':stack.item.count}}
            for _,stack in sorted(self.stacks.items())]}

    @classmethod
    def restore(cls,data,inventory):
        if not isinstance(data,dict) or set(data)!={'next_entity','stacks'}:
            raise ValueError('Unknown ground-loot profile schema')
        if (type(data['next_entity']) is not int or not 0x400001<=data['next_entity']<=2**32
                or not isinstance(data['stacks'],list) or len(data['stacks'])>MAX_GROUND_STACKS):
            raise ValueError('Invalid ground entity allocator/count')
        world=cls()
        world.next_entity=data['next_entity']
        uids={item.uid for item in inventory.items.values()}
        for row in data['stacks']:
            if not isinstance(row,dict) or set(row) not in ({'entity','position','item'},
                                                          {'entity','position','item','magazine'}):
                raise ValueError('Unknown ground-stack schema')
            entity,position,fields=row['entity'],row['position'],row['item']
            if (type(entity) is not int or not 0x400001<=entity<world.next_entity
                    or entity in world.stacks or not isinstance(position,list) or len(position)!=3
                    or any(type(x) is not int or abs(x)>=2000000 for x in position)
                    or not isinstance(fields,dict) or set(fields)!={'kind','template','uid','count'}
                    or any(type(x) is not int for x in fields.values())):
                raise ValueError('Invalid ground identity/position/item fields')
            item=Item(**fields)
            magazine=row.get('magazine',0)
            if (not cls.supported(item) or type(magazine) is not int or magazine<0
                    or is_weapon(item) and (magazine>WEAPONS[item.template].capacity or 'magazine' not in row)
                    or not is_weapon(item) and magazine!=0
                    or not 0<item.uid<inventory.next_uid or item.uid in uids):
                raise ValueError('Unsupported or duplicate ground item/magazine')
            world.stacks[entity]=GroundStack(entity,tuple(position),item,magazine)
            uids.add(item.uid)
        return world

    @staticmethod
    def supported(item):
        return (item.kind==3 and item.template in AMMUNITION and 0<item.count<=MAX_AMMO) or is_weapon(item)

    @staticmethod
    def error(entity):
        # Kind 1 requires the additional entity DWORD after the error.
        return [(0x3b66,struct.pack('>BII',1,1,entity))]

    def add(self,item,position,magazine=0):
        if (not self.supported(item) or type(magazine) is not int or magazine<0
                or is_weapon(item) and magazine>WEAPONS[item.template].capacity
                or not is_weapon(item) and magazine!=0
                or len(self.stacks)>=MAX_GROUND_STACKS or self.next_entity>=2**32
                or len(position)!=3 or any(type(x) is not int or abs(x)>=2000000 for x in position)):
            raise ValueError('Unsupported or out-of-bounds ground item/magazine')
        stack=GroundStack(self.next_entity,tuple(position),item,magazine)
        self.next_entity+=1
        self.stacks[stack.entity]=stack
        return stack

    def announce(self):
        if self.announced:
            return []
        self.announced=True
        return [stack.spawn() for stack in self.stacks.values()]

    def pickup(self,body,inventory,actor_uid,player_position,can_interact):
        if len(body) not in (33,41):
            return []
        entity,slot,owner,container,destination,automatic,*camera=struct.unpack('>IIQBHB3iB',body[:33])
        stack=self.stacks.get(entity)
        if (not can_interact or not self.announced or stack is None or slot not in (0,0xffffffff)
                or automatic not in (0,1) or owner not in (0,actor_uid)
                or math.dist(player_position,stack.position)>PICKUP_DISTANCE
                or is_weapon(stack.item) and inventory.weapon() is not None):
            return self.error(entity)
        if automatic:
            key=next(((1,i) for i in WEAPONS[stack.item.template].slots if (1,i) not in inventory.items),None) if is_weapon(stack.item) else next((key for key,item in sorted(inventory.items.items())
                      if key[0]==2 and item.kind==3 and item.template==stack.item.template and item.count+stack.item.count<=MAX_AMMO),None)
            if key is None:
                key=next(((2,i) for i in range(128) if (2,i) not in inventory.items),None)
        else:
            key=(container,destination)
        if key is None or not inventory.fits(key,stack.item):
            return self.error(entity)
        target=inventory.items.get(key)
        if target is not None and (stack.item.kind!=3 or target.kind!=3 or target.template!=stack.item.template
                                   or target.count+stack.item.count>MAX_AMMO):
            return self.error(entity)
        inventory.items[key]=(replace(target,count=target.count+stack.item.count) if target else stack.item)
        inventory.next_uid=max(inventory.next_uid,stack.item.uid+1)
        del self.stacks[entity]
        # Apply the bag delta, remove the entire single-item entity, then
        # emit the original pickup-template/count sound notification.
        notice=struct.pack('>IIBII',entity,slot,stack.item.kind,stack.item.template,stack.item.count)
        if is_weapon(stack.item):
            notice+=bytes(4)  # Original kind 1/2 union has three DWORDs.
        return [inventory.delta([key]),(0x82b,struct.pack('>Q',entity)),(0x3b64,notice)]

    def drop(self,body,inventory,actor_uid,player_position,can_interact,magazine=0):
        if len(body) not in (15,23):
            return []
        command,container,slot,quantity,owner,current=struct.unpack('>BBHHQB',body[:15])
        key=(container,slot)
        item=inventory.items.get(key)
        # Original UI 0x13D74EE sends quantity zero when dropping a whole
        # item. The client's live M4A1 drop uses exactly this form.
        if item is not None and quantity==0:
            quantity=item.count
        if (command!=2 or current!=1 or not can_interact or not inventory.valid_slot(key)
                or owner not in (0,actor_uid) or item is None or not self.supported(item)
                or not 0<quantity<=item.count or len(self.stacks)>=MAX_GROUND_STACKS
                or self.next_entity>=2**32 or inventory.next_uid>=2**64-1):
            return [inventory.reply(2,1)]
        # The owning gameplay session commits inventory and world together
        # before sending any acknowledgement when world persistence is used.
        dropped=item if quantity==item.count else replace(item,count=quantity,uid=inventory.next_uid)
        stack=self.add(dropped,tuple(player_position),magazine if is_weapon(item) else 0)
        if quantity==item.count:
            del inventory.items[key]
        else:
            inventory.next_uid+=1
            inventory.items[key]=replace(item,count=item.count-quantity)
        return [stack.spawn(),inventory.delta([key]),inventory.reply(2,template=item.template)]
