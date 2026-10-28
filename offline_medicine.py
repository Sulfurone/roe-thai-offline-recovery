"""Timed Thai medicine-use candidate from original ItemTable facts.

Cast times and total quantities are original table values. Bandage/first-aid
buff pulse timing is not recovered: this candidate applies their table amount
after casting. Original buff scheduling remains required for full fidelity.
"""
from dataclasses import dataclass,replace
import struct
import time


@dataclass(frozen=True)
class Medicine:
    seconds: int
    healing: int
    full_heal: bool = False


MEDICINES={70001:Medicine(3,100),70002:Medicine(6,500),70003:Medicine(8,1000,True)}


class MedicineUse:
    def __init__(self):self.pending=None

    def begin(self,body,inventory,vitals,allowed,now=None):
        now=time.monotonic() if now is None else now
        if len(body) not in (10,18) or body[:1]!=b'\3':return []
        command,container,slot,target_kind,target,current=struct.unpack('>BBHBIB',body[:10])
        # F62700 selects target kind 0 for ordinary self-use. Its target DWORD
        # is opaque/unused here; do not reinterpret it as an object UID.
        reject=lambda:[inventory.reply(3,1)] if inventory is not None else []
        item=inventory.items.get((container,slot)) if inventory is not None else None
        if (not allowed or current!=1 or target_kind!=0 or container!=2 or item is None
                or item.kind!=7 or item.template not in MEDICINES or item.count<1
                or not 0<vitals.current<vitals.maximum):return reject()
        if self.pending is not None:
            return [] if self.pending['uid']==item.uid else reject()
        spec=MEDICINES[item.template]
        self.pending=dict(uid=item.uid,template=item.template,deadline=now+spec.seconds)
        # Original 128CB60 forwards successful operation 3 to actor virtual
        # +2E0 with the item template. Sending it again at finish restarts it.
        return [inventory.reply(3,template=item.template)]

    def tick(self,inventory,vitals,actor_uid,allowed,now=None):
        now=time.monotonic() if now is None else now
        pending=self.pending
        if pending is None:return []
        key=next((k for k,item in inventory.items.items() if item.uid==pending['uid']),None) if inventory else None
        item=inventory.items.get(key) if key is not None else None
        if (not allowed or item is None or item.kind!=7 or item.template!=pending['template']
                or item.count<1 or not 0<vitals.current<vitals.maximum):
            self.pending=None
            return []
        if now<pending['deadline']:return []
        self.pending=None
        spec=MEDICINES[item.template]
        amount=max(0,min(vitals.maximum,1000)-vitals.current) if spec.full_heal else spec.healing
        if not vitals.heal(amount):return []
        if item.count==1:del inventory.items[key]
        else:inventory.items[key]=replace(item,count=item.count-1)
        return [inventory.delta([key]),vitals.packet(actor_uid)]
