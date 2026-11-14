"""Scheduled Thai supply flybys and searchable ground supplies."""
from dataclasses import dataclass
import math
import random
import struct

from offline_gameplay import TYPED_VEHICLE_UID
from offline_items import SPAWNABLE_EXTRA_ITEMS
from offline_motion import aircraft_spawn_heading
from offline_weapons import WEAPONS

def supply_vehicle(template, uid, position, config=4, *, state=0):
    if len(template)<16:
        raise ValueError('Invalid Thai supply aircraft fixture')
    name_size = struct.unpack_from('>I',template,8)[0]
    start = 12+name_size
    if not 1<=name_size<=128 or len(template)<start+41 or template[start-1]!=0:
        raise ValueError('Invalid Thai supply aircraft fixture')
    if struct.unpack_from('>I',template,start)[0]!=4:
        raise ValueError('Supply flyby requires a config-4 aircraft fixture')
    body = bytearray(template)
    struct.pack_into('>Q',body,0,uid)
    struct.pack_into('>II',body,start,config,state)
    struct.pack_into('>I3i',body,start+8,100,*position)
    return bytes(body)


@dataclass
class SupplyFlight:
    number: int
    started: float
    landing: tuple
    start: tuple
    end: tuple
    next_move: float
    aircraft_visible: bool = True
    cargo_visible: bool = False

    @property
    def aircraft(self):
        return TYPED_VEHICLE_UID+0x6000+2*self.number

    def position_at(self, elapsed, duration):
        fraction = min(1., elapsed/duration)
        return tuple(round(a+(b-a)*fraction) for a,b in zip(self.start,self.end))

    def movement(self, message, position, speed):
        length = math.dist(self.start,self.end)
        direction = tuple((b-a)/length for a,b in zip(self.start,self.end))
        return message,struct.pack('>Q3iB3fI',self.aircraft,*position,0,*direction,speed)


@dataclass
class LandedSupply:
    position: tuple
    expires: float
    parcel: int


