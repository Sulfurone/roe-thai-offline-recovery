"""Local active-roster count through the original Thai survivor-number DTO.

The second DWORD is deliberately left uninterpreted. This does not implement
original matchmaking, a fixed participant pool, evacuation or victory rules.
"""
import struct


def survivor_number(count):
    # The codec reads two DWORDs; the verified callback consumes only the first.
    # 1000 is a local input bound, not a recovered original participant limit.
    if type(count) is not int or not 0<=count<=1000:
        raise ValueError('Local survivor count must be an integer in 0..1000')
    return 0x047d,struct.pack('>II',count,0)


class SurvivorStatus:
    def __init__(self,game,bots):
        if game is None or bots is None:raise ValueError('Survivor status requires a local game and roster')
        self.game,self.bots=game,bots
        self.last_count=None

    def tick(self):
        if not self.game.actor_ready:return []
        count=int(self.game.vitals.current>0)
        count+=sum(self.bots.vitals[uid].current>0 for uid in self.bots.actors)
        if count==self.last_count:return []
        packet=survivor_number(count)
        self.last_count=count
        return [packet]
