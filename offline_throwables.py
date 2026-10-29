"""Original Thai throw handshake; physics/effects remain in the client.

No damage is accepted from the client-supplied affected-actor list. Full blast
occlusion, armour damage and flash blindness are separate work.
"""
from dataclasses import dataclass,field,replace
import struct
import time
from offline_items import EXTRA_ITEMS


def throwable(template):
    return template in EXTRA_ITEMS and EXTRA_ITEMS[template].kind==5


@dataclass
class Throws:
    active: dict = field(default_factory=dict)
    last_completion: dict | None = field(default=None,init=False)

    def take_completion(self):
        event,self.last_completion=self.last_completion,None
        return event

    def handle(self,message,body,inventory,actor_uid,allowed,now=None,reference_position=None):
        now=time.monotonic() if now is None else now
        self.last_completion=None
        # Keep completed receipts for retransmissions; cap all live receipts.
        self.active={k:v for k,v in self.active.items() if now-v['at']<120}
        if message==0x1004:
            # Real Thai C2S applications can append eight transport fields.
            # Keep them opaque and outside the logical request/receipt key.
            if len(body) not in (51,59):return []
            body=body[:51]
            template=struct.unpack_from('>I',body)[0]
            serial=struct.unpack_from('>I',body,43)[0]
            ack=lambda error:(0x1005,struct.pack('>3I',template,serial,error))
            key=serial
            previous=self.active.get(key)
            if previous is not None:
                return [ack(0 if previous['body']==body else 1)]
            position=struct.unpack_from('>3i',body,4)
            if (not allowed or inventory is None or not throwable(template)
                    or len(self.active)>=256 or any(abs(x)>=2000000 for x in position)
                    or any(body[i] for i in (16,29,42))):return [ack(1)]
            # The request identifies a template, not a carried object UID.
            # Prefer its equipped stack, then the first matching bag stack.
            source=next((k for k,item in sorted(inventory.items.items())
                         if item.template==template and item.kind==5 and item.count>0),None)
            if source is None:return [ack(1)]
            item=inventory.items[source]
            if item.count==1:del inventory.items[source]
            else:inventory.items[source]=replace(item,count=item.count-1)
            self.active[key]=dict(at=now,body=body,finished=False,
                                  reference=tuple(reference_position) if reference_position is not None else None)
            return [ack(0),inventory.delta([source])]
        if message==0x1007:
            if len(body)<25:return []
            template,count=struct.unpack_from('>II',body)
            if count>120 or len(body) not in (25+8*count,33+8*count):return []
            offset=8+8*count
            position=struct.unpack_from('>3i',body,offset)
            serial=struct.unpack_from('>I',body,offset+13)[0]
            ack=lambda error:(0x1008,struct.pack('>3I',template,serial,error))
            previous=self.active.get(serial)
            if (previous is None or struct.unpack_from('>I',previous['body'])[0]!=template or body[offset+12]!=0
                    or any(abs(x)>=2000000 for x in position)):return [ack(1)]
            if previous['finished']:return [ack(0)]
            previous['finished']=True
            self.last_completion=dict(template=template,serial=serial,position=position,
                origin=struct.unpack_from('>3i',previous['body'],4),
                reference=previous['reference'],released_at=previous['at'])
            # 1287DB0 selects owner UID, then E3AE10 selects local throw serial.
            # The last DWORD's detailed effect meaning is unknown: retain zero.
            effect=(0x1009,struct.pack('>II3iBQI',template,serial,*position,0,actor_uid,0))
            return [ack(0),effect]
        return []
