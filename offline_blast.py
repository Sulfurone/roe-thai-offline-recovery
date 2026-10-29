"""Local frag blast damage, independently bounded from client target UID lists.

The owned Thai ThrowableParams gives frag radius 1000 cm. Peak damage,
inner radius, falloff and body samples are explicit local prototype rules,
not a recovered original server formula or mesh collision implementation.
"""
import math
import time

from offline_combat import death_packet


class BlastCombat:
    RADIUS = 1000.  # Original 50001 mExplodeRange, centimetres.
    INNER_RADIUS = 200.
    PEAK_DAMAGE = 1000
    MAX_TRAVEL = 30000.

    def __init__(self,game,bots,visibility):
        self.game,self.bots,self.visibility=game,bots,visibility
        self.seen={}
        self.events=[]

    @staticmethod
    def point(value):
        return (isinstance(value,(tuple,list)) and len(value)==3
                and all(type(v) in (int,float) and abs(v)<2_000_000 and math.isfinite(v) for v in value))

    def damage_at(self,position,feet):
        # Distance to a conservative vertical body capsule, not its eye point.
        horizontal=max(0,math.dist(position[:2],feet[:2])-35)
        vertical=max(feet[2]-position[2],position[2]-feet[2]-180,0)
        distance=math.hypot(horizontal,vertical)
        if distance>=self.RADIUS:return 0
        if distance<=self.INNER_RADIUS:return self.PEAK_DAMAGE
        return math.ceil(self.PEAK_DAMAGE*(self.RADIUS-distance)/(self.RADIUS-self.INNER_RADIUS))

    def exposed(self,position,feet):
        origin=(position[0],position[1],position[2]+10)
        return any(self.visibility.clear(origin,(feet[0],feet[1],feet[2]+height))
                   for height in (30,90,150))

    def complete(self,event,now=None):
        self.events=[]
        if event is None:return []
        now=time.monotonic() if now is None else now
        self.seen={serial:at for serial,at in self.seen.items() if 0<=now-at<120}
        def reject(reason):
            self.events.append(dict(action='blast_rejected',reason=reason))
            return []
        if event.get('template')!=50001:return []  # Smoke/flash are not frag damage.
        serial=event.get('serial')
        if type(serial) is not int or not 0<=serial<2**32:return reject('serial')
        if serial in self.seen:return reject('duplicate')
        if len(self.seen)>=256:return reject('receipt_capacity')
        origin,reference,position=(event.get(k) for k in ('origin','reference','position'))
        if not all(self.point(p) for p in (origin,reference,position)):
            return reject('source_unavailable')
        if math.dist(origin,reference)>500:return reject('source_position')
        if math.dist(origin,position)>self.MAX_TRAVEL:return reject('endpoint_distance')
        self.seen[serial]=now
        g=self.game
        targets=[]
        # An in-flight grenade can still affect bots after its thrower dies.
        # Stale self position and vehicle occupants need separate handling.
        if (g.actor_ready and g.vitals.current and not g.seated
                and (not g.require_self_position_for_drop or g.has_fresh_self_position(now))):
            targets.append((g.actor_uid,g.player_position,g.vitals,True))
        if self.bots is not None:
            targets.extend((uid,actor['position'],self.bots.vitals[uid],False)
                           for uid,actor in self.bots.actors.items() if self.bots.vitals[uid].current)
        replies=[]
        for uid,feet,hp,own in targets:
            amount=self.damage_at(position,feet)
            if not amount or not self.exposed(position,feet):continue
            applied=hp.damage(amount)
            replies.append(hp.packet(uid))
            if not hp.current:
                replies.append(death_packet(uid))
                if own:g.medicine.cancel()
            self.events.append(dict(action='blast_hit',serial=serial,target_uid=uid,
                damage=applied,current=hp.current,original_damage_formula=False))
        self.events.append(dict(action='blast_completed',serial=serial,position=position,
            affected=sum(e['action']=='blast_hit' for e in self.events),
            radius=self.RADIUS,original_damage_formula=False))
        return replies
