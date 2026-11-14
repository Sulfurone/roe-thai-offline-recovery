"""Local surviving participant count through the original Thai DTO.

The second DWORD is deliberately left uninterpreted. This does not implement
original matchmaking, a fixed participant pool, evacuation or victory rules.
"""
import struct


def room_kill_broadcast(killer_uid, killer_name, victim_uid, victim_name, weapon, alive, *, headshot=False,
                        vehicle_impact=False):
    """Thai 0x0480 ROOM_KILL_BROADCAST for a final elimination."""
    if not 0<=alive<=64 or not 0<=weapon<2**31 or bool(killer_uid)!=bool(weapon):
        raise ValueError('Invalid kill broadcast cause or survivor count')

    def participant(uid, name):
        if not 0 <= uid < 2**64 or len(name) > 127 or b'\0' in name:
            raise ValueError('Invalid kill broadcast participant')
        return struct.pack('>QI',uid,len(name)+1)+name+b'\0'

    # Original E_POWER_UPDATE_REASON values: SHOOT=1, MISSLE=2, SHRINK=3, VEHICLE_HIT_STC=12.
    reason=12 if vehicle_impact else 3 if not weapon else 2 if weapon==50001 else 1
    vehicle=weapon if vehicle_impact else 0
    if vehicle_impact:
        weapon=0
    # Solo mode has no separate downer or team flags.
    body=participant(killer_uid,killer_name)+participant(0,b'')+struct.pack('>I',weapon)
    body+=participant(victim_uid,victim_name)+struct.pack('>3I5B',alive,vehicle,reason,0,0,0,0,int(headshot))
    return 0x0480,body


def survivor_number(count):
    # The codec reads two DWORDs; the verified callback consumes only the first.
    # 1000 is a local input bound, not a recovered original participant limit.
    if type(count) is not int or not 0<=count<=1000:
        raise ValueError('Local survivor count must be an integer in 0..1000')
    return 0x047d,struct.pack('>II',count,0)


def survivor_count(game,bots):
    return int(game.vitals.current>0)+sum(hp.current>0 for hp in bots.vitals.values())


class SurvivorStatus:
    def __init__(self,game,bots):
        if game is None or bots is None:raise ValueError('Survivor status requires a local game and roster')
        self.game,self.bots=game,bots
        self.last_count=None

    def tick(self):
        if not self.game.actor_ready:return []
        count=survivor_count(self.game,self.bots)
        if count==self.last_count:return []
        packet=survivor_number(count)
        self.last_count=count
        return [packet]