class SupplyDrops:
    SCHEDULE = (120,420,660)
    FLY_SECONDS = 12.
    LAND_SECONDS = 19.
    LIFETIME = 300.
    SPEED = 4500
    HEIGHT = 14000

    def __init__(self, game, zones, parcels, aircraft_template, seed, visibility=None):
        supply_vehicle(aircraft_template,TYPED_VEHICLE_UID,(0,0,0))
        self.game, self.zones, self.parcels = game,zones,parcels
        self.terrain, self.visibility = zones.terrain,visibility
        self.template = aircraft_template
        self.rng = random.Random(f'{seed}:supply-drops')
        self.index = 0
        self.flight = None
        self.landed = {}
        self.next_attempt = 0.
        self.last_event = None

    def landing_spot(self, circle):
        center = (circle.x,circle.y)
        player = self.game.player_position[:2]
        scale = min(1.,circle.radius*.6/max(1.,math.dist(center,player)))
        anchor = tuple(a+(b-a)*scale for a,b in zip(center,player))
        for i in range(64):
            angle = self.rng.uniform(0,math.tau)
            if i<32:
                distance = min(33000,circle.radius*.65)*self.rng.uniform(.5,1.)
                x,y = (round(a+b*distance) for a,b in zip(anchor,(math.cos(angle),math.sin(angle))))
            else:
                distance = circle.radius*.8*math.sqrt(self.rng.random())
                x,y = (round(a+b*distance) for a,b in zip(center,(math.cos(angle),math.sin(angle))))
            if not (29000<=x<=380600 and 29000<=y<=380600
                    and math.dist(center,(x,y))<=circle.radius-300):
                continue
            heights = [self.terrain.height_at(x+dx,y+dy) for dx,dy in ((0,0),(-250,0),(250,0),(0,-250),(0,250))]
            if (any(z is None or not math.isfinite(z) or z<6500-1e-6 for z in heights)
                    or max(heights)-min(heights)>100):
                continue
            z = round(heights[0])
            if self.visibility is not None and not self.visibility.clear((x,y,z+25),(x,y,z+175),padding=65):
                continue
            if any(math.dist((x,y),drop.position[:2])<10000 for drop in self.landed.values()):
                continue
            return x,y,z+20
        return None

    def loot(self):
        weapon = self.rng.choice((10102,10103,10104,10207))
        spec = WEAPONS[weapon]
        extras = ((200103,1),(201003,1),(200903,1),(70003,2),(50001,2),(50002,2),
                  (self.rng.choice((40302,40303)),1))
        return [(weapon,spec.kind,1,spec.capacity),(spec.ammunition,3,spec.capacity*8,0)]+[
            (template,SPAWNABLE_EXTRA_ITEMS[template].kind,count,0) for template,count in extras]

    def status(self, now):
        if self.flight is not None:
            flight = self.flight
            return ('incoming',*flight.landing[:2],max(0,math.ceil(self.LAND_SECONDS-now+flight.started)))
        if self.landed:
            closest = min(self.landed.values(),key=lambda drop:math.dist(drop.position,self.game.player_position))
            return ('landed',*closest.position[:2],0)
        return None

    def tick(self, now):
        self.last_event = None
        replies = []
        for uid,drop in list(self.landed.items()):
            if now>=drop.expires or not self.parcels.parcels[drop.parcel][1]:
                replies.append(self.parcels.remove_airdrop(uid))
                del self.landed[uid]
        flight = self.flight
        if flight is not None:
            elapsed = now-flight.started
            if elapsed>=self.FLY_SECONDS and flight.aircraft_visible:
                replies.append((0x654c,struct.pack('>Q',flight.aircraft)))
                flight.aircraft_visible = False
            if elapsed>=self.LAND_SECONDS:
                uid=flight.aircraft+1
                entity=self.parcels.add_airdrop(uid,flight.landing,self.loot())
                if entity is not None:
                    self.landed[uid]=LandedSupply(flight.landing,now+self.LIFETIME,entity)
                    replies.extend(((0x654b,supply_vehicle(self.template,uid,flight.landing,config=501,state=1)),
                                    (0x6571,struct.pack('>QI',uid,entity))))
                    self.last_event=dict(action='landed',number=flight.number,position=flight.landing,entity=entity)
                elif flight.cargo_visible:
                    replies.append((0x654c,struct.pack('>Q',uid)))
                self.flight = None
                return replies
            if elapsed>=self.FLY_SECONDS/2 and not flight.cargo_visible:
                position = (*flight.landing[:2],flight.start[2])
                replies.append((0x654b,supply_vehicle(self.template,flight.aircraft+1,position,config=501)))
                flight.cargo_visible = True
                self.last_event = dict(action='released',number=flight.number,position=position)
            if flight.aircraft_visible and now>=flight.next_move:
                flight.next_move = now+.25
                target = flight.position_at(elapsed+.5,self.FLY_SECONDS)
                replies.append(flight.movement(0x6563,target,self.SPEED))
            return replies

        started = self.zones.started
        if (started is None or not self.game.vitals.current or self.index>=len(self.SCHEDULE)
                or now<max(started+self.SCHEDULE[self.index],self.next_attempt)):
            return replies
        position = self.landing_spot(self.zones.stage_at(now)[2])
        if position is None:
            self.next_attempt = now+5
            return replies
        self.index += 1
        angle = self.rng.uniform(0,math.tau)
        half = self.FLY_SECONDS*self.SPEED/2
        dx,dy = round(math.cos(angle)*half),round(math.sin(angle)*half)
        x,y,z = position
        start,end = (x-dx,y-dy,z+self.HEIGHT),(x+dx,y+dy,z+self.HEIGHT)
        flight = self.flight = SupplyFlight(self.index,now,position,start,end,now+.25)
        self.last_event = dict(action='incoming',number=flight.number,position=position)
        aircraft = aircraft_spawn_heading(supply_vehicle(self.template,flight.aircraft,start),end)
        notice = struct.pack('>3iB',x,y,start[2],0)+bytes(13)
        return replies+[(0x4a6,notice),
                        (0x654b,aircraft),flight.movement(0x6564,start,self.SPEED)]
