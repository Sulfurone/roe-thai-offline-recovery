"""Bounded original-Thai inventory transfers and a small equipment catalogue.

Known firearms/ammunition and whitelisted generic item variants are encoded.
External containers and item-use operations remain separate protocols.
Ground drop is implemented by offline_ground_loot.
"""
from dataclasses import dataclass,replace
import struct
from offline_weapons import WEAPONS,AMMUNITION,AMMO_STACK_MAX,is_weapon
from offline_items import EXTRA_ITEMS,is_extra
from offline_attachments import compatible

WEAPON_TEMPLATE=10201
AMMO_TEMPLATE=30001
MAX_AMMO=AMMO_STACK_MAX
MAX_RESERVE=128*MAX_AMMO


def stack_limit(item):
    return EXTRA_ITEMS[item.template].max_stack if is_extra(item) else MAX_AMMO if item.kind==3 and item.template in AMMUNITION else 1


def supported(item):
    base=is_weapon(item) or is_extra(item) or (item.kind==3 and item.template in AMMUNITION and 0<item.count<=MAX_AMMO)
    indices=[index for index,_ in item.parts]
    return (base and len(indices)<=7 and len(set(indices))==len(indices)
            and all(type(index) is int and 0<=index<7 and not part.parts
                    and compatible(item,part,index) for index,part in item.parts))


@dataclass(frozen=True)
class Item:
    kind: int
    template: int
    uid: int
    count: int
    parts: tuple = ()

    def wire(self):
        spec=EXTRA_ITEMS.get(self.template)
        # OBJECT_INFO's union tag is not ItemTable.mCategory. Armour uses
        # the unique-equipment branch whose first DWORD is current durability.
        # Medicines use the stack branch's leading ushort quantity.
        wire_kind=1 if self.kind==20 else 2 if self.kind==7 else self.kind
        base=struct.pack('>BBIQIIBBIH',wire_kind,0,self.template,self.uid,
                         self.count,0,0,0,0,0)
        # Native D6B220: DWORD, seven part template IDs (D85180),
        # bounded auxiliary array count, final DWORD. Keep opaque fields zero.
        installed=dict(self.parts)
        extra=(struct.pack('>10I',spec.durability if self.kind==20 and spec else 0,
                           *(installed[i].template if i in installed else 0 for i in range(7)),0,0)
               if wire_kind==1 else (struct.pack('>H',self.count if self.kind==7 else 0)+bytes(22)
               if wire_kind==2 else (b'\0' if wire_kind==0 else b'')))
        return base+extra+bytes(4)


EMPTY=Item(0,0,0,0)


def item_uids(item):
    return [item.uid]+[part.uid for _,part in item.parts]


def item_fields(item):
    row=dict(kind=item.kind,template=item.template,uid=item.uid,count=item.count)
    if item.parts:
        row['parts']=[dict(index=index,**item_fields(part)) for index,part in sorted(item.parts)]
    return row


