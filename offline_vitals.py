"""Bounded single-player life state and the original Thai 1069 HP delta.

Initial 100 HP is the offline scenario setting, not a recovered server table
default. Combat damage, item-use timing and death actions are separate work.
"""
from dataclasses import dataclass
import struct


@dataclass
class Vitals:
    current: int = 100
    maximum: int = 100

    def __post_init__(self):
        if (type(self.current) is not int or type(self.maximum) is not int
                or not 1<=self.maximum<=100000 or not 0<=self.current<=self.maximum):
            raise ValueError('Invalid offline life state')

    def damage(self,amount):
        if type(amount) is not int or amount<0:raise ValueError('Invalid damage')
        applied=min(amount,self.current)
        self.current-=applied
        return applied

    def heal(self,amount):
        if type(amount) is not int or amount<0:raise ValueError('Invalid healing')
        # Reanimation is a separate state transition, not healing from zero.
        applied=min(amount,self.maximum-self.current) if self.current else 0
        self.current+=applied
        return applied

    def packet(self,uid):
        if type(uid) is not int or not 0<uid<2**64:raise ValueError('Invalid life owner')
        # D775D0/D77690: UID, flag, byte count, indexed (byte, DWORD, DWORD)
        # rows. Native 127B080 index 0 reads BOTH current and maximum HP.
        return 0x1069,struct.pack('>QBB',uid,0,1)+struct.pack('>BII',0,self.current,self.maximum)
