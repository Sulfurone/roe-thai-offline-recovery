"""Bounded original-Thai inventory transfers for supported firearms and ammunition.

Only the verified weapon/ammunition object variants are encoded. Unknown
items, external containers, use and world-drop operations are rejected.
"""
from dataclasses import dataclass,replace
import struct
from offline_weapons import WEAPONS,AMMUNITION,AMMO_STACK_MAX,is_weapon

WEAPON_TEMPLATE=10201
AMMO_TEMPLATE=30001
MAX_AMMO=AMMO_STACK_MAX
MAX_RESERVE=128*MAX_AMMO


@dataclass(frozen=True)
class Item:
    kind: int
    template: int
    uid: int
    count: int

    def wire(self):
        base=struct.pack('>BBIQIIBBIH',self.kind,0,self.template,self.uid,
                         self.count,0,0,0,0,0)
        extra=bytes(40) if self.kind==1 else (bytes(24) if self.kind==2 else (b'\0' if self.kind==0 else b''))
        return base+extra+bytes(4)


EMPTY=Item(0,0,0,0)


class OfflineInventory:
    def __init__(self,reserve=120):
        if type(reserve) is not int or not 0<=reserve<=MAX_AMMO:
            raise ValueError('Initial offline ammunition stack exceeds the original stack limit')
        self.items={(1,1):Item(1,WEAPON_TEMPLATE,0x100101,1)}
        if reserve:
            self.items[2,0]=Item(3,AMMO_TEMPLATE,0x100102,reserve)
        self.next_uid=0x100103
        # Loaded rounds per carried weapon uid; the original keeps one
        # magazine per gun, not per character.
        self.weapon_magazines={}

    @staticmethod
    def valid_slot(key):
        container,slot=key
        return (container==1 and slot in (1,2,3)) or (container==2 and 0<=slot<128)

    @classmethod
    def fits(cls,key,item):
        return cls.valid_slot(key) and (key[0]==2 or is_weapon(item) and key[1] in WEAPONS[item.template].slots)

    @property
    def reserve(self):
        return sum(item.count for (container,_),item in self.items.items()
                   if container==2 and item.kind==3)

    def reserve_for(self,template):
        return sum(item.count for (container,_),item in self.items.items()
                   if container==2 and item.kind==3 and item.template==template)

    def weapon(self):
        return next((item for item in self.items.values() if is_weapon(item)),None)

    def weapon_slot(self):
        return next((slot for (container,slot),item in self.items.items()
                     if container==1 and is_weapon(item)),None)

    def full_body(self):
        body=struct.pack('>I',len(self.items))
        for (container,slot),item in sorted(self.items.items()):
            body+=bytes((container,slot))+item.wire()
        return body+bytes(8)+b'\1'

    def delta(self,keys):
        keys=sorted(set(keys))
        if len(keys)>129 or any(not self.valid_slot(key) for key in keys):
            raise ValueError('Inventory delta exceeds the local slot bound')
        body=bytes((len(keys),))
        for container,slot in keys:
            body+=struct.pack('>HB',slot,container)+self.items.get((container,slot),EMPTY).wire()
        return 0x3e82,body+b'\1'

    @staticmethod
    def reply(command,error=0,template=0):
        return 0x3e81,struct.pack('>BIIB',command,error,template,1)

    def transfer(self,source,destination,quantity):
        item=self.items.get(source)
        target=self.items.get(destination)
        if (not self.valid_slot(source) or not self.valid_slot(destination)
                or item is None or not 0<quantity<=item.count
                or not self.fits(destination,item)):
            return [self.reply(1,1)]
        if source==destination:
            return [self.reply(1)]
        updated=dict(self.items)
        if target is None:
            if quantity==item.count:
                updated.pop(source)
                updated[destination]=item
            else:
                if self.next_uid>=2**64:
                    return [self.reply(1,1)]
                updated[source]=replace(item,count=item.count-quantity)
                updated[destination]=replace(item,count=quantity,uid=self.next_uid)
                self.next_uid+=1
        elif item.kind==target.kind==3 and item.template==target.template:
            if target.count+quantity>MAX_AMMO:
                return [self.reply(1,1)]
            updated[destination]=replace(target,count=target.count+quantity)
            if quantity==item.count:
                updated.pop(source)
            else:
                updated[source]=replace(item,count=item.count-quantity)
        elif quantity==item.count and self.fits(source,target):
            updated[source],updated[destination]=target,item
        else:
            return [self.reply(1,1)]
        self.items=updated
        # Apply the actual slot updates before acknowledging the operation.
        return [self.delta((source,destination)),self.reply(1,template=item.template)]

    def handle(self,body):
        if not body:
            return []
        command=body[0]
        if command!=1:
            return [self.reply(command,1)]
        if len(body) not in (10,18):
            return []
        command,src,src_slot,dst,dst_slot,quantity,current=struct.unpack('>BBHBHHB',body[:10])
        if current!=1:
            return [self.reply(1,1)]
        return self.transfer((src,src_slot),(dst,dst_slot),quantity)

    def consume(self,quantity,template=AMMO_TEMPLATE):
        if template not in AMMUNITION or not 0<=quantity<=self.reserve_for(template):
            raise ValueError('Not enough offline ammunition')
        changed=[]
        for key,item in sorted(list(self.items.items())):
            if not quantity:
                break
            if key[0]!=2 or item.kind!=3 or item.template!=template:
                continue
            used=min(quantity,item.count)
            quantity-=used
            changed.append(key)
            if used==item.count:
                del self.items[key]
            else:
                self.items[key]=replace(item,count=item.count-used)
        return self.delta(changed)

    def snapshot(self,magazine,selected_slot):
        return {'version':2,'magazine':magazine,'selected_slot':selected_slot,
                'next_uid':self.next_uid,'items':[
                    dict(container=key[0],slot=key[1],kind=item.kind,
                         template=item.template,uid=item.uid,count=item.count)
                    for key,item in sorted(self.items.items())],
                'weapon_magazines':[{'uid':uid,'magazine':count}
                                    for uid,count in sorted(self.weapon_magazines.items())]}

    @classmethod
    def restore(cls,data):
        fields={'version','magazine','selected_slot','next_uid','items'}
        if not isinstance(data,dict) or set(data) not in (fields,fields|{'weapon_magazines'}):
            raise ValueError('Unknown offline inventory profile schema')
        version=1 if set(data)==fields else 2
        if data['version']!=version:
            raise ValueError('Unknown offline inventory profile schema')
        for field,minimum,maximum in [('version',1,2),('magazine',0,max(s.capacity for s in WEAPONS.values())),
                                      ('selected_slot',0,6),('next_uid',1,2**64-1)]:
            if type(data[field]) is not int or not minimum<=data[field]<=maximum:
                raise ValueError(f'Invalid offline profile {field}')
        if not isinstance(data['items'],list) or len(data['items'])>129:
            raise ValueError('Too many offline inventory entries')
        inventory=cls(0)
        inventory.items={}
        inventory.next_uid=data['next_uid']
        uids=set()
        for row in data['items']:
            if not isinstance(row,dict) or set(row)!={'container','slot','kind','template','uid','count'}:
                raise ValueError('Unknown offline item schema')
            if any(type(value) is not int for value in row.values()):
                raise ValueError('Offline item fields must be integers')
            key=(row['container'],row['slot'])
            item=Item(row['kind'],row['template'],row['uid'],row['count'])
            if (not inventory.fits(key,item) or key in inventory.items
                    or not 0<item.uid<inventory.next_uid or item.uid in uids):
                raise ValueError('Invalid or duplicate offline item identity/slot')
            if not (is_weapon(item) or (item.kind==3 and item.template in AMMUNITION and 0<item.count<=MAX_AMMO)):
                raise ValueError('Unsupported offline item type/count')
            inventory.items[key]=item
            uids.add(item.uid)
        # Original carry limit: two long guns in slots 1/2 plus one pistol
        # in slot 3; further guns may only sit in the bag.
        weapons=[item for item in inventory.items.values() if is_weapon(item)]
        if (inventory.reserve>MAX_RESERVE or sum(item.kind==1 for item in weapons)>2
                or sum(item.kind==2 for item in weapons)>1):
            raise ValueError('Offline loadout exceeds its supported limits')
        if version==1:
            # v1 profiles carried a single gun whose magazine was global.
            weapon=next(iter(weapons),None)
            if weapon is not None:
                if data['magazine']>WEAPONS[weapon.template].capacity:
                    raise ValueError('Magazine exceeds this firearm capacity')
                inventory.weapon_magazines[weapon.uid]=data['magazine']
        else:
            weapon_by_uid={item.uid:item for item in weapons}
            for row in data['weapon_magazines']:
                if (not isinstance(row,dict) or set(row)!={'uid','magazine'}
                        or any(type(value) is not int for value in row.values())):
                    raise ValueError('Invalid offline weapon magazine entry')
                weapon=weapon_by_uid.get(row['uid'])
                if (weapon is None or not 0<=row['magazine']<=WEAPONS[weapon.template].capacity
                        or row['uid'] in inventory.weapon_magazines):
                    raise ValueError('Invalid or duplicate offline weapon magazine entry')
                inventory.weapon_magazines[row['uid']]=row['magazine']
            active=inventory.items.get((1,data['selected_slot']))
            expected=(inventory.weapon_magazines.get(active.uid,0)
                      if active is not None and is_weapon(active) else 0)
            if data['magazine']!=expected:
                raise ValueError('Saved magazine does not match the selected weapon')
        return inventory
