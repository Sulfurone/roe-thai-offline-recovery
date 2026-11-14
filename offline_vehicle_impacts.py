"""Resolve local vehicle impacts along consecutive driver physics reports."""
import math


class VehicleImpacts:
    MIN_SPEED=350  # cm/s
    MAX_SPEED=5500
    FULL_DAMAGE_SPEED=1450
    CONTACT_RADIUS=165
    MIN_SAMPLE=.09
    MAX_SAMPLE=.6

    def __init__(self,game,bots,visibility=None):
        self.game,self.bots,self.visibility=game,bots,visibility
        self.reset()

    def reset(self):
        self.sample=None
        self.contacts=set()

    def move(self,uid,config,position,velocity,now):
        previous=self.sample
        if not self.game.vitals.current or previous is None or previous[0]!=uid:
            self.reset()
            self.sample=(uid,position,now)
            return []
        _,start,at=previous
        elapsed=now-at
        if elapsed<self.MIN_SAMPLE:
            return []
        self.sample=(uid,position,now)
        dx,dy=position[0]-start[0],position[1]-start[1]
        length=math.hypot(dx,dy)
        speed=math.hypot(*velocity[:2])
        if (elapsed>self.MAX_SAMPLE or not self.MIN_SPEED<=speed<=self.MAX_SPEED
                or not 0<length<=self.MAX_SPEED*elapsed+150
                or dx*velocity[0]+dy*velocity[1]<0):
            self.contacts.clear()
            return []
        replies=[]
        touching=set()
        for bot,actor in self.bots.active_actors():
            if not self.bots.vitals[bot].current:
                continue
            victim=actor['position']
            fraction=max(0.,min(1.,((victim[0]-start[0])*dx+(victim[1]-start[1])*dy)/length**2))
            point=tuple(a+(b-a)*fraction for a,b in zip(start,position))
            if abs(victim[2]-point[2])>165 or math.dist(victim[:2],point[:2])>self.CONTACT_RADIUS:
                continue
            touching.add(bot)
            if bot in self.contacts:
                continue
            if self.visibility is not None and not self.visibility.clear(
                    (*point[:2],point[2]+85),(*victim[:2],victim[2]+85)):
                continue
            damage=min(1000,max(100,round(1000*(speed/self.FULL_DAMAGE_SPEED)**2)))
            replies.extend(self.bots.damage(bot,damage,killer=self.game.actor_uid,weapon=config))
        self.contacts=touching
        return replies
