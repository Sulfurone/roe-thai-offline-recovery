"""Finite original-Thai firearm, ammunition and equipment ground loot.

The original 0x821 entity-type 1/subtype 2 is one ground item. Container
loot has a separate slot-list protocol and is deliberately not encoded here.
"""
from dataclasses import dataclass,replace
import math
import struct
from offline_inventory import Item,MAX_AMMO,supported,stack_limit,item_fields,read_item,item_uids
from offline_weapons import WEAPONS,AMMUNITION,is_weapon
from offline_items import EXTRA_ITEMS,is_extra

# Server working-set bound for independent 0x821 entities. This is unrelated
# to the original inventory delta's fixed 128-row array.
MAX_GROUND_STACKS=512
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
        self.last_rejection=None

    def snapshot(self):
        return {'next_entity':self.next_entity,'stacks':[
            {'entity':stack.entity,'position':list(stack.position),'magazine':stack.magazine,
             'item':item_fields(stack.item)}
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
        uids={uid for item in inventory.items.values() for uid in item_uids(item)}
        for row in data['stacks']:
            if not isinstance(row,dict) or set(row) not in ({'entity','position','item'},
                                                          {'entity','position','item','magazine'}):
                raise ValueError('Unknown ground-stack schema')
            entity,position,fields=row['entity'],row['position'],row['item']
            if (type(entity) is not int or not 0x400001<=entity<world.next_entity
                    or entity in world.stacks or not isinstance(position,list) or len(position)!=3
                    or any(type(x) is not int or abs(x)>=2000000 for x in position)
                    or not isinstance(fields,dict)):
                raise ValueError('Invalid ground identity/position/item fields')
            item=read_item(fields)
            identities=item_uids(item)
            magazine=row.get('magazine',0)
            if (not cls.supported(item) or type(magazine) is not int or magazine<0
                    or is_weapon(item) and (magazine>WEAPONS[item.template].capacity or 'magazine' not in row)
                    or not is_weapon(item) and magazine!=0
                    or any(not 0<uid<inventory.next_uid or uid in uids for uid in identities)
                    or len(set(identities))!=len(identities)):
                raise ValueError('Unsupported or duplicate ground item/magazine')
            world.stacks[entity]=GroundStack(entity,tuple(position),item,magazine)
            uids.update(identities)
        return world

    @staticmethod
    def supported(item):
        return supported(item)

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
        self.last_rejection=None
        if len(body) not in (33,41):
            self.last_rejection={'reason':'length'}
            return []
        entity,slot,owner,container,destination,automatic,*camera=struct.unpack('>IIQBHB3iB',body[:33])
        stack=self.stacks.get(entity)
        actor_distance=math.dist(player_position,stack.position) if stack else math.inf
        request_camera=tuple(camera[:3])
        camera_distance=(math.dist(request_camera,stack.position) if stack and any(request_camera)
            and all(abs(v)<2000000 for v in request_camera) else math.inf)
        # The original sender includes the live camera position (535000+38).
        # Walking command keyframes can lag behind it. Retain the original
        # 500 cm range and accept either independently bounded viewpoint.
        nearby=min(actor_distance,camera_distance)<=PICKUP_DISTANCE
        if (not can_interact or not self.announced or stack is None or slot not in (0,0xffffffff)
                or automatic not in (0,1) or owner not in (0,actor_uid)
                or not nearby):
            self.last_rejection={'reason':'distance' if stack and not nearby else 'identity_or_state',
                'entity':entity,'actor_distance_cm':round(actor_distance) if math.isfinite(actor_distance) else None,
                'camera_distance_cm':round(camera_distance) if math.isfinite(camera_distance) else None}
            return self.error(entity)
        if automatic:
            equip=(WEAPONS[stack.item.template].slots if is_weapon(stack.item) else
                   (EXTRA_ITEMS[stack.item.template].slot,) if is_extra(stack.item) and EXTRA_ITEMS[stack.item.template].slot else ())
            key=next(((1,i) for i in equip if (1,i) not in inventory.items),None)
            if key is None and stack_limit(stack.item)>1:
                key=next((key for key,item in sorted(inventory.items.items())
                          if item.kind==stack.item.kind and item.template==stack.item.template
                          and item.count+stack.item.count<=stack_limit(stack.item)),None)
            if key is None:
                key=next(((2,i) for i in range(128) if (2,i) not in inventory.items),None)
        else:
            key=(container,destination)
        if key is None or not inventory.fits(key,stack.item):
            self.last_rejection={'reason':'destination_or_capacity','entity':entity}
            return self.error(entity)
        target=inventory.items.get(key)
        if target is not None and (stack_limit(stack.item)<=1 or target.kind!=stack.item.kind or target.template!=stack.item.template
                                   or target.count+stack.item.count>stack_limit(stack.item)):
            self.last_rejection={'reason':'occupied_or_full','entity':entity}
            return self.error(entity)
        inventory.items[key]=(replace(target,count=target.count+stack.item.count) if target else stack.item)
        inventory.next_uid=max(inventory.next_uid,stack.item.uid+1)
        del self.stacks[entity]
        # Apply the bag delta, remove the entire single-item entity, then
        # emit the original pickup-template/count sound notification.
        notice=struct.pack('>IIBII',entity,slot,stack.item.kind if is_weapon(stack.item) else 3,stack.item.template,stack.item.count)
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