def read_item(row,nested=False):
    fields={'kind','template','uid','count'}
    if (not isinstance(row,dict) or set(row) not in (fields,fields|{'parts'})
            or any(type(row[k]) is not int for k in fields)):
        raise ValueError('Unknown offline item schema')
    parts=row.get('parts',[])
    if nested and parts or not isinstance(parts,list) or len(parts)>7:
        raise ValueError('Invalid nested offline parts')
    decoded=[]
    for part in parts:
        if not isinstance(part,dict) or set(part)!=fields|{'index'} or type(part['index']) is not int:
            raise ValueError('Unknown installed part schema')
        decoded.append((part['index'],read_item({k:part[k] for k in fields},True)))
    item=Item(*(row[k] for k in ('kind','template','uid','count')),tuple(decoded))
    if not supported(item):
        raise ValueError('Unsupported offline item or installed part')
    return item


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
        return (container==1 and slot in (1,2,3,5,10,11,12)) or (container==2 and 0<=slot<128)

    @classmethod
    def fits(cls,key,item):
        return cls.valid_slot(key) and (key[0]==2
            or is_weapon(item) and key[1] in WEAPONS[item.template].slots
            or is_extra(item) and EXTRA_ITEMS[item.template].slot==key[1])

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
        # Original delta DTO has 128 native rows before its final owner flag.
        if len(keys)>128 or any(not self.valid_slot(key) for key in keys):
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
        elif item.kind==target.kind and item.template==target.template and stack_limit(item)>1:
            if target.count+quantity>stack_limit(item):
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
        if command==6:
            return self.transfer_part(body)
        if command!=1:
            return [self.reply(command,1)]
        if len(body) not in (10,18):
            return []
        command,src,src_slot,dst,dst_slot,quantity,current=struct.unpack('>BBHBHHB',body[:10])
        if current!=1:
            return [self.reply(1,1)]
        return self.transfer((src,src_slot),(dst,dst_slot),quantity)

    def transfer_part(self,body):
        if len(body) not in (26,34):
            return []
        command,source_uid,src,src_slot,target_uid,dst,dst_slot,quantity,current=struct.unpack('>BQBHQBHHB',body[:26])
        failure=[self.reply(6,1)]
        if current!=1 or quantity!=1 or src not in (1,2,3) or dst not in (1,2,3):
            return failure
        # Container 3 addresses a part index inside the weapon identified by
        # UID. Other containers address a real inventory slot plus its UID.
        source_key=(next((k for k,v in self.items.items() if v.uid==source_uid and is_weapon(v)),None)
                    if src==3 else (src,src_slot))
        source=self.items.get(source_key)
        part=(dict(source.parts).get(src_slot) if source is not None and src==3 else source)
        if (source is None or source.uid!=source_uid or part is None or part.kind!=4
                or not is_extra(part) or part.count!=1):
            return failure
        target_key=(next((k for k,v in self.items.items() if v.uid==target_uid and is_weapon(v)),None)
                    if dst==3 else (dst,dst_slot))
        target=self.items.get(target_key)
        if dst==3:
            if target is None or not compatible(target,part,dst_slot):
                return failure
            previous=dict(target.parts).get(dst_slot)
        else:
            # The native UI uses zero for an empty bag target UID.
            if (target_key is None or not self.fits(target_key,part)
                    or target is not None or target_uid!=0):
                return failure
            previous=None
        if source_key==target_key:
            return [self.reply(6)] if src==dst==3 and src_slot==dst_slot else failure
        if previous is not None and src==3 and not compatible(source,previous,src_slot):
            return failure
        updated=dict(self.items)
        if src==3:
            parts=dict(source.parts)
            if previous is None:parts.pop(src_slot)
            else:parts[src_slot]=previous
            updated[source_key]=replace(source,parts=tuple(sorted(parts.items())))
        elif previous is None:
            del updated[source_key]
        else:
            updated[source_key]=previous
        if dst==3:
            parts=dict(target.parts)
            parts[dst_slot]=part
            updated[target_key]=replace(target,parts=tuple(sorted(parts.items())))
        else:
            updated[target_key]=part
        self.items=updated
        return [self.delta((source_key,target_key)),self.reply(6,template=part.template)]

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
                    dict(container=key[0],slot=key[1],**item_fields(item))
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
        if not isinstance(data['items'],list) or len(data['items'])>135:
            raise ValueError('Too many offline inventory entries')
        inventory=cls(0)
        inventory.items={}
        inventory.next_uid=data['next_uid']
        uids=set()
        for row in data['items']:
            if not isinstance(row,dict) or set(row) not in ({'container','slot','kind','template','uid','count'},
                                                           {'container','slot','kind','template','uid','count','parts'}):
                raise ValueError('Unknown offline item schema')
            if any(type(row[k]) is not int for k in ('container','slot')):
                raise ValueError('Offline item fields must be integers')
            key=(row['container'],row['slot'])
            item=read_item({k:v for k,v in row.items() if k not in ('container','slot')})
            identities=item_uids(item)
            if (not inventory.fits(key,item) or key in inventory.items
                    or any(not 0<uid<inventory.next_uid or uid in uids for uid in identities)
                    or len(set(identities))!=len(identities)):
                raise ValueError('Invalid or duplicate offline item identity/slot')
            if not supported(item):
                raise ValueError('Unsupported offline item type/count')
            inventory.items[key]=item
            uids.update(identities)
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
