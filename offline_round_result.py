"""Local last-survivor outcome for the game-window overlay."""
from offline_bots import BotRoster


class LocalRoundResult:
    def __init__(self,game,bots):
        if game is None or bots is None or not 1<=bots.count<=BotRoster.MAX_COUNT:
            raise ValueError('A round requires the player and a bounded bot roster')
        self.game,self.bots=game,bots
        self.state='waiting'
        self.participants=None
        self.placement=None
        self.size=bots.count+1

    def tick(self):
        if self.state in ('won','lost'):return False
        if not self.game.actor_ready:return False
        if not self.game.vitals.current:
            self.state='lost'
            # Roster slots without an actor yet are still in the match.
            eliminated=sum(not hp.current for hp in self.bots.vitals.values())
            self.placement=self.size-eliminated
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
            self.placement=1
            return True
        return False
