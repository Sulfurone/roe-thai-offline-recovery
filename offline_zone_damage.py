"""Optional local circle damage; rates are experimental, not original ROE rules."""
import math
import time
from offline_combat import death_packet


class ZoneDamage:
    PERIOD=1.0
    STAGE_DAMAGE=(10,20,40,70,100)
    CLOSED_DAMAGE=150

    def __init__(self,schedule,bots=None,control=None):
        self.schedule=schedule
        self.game=schedule.game
        self.bots=bots
        self.control=control
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
        stage=self.schedule.stage_at(now)[0]
        amount_per_tick=(self.CLOSED_DAMAGE if radius==0 else
                         self.STAGE_DAMAGE[min(stage,len(self.schedule.plan.stages)-1,len(self.STAGE_DAMAGE)-1)])
        def outside(pos):return radius==0 or math.hypot(pos[0]-x,pos[1]-y)>radius
        replies=[];g=self.game
        in_car=g.seated and self.control is not None and self.control.active_vehicle is not None
        fresh=(g.actor_ready and g.vitals.current and
               (in_car or not g.require_self_position_for_drop or g.has_fresh_self_position(now)))
        if fresh and outside(g.player_position):
            amount=g.vitals.damage(amount_per_tick)
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
                    replies.extend(self.bots.damage(uid,amount_per_tick,weapon=0))
                    self.events.append(dict(uid=uid,damage=before-self.bots.vitals[uid].current,
                                            current=self.bots.vitals[uid].current))
        return replies
