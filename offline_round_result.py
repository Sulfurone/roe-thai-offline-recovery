"""Optional local last-survivor outcome; not the original ROE result protocol."""


class LocalRoundResult:
    def __init__(self,game,bots):
        if game is None or bots is None or not 1<=bots.count<=4:
            raise ValueError('A round requires the player and a bounded bot roster')
        self.game,self.bots=game,bots
        self.state='waiting'
        self.participants=None

    def tick(self):
        if self.state in ('won','lost'):return False
        if not self.game.actor_ready:return False
        if not self.game.vitals.current:
            self.state='lost'
            return True
        if self.participants is None:
            # Never award a win while missing bots are still awaiting a spawn.
            if len(self.bots.actors)!=self.bots.count:return False
            self.participants=frozenset(self.bots.actors)
            self.state='playing'
        # A removed or incomplete roster is not evidence of a kill.
        if any(uid not in self.bots.actors or uid not in self.bots.vitals for uid in self.participants):return False
        if all(not self.bots.vitals[uid].current for uid in self.participants):
            self.state='won'
            return True
        return False
