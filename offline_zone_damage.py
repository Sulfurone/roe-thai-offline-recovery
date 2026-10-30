"""Optional local circle damage; rates are experimental, not original ROE rules."""
import math
import time
from offline_combat import death_packet


class ZoneDamage:
    PERIOD=1.0
    DAMAGE=10

    def __init__(self,schedule,bots=None):
        self.schedule=schedule
        self.game=schedule.game
        self.bots=bots
        self.next_tick=None
        self.events=[]

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        self.events=[]
        circle=self.schedule.circle_at(now)
        if circle is None:return []
        if self.next_tick is None:
            self.next_tick=now+self.PERIOD
            return []
        if now<self.next_tick:return []
        # No accumulated burst after a service stall or stale coordinates.
        self.next_tick=now+self.PERIOD
        x,y,radius=circle
        def outside(pos):return math.hypot(pos[0]-x,pos[1]-y)>radius
        replies=[];g=self.game
        fresh=(g.actor_ready and g.vitals.current and
               (not g.require_self_position_for_drop or g.has_fresh_self_position(now)))
        if fresh and outside(g.player_position):
            amount=g.vitals.damage(self.DAMAGE)
            if amount:
                replies.append(g.vitals.packet(g.actor_uid))
                if not g.vitals.current:
                    g.medicine.pending=None
                    replies.append(death_packet(g.actor_uid))
                self.events.append(dict(uid=g.actor_uid,damage=amount,current=g.vitals.current))
        if self.bots is not None:
            for uid,actor in self.bots.actors.items():
                if self.bots.vitals[uid].current and outside(actor['position']):
                    before=self.bots.vitals[uid].current
                    replies.extend(self.bots.damage(uid,self.DAMAGE))
                    self.events.append(dict(uid=uid,damage=before-self.bots.vitals[uid].current,
                                            current=self.bots.vitals[uid].current))
        return replies
