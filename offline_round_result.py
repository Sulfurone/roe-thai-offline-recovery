"""Local last-survivor outcome and the Thai native outcome messages."""
import struct
import time

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
        self.started_at=None
        self.survival_seconds=0

    def tick(self):
        if self.state in ('won','lost'):return False
        if not self.game.actor_ready:return False
        now=time.monotonic()
        if self.started_at is None:self.started_at=now
        if not self.game.vitals.current:
            self.state='lost'
            # Roster slots without an actor yet are still in the match.
            eliminated=sum(not hp.current for hp in self.bots.vitals.values())
            self.placement=self.size-eliminated
            self.survival_seconds=int(now-self.started_at)
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
            self.survival_seconds=int(now-self.started_at)
            return True
        return False

    def native_messages(self, room_uid, name, *, killer_uid=0, killer_name=b''):
        if self.state not in ('won', 'lost'):
            return []
        # SET_MATCH_ID initializes the same client field that OUTCOME checks.
        replies = [(0x0d77, struct.pack('>IQ', 0, room_uid) + bytes(28))]
        if self.state == 'lost':
            killer_name += b'\0'
            terminal = (struct.pack('>QI', killer_uid, len(killer_name)) + killer_name
                        + struct.pack('>QIBIII', 0, 1, 0, 0, 0, 15))
            replies.append((0x106e, terminal))
        # This build reads separate rank/total pairs for solo and team mode.
        # The offline roster has one human with no allies in either mode.
        outcome = (struct.pack('>QQI', room_uid, self.game.actor_uid, len(name)) + name
                   + struct.pack('>6I2Q4IB', self.placement, self.size,
                                 self.placement, self.size, 0, 0, 0, 0,
                                 0, 0, 0, self.survival_seconds, 0))
        replies.append((0x0d62, outcome))
        return replies
