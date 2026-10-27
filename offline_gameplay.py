"""Opt-in Thai single-player interaction prototype, isolated from the baseline.

Wire fields below are checked against the original Thai native decoders.
Physics remains in the client; successful protocol handling is not a claim
that rendering, driving, or combat has been visually verified.
"""
from dataclasses import dataclass,field
import json
import math
from pathlib import Path
import random
import struct
import time
from offline_inventory import Item,OfflineInventory
from offline_ground_loot import OfflineGroundLoot,MAX_GROUND_STACKS
from offline_weapons import WEAPONS,AMMUNITION,is_weapon
import offline_world_state

ACTOR_UID = 256
JEEP_UID = 0x200101
JEEP_CONFIG = 101
TYPED_ACTOR_UID = 0x0001000000000100
TYPED_VEHICLE_UID = 0x0005000000200101
# Original EuVehicleTable rows, decoded with the 0x74FEF0 reflection schema.
# id: (initial HP, initial oil, get-on distance in cm). Oil is zero in this
# Thai table, including max oil; do not invent a modern fuel mechanic.
VEHICLE_DEFAULTS = {101:(24000,0,500),3:(100,0,0),4:(100,0,0)}


@dataclass
class OfflineGameplay:
    magazine: int = 30
    reserve: int = 120
    selected_slot: int = 1
    seated: bool = False
    seat: int = 0
    vehicle_position: tuple = (326400,272200,6501)
    player_position: tuple = (325800,271700,7054)
    auto_board: bool = False
    actor_ready: bool = False
    vehicle_ready: bool = False
    vehicle_announced: bool = False
    vehicle_config: int = JEEP_CONFIG
    actor_uid: int = ACTOR_UID
    vehicle_uid: int = JEEP_UID
    initialize_vehicle: bool = False
    vehicle_initialized: bool = False
    auto_exit_after: float = 0
    exit_deadline: float | None = None
    aircraft_route_speed: int = 0
    route_started: float | None = None
    route_origin: tuple | None = None
    route_next: float = 0
    inventory_enabled: bool = False
    state_file: Path | None = None
    inventory: OfflineInventory | None = field(default=None,init=False)
    _saved_payload: str | None = field(default=None,init=False,repr=False)
    inventory_selftest: bool = False
    inventory_test_started: float | None = None
    inventory_test_stage: int = 0
    opening_airdrop: bool = False
    jump_enable_deadline: float | None = None
    jump_allowed: bool = False
    deployment_phase: str = 'ground'
    aircraft_route_end: tuple | None = None
    ground_loot_enabled: bool = False
    arsenal_enabled: bool = False
    ground_loot: OfflineGroundLoot | None = field(default=None,init=False)
    world_file: Path | None = None
    state_save_count: int = field(default=0,init=False)
    scatter_loot: bool = False
    scatter_anchor: tuple | None = field(default=None,init=False)
    scatter_random: random.Random = field(default_factory=random.Random,init=False)

    def __post_init__(self):
        if self.arsenal_enabled and not self.ground_loot_enabled:
            raise ValueError('Arsenal requires ground loot')
        if self.scatter_loot and not self.ground_loot_enabled:
            raise ValueError('Scatter loot requires ground loot')
        if self.ground_loot_enabled and (not self.inventory_enabled or self.state_file is not None):
            raise ValueError('Ground loot requires inventory and cannot use an inventory-only profile')
        if self.world_file is not None and (not self.ground_loot_enabled or not self.inventory_enabled
                or self.state_file is not None or self.inventory_selftest):
            raise ValueError('World persistence requires inventory/ground loot and a separate world profile')
        if self.aircraft_route_end is not None and (len(self.aircraft_route_end)!=3
                or any(type(x) is not int or abs(x)>=2000000 for x in self.aircraft_route_end)):
            raise ValueError('Aircraft route endpoint must be three bounded integer coordinates')
        maximum_speed=5000 if self.aircraft_route_end is not None else 2500
        maximum_duration=180 if self.aircraft_route_end is not None else 40
        if self.opening_airdrop and (self.vehicle_config!=4 or not self.auto_board
                or not 0<self.aircraft_route_speed<=maximum_speed or not 3<self.auto_exit_after<=maximum_duration):
            raise ValueError('Opening airdrop requires aircraft auto-board and a bounded route/speed/duration')
        if self.state_file is not None and not self.inventory_enabled:
            raise ValueError('Persistent inventory requires the inventory option')
        if self.inventory_selftest and (not self.inventory_enabled or self.state_file is not None):
            raise ValueError('Inventory self-test requires a fresh, non-persistent inventory')
        if not self.inventory_enabled:
            return
        self.inventory=OfflineInventory(self.reserve)
        weapon=self.inventory.items.get((1,1))
        if weapon is not None:
            self.inventory.weapon_magazines[weapon.uid]=self.magazine
        if self.ground_loot_enabled:
            from offline_inventory import Item,AMMO_TEMPLATE
            self.ground_loot=OfflineGroundLoot()
            self.ground_loot.add(Item(3,AMMO_TEMPLATE,self.inventory.next_uid,60),(325950,271700,6501))
            self.inventory.next_uid+=1
            if self.arsenal_enabled and (self.world_file is None or not Path(self.world_file).exists()):
                # An explicit fresh test world provides all recovered firearms.
                # Existing saved worlds are restored without adding items.
                for index,(template,spec) in enumerate(sorted(WEAPONS.items())):
                    position=(325950+(index%5)*175,271875+(index//5)*175,6501)
                    self.ground_loot.add(Item(spec.kind,template,self.inventory.next_uid,1),position)
                    self.inventory.next_uid+=1
                for index,template in enumerate(sorted(AMMUNITION-{AMMO_TEMPLATE})):
                    position=(325950+index*175,271525,6501)
                    self.ground_loot.add(Item(3,template,self.inventory.next_uid,60),position)
                    self.inventory.next_uid+=1
        if self.state_file is not None:
            self.state_file=Path(self.state_file)
            if self.state_file.exists():
                if self.state_file.stat().st_size>65536:
                    raise ValueError('Offline inventory profile exceeds 64 KiB')
                data=json.loads(self.state_file.read_text(encoding='utf-8'))
                self.inventory=OfflineInventory.restore(data)
                self.magazine=data['magazine']
                self.selected_slot=data['selected_slot']
                self.reserve=self.inventory.reserve
                self._saved_payload=self.state_payload()
        if self.world_file is not None:
            self.world_file=Path(self.world_file)
            if self.world_file.exists():
                self.inventory,self.ground_loot,self.magazine,self.selected_slot=offline_world_state.read(self.world_file)
                self.reserve=self.inventory.reserve
                self._saved_payload=self.state_payload()

    def state_payload(self):
        if self.world_file is not None:
            data=offline_world_state.snapshot(self.inventory,self.ground_loot,self.magazine,self.selected_slot)
            return json.dumps(data,indent=2)+'\n'
        return json.dumps(self.inventory.snapshot(self.magazine,self.selected_slot),indent=2)+'\n'

    def save_state(self):
        destination=self.world_file or self.state_file
        if destination is None:
            return False
        payload=self.state_payload()
        if payload==self._saved_payload:
            return False
        offline_world_state.write_atomic(destination,payload)
        self._saved_payload=payload
        self.state_save_count+=1
        return True

    def has_weapon(self,slot):
        if self.inventory is None:
            return slot==1
        item=self.inventory.items.get((1,slot))
        return item is not None and is_weapon(item)

    def weapon_key(self,slot=None):
        slot=self.selected_slot if slot is None else slot
        return (1,slot) if self.has_weapon(slot) else None

    def weapon_magazine(self,key):
        if self.inventory is None:
            return self.magazine
        item=self.inventory.items.get(key)
        if item is None or not is_weapon(item):
            return 0
        if key==self.weapon_key():
            return self.magazine
        return self.inventory.weapon_magazines.get(item.uid,0)

    def set_weapon_magazine(self,key,count):
        if self.inventory is None:
            return
        item=self.inventory.items.get(key)
        if item is None or not is_weapon(item):
            return
        self.inventory.weapon_magazines[item.uid]=count
        if key==self.weapon_key():
            self.magazine=count

    def refresh_magazine(self):
        # The live magazine value always mirrors the gun in the selected
        # slot; with no gun selected it carries no meaning.
        if self.inventory is None:
            return
        key=self.weapon_key()
        self.magazine=(self.inventory.weapon_magazines[self.inventory.items[key].uid]
                       if key is not None else 0)

    def sync_slot(self):
        if self.inventory is None:
            return 1
        if self.has_weapon(self.selected_slot):
            return self.selected_slot
        return next((slot for (container,slot),item in sorted(self.inventory.items.items())
                     if container==1 and is_weapon(item)),1)

    def ammo_sync(self,slot=None):
        if slot is None:
            slot=self.sync_slot()
        return 0x04a0, struct.pack('>QII',self.actor_uid,slot,self.weapon_magazine((1,slot)))

    def observe_spawn(self,message,body):
        # Native 0x654B: QWORD uid, DWORD name length, NUL-terminated name,
        # three DWORDs (config/flags/state), followed by integer XYZ.
        if message!=0x654b or len(body)<40:
            return
        uid,name_bytes=struct.unpack_from('>QI',body)
        if uid!=self.vehicle_uid or not 1<=name_bytes<=128:
            return
        start=12+name_bytes
        if len(body)<start+24 or body[start-1]!=0:
            return
        config=struct.unpack_from('>I',body,start)[0]
        position=struct.unpack_from('>3i',body,start+12)
        if config!=self.vehicle_config or not all(abs(v)<2000000 for v in position):
            return
        self.vehicle_position=position
        self.vehicle_announced=True

    def can_auto_board(self):
        # The unoccupied glider does not send car physics reports. Its
        # diagnostic boarding gate uses the map actor's first movement.
        return (self.auto_board and self.actor_ready and
                (self.vehicle_ready or (self.vehicle_config in (3,4) and self.vehicle_announced)))

    def reserve_sync(self):
        if self.inventory is not None:
            keys=[key for key,item in self.inventory.items.items() if item.kind==3]
            return self.inventory.delta(keys or [(2,0)])
        # Thai 0x3E82: count byte; slot ushort; container byte; OBJECT_INFO;
        # current-map flag. This updates one bag slot without resetting guns.
        kind,template,uid = (3,30001,0x100102) if self.reserve else (0,0,0)
        body = struct.pack('>BHB',1,0,2)
        body += struct.pack('>BBIQIIBBIH',kind,0,template,uid,self.reserve,0,0,0,0,0)
        if kind == 0:
            body += b'\0'  # Native empty-object union has one dummy byte.
        body += struct.pack('>IB',0,1)
        return 0x3e82,body

    def owner_sync(self, owner):
        return 0x656d, struct.pack('>QIQ',self.vehicle_uid,0,owner)

    def vehicle_state_sync(self):
        # Thai 0x6554 routes to health/status; 0x656E sets oil. The base
        # table gives no evidence for a nonzero fuel resource in this build.
        hp,oil,_=VEHICLE_DEFAULTS[self.vehicle_config]
        return [(0x6554,struct.pack('>QII',self.vehicle_uid,hp,0)),
                (0x656e,struct.pack('>QI',self.vehicle_uid,oil))]

    def initialize_vehicle_once(self):
        if not self.initialize_vehicle or self.vehicle_initialized:
            return []
        self.vehicle_initialized=True
        return self.vehicle_state_sync()

    def board(self, seat=1):
        if self.seated:
            return []
        self.seated = True
        self.seat = seat
        if self.auto_exit_after>0:
            self.exit_deadline=time.monotonic()+self.auto_exit_after
        # +8 is the vehicle CONFIG ID, not the seat. Callback 0x108D040
        # looks up that config; +0x18 is a one-based passenger seat.
        reply = struct.pack('>QIIQII3iB',self.vehicle_uid,self.vehicle_config,0,
                            self.actor_uid,seat,0,*self.vehicle_position,0)
        prefix=self.initialize_vehicle_once()
        replies=prefix+[self.owner_sync(self.actor_uid),(0x6542,reply)]
        if self.vehicle_config==4:
            # Original 0x1288F00 enables SimpleAeroUnit's jump control.
            self.jump_allowed=not self.opening_airdrop
            if self.jump_allowed:
                replies.append((0x6565,struct.pack('>Q',self.vehicle_uid)))
            if self.aircraft_route_speed>0:
                self.route_origin=self.vehicle_position
                self.route_started=time.monotonic()
                self.route_next=self.route_started
                replies.append((0x6564,self.aircraft_move(self.vehicle_position)))
                if self.opening_airdrop:
                    self.jump_enable_deadline=self.route_started+3
                    self.exit_deadline=self.route_started+self.auto_exit_after
                    self.deployment_phase='boarding'
        return replies

    def aircraft_move(self,position):
        # Thai 0x6563/64: UID, integer position+flag, direction floats,
        # movement speed DWORD. 0x130DDD0 normalizes the target delta;
        # 0x130E180 integrates that direction times speed and frame delta.
        direction=(0.,1.,0.)
        if self.aircraft_route_end is not None:
            origin=self.route_origin or self.vehicle_position
            length=math.dist(origin,self.aircraft_route_end)
            if length>0:
                direction=tuple((b-a)/length for a,b in zip(origin,self.aircraft_route_end))
        return struct.pack('>Q3iB3fI',self.vehicle_uid,*position,0,*direction,self.aircraft_route_speed)

    def route_position_at(self,elapsed):
        elapsed=max(0.,elapsed)
        if self.opening_airdrop:
            elapsed=min(elapsed,self.auto_exit_after)
        if self.aircraft_route_end is not None:
            length=math.dist(self.route_origin,self.aircraft_route_end)
            ratio=min(elapsed*self.aircraft_route_speed/length,1.) if length else 1.
            return tuple(round(a+(b-a)*ratio) for a,b in zip(self.route_origin,self.aircraft_route_end))
        x,y,z=self.route_origin
        return (x,y+round(min(elapsed*self.aircraft_route_speed,100000)),z)

    def update_route_position(self,now):
        if self.route_started is None or self.route_origin is None:
            return
        self.vehicle_position=self.route_position_at(now-self.route_started)

    def leave(self,now=None):
        if not self.seated:
            return []
        now=time.monotonic() if now is None else now
        self.update_route_position(now)
        x,y,z = self.vehicle_position
        position = (x+180,y,z+120)
        reply = struct.pack('>QIQII3iB',self.vehicle_uid,0,self.actor_uid,self.seat,
                            0,*position,0)
        self.seated = False
        self.seat = 0
        self.exit_deadline=None
        self.jump_enable_deadline=None
        self.jump_allowed=False
        if self.opening_airdrop:
            self.deployment_phase='descending'
        else:
            self.route_started=None
        self.player_position = position
        return [(0x6544,reply),self.owner_sync(0)]

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        if self.route_started is not None and (self.seated or self.opening_airdrop):
            self.update_route_position(now)
        if self.exit_deadline is not None and now>=self.exit_deadline:
            replies=self.leave(now)
            if self.opening_airdrop:
                self.route_started=None
            return replies
        replies=[]
        if (self.jump_enable_deadline is not None and now>=self.jump_enable_deadline
                and self.seated):
            self.jump_enable_deadline=None
            self.jump_allowed=True
            self.deployment_phase='jump_available'
            replies.append((0x6565,struct.pack('>Q',self.vehicle_uid)))
        if (self.opening_airdrop and self.route_started is not None
                and now>=self.route_started+self.auto_exit_after):
            replies.append((0x6563,self.aircraft_move(self.vehicle_position)))
            self.route_started=None
            return replies
        if (self.route_started is not None and now>=self.route_next
                and (self.seated or self.opening_airdrop)):
            self.route_next=now+.25
            target=self.route_position_at(now-self.route_started+.25)
            replies.append((0x6563,self.aircraft_move(target)))
        if replies:
            return replies
        if (self.inventory_selftest and self.inventory_test_started is not None
                and self.inventory_test_stage<3
                and now-self.inventory_test_started>=2*(self.inventory_test_stage+1)):
            moves=[(2,0,2,5,30),(1,1,1,2,1),(1,2,1,1,1)]
            request=struct.pack('>BBHBHHB',1,*moves[self.inventory_test_stage],1)
            self.inventory_test_stage+=1
            return self.handle(0x3e80,request)
        return []

    @staticmethod
    def valid_length(body, logical):
        # Actual Thai application requests append eight transport fields
        # after the logical DTO. Unit tests may use the bare logical body.
        return len(body) in (logical,logical+8)

    def handle(self,message,body):
        if self.world_file is None:
            return self._handle(message,body)
        previous=self.state_payload()
        announced=self.ground_loot.announced
        try:
            replies=self._handle(message,body)
            # Commit both sides of every transfer before returning replies
            # to the socket sender. A write failure closes the session without
            # acknowledging a mutation that could disappear on restart.
            self.save_state()
            return replies
        except (OSError,ValueError):
            self.inventory,self.ground_loot,self.magazine,self.selected_slot=offline_world_state.restore(json.loads(previous))
            self.ground_loot.announced=announced
            self.reserve=self.inventory.reserve
            raise

    SCATTER_STEP=60000  # centimetres of reported travel between clusters
    SCATTER_MIN=3000
    SCATTER_MAX=8000
    SCATTER_CEILING=12000  # ignore airborne positions from an opening jump

    def scatter(self,position):
        # Ground height away from the spawn plateau is only known from the
        # client's own reports, so clusters anchor to the reported position
        # and inherit its height. Clusters are committed with the world
        # profile like any other loot mutation.
        if self.ground_loot is None or not self.ground_loot.announced:
            return []
        x,y,z=position
        if z>=self.SCATTER_CEILING:
            return []
        anchor=self.scatter_anchor
        if anchor is None:
            self.scatter_anchor=position
            return []
        if math.dist((x,y,0),(anchor[0],anchor[1],0))<self.SCATTER_STEP:
            return []
        self.scatter_anchor=position
        if len(self.ground_loot.stacks)>MAX_GROUND_STACKS-2:
            return []
        picks=self.scatter_random
        template=sorted(WEAPONS)[len(self.ground_loot.stacks)//2%len(WEAPONS)]
        spec=WEAPONS[template]
        angle=picks.uniform(0,2*math.pi)
        distance=picks.uniform(self.SCATTER_MIN,self.SCATTER_MAX)
        spot=(x+round(distance*math.cos(angle)),y+round(distance*math.sin(angle)),z)
        weapon=self.ground_loot.add(Item(spec.kind,template,self.inventory.next_uid,1),
                                    spot,picks.randint(0,spec.capacity))
        self.inventory.next_uid+=1
        ammo=self.ground_loot.add(Item(3,spec.ammunition,self.inventory.next_uid,
                                       picks.randint(40,60)),(spot[0]+100,spot[1],spot[2]))
        self.inventory.next_uid+=1
        return [weapon.spawn(),ammo.spawn()]

    def _handle(self, message, body):
        if message==0x3b63 and self.ground_loot is not None:
            stack=(self.ground_loot.stacks.get(struct.unpack_from('>I',body)[0])
                   if len(body) in (33,41) else None)
            replies=self.ground_loot.pickup(body,self.inventory,self.actor_uid,self.player_position,
                                            self.actor_ready and not self.seated)
            self.reserve=self.inventory.reserve
            if stack is not None and is_weapon(stack.item) and any(msg==0x3e82 for msg,_ in replies):
                key=next((k for k,item in self.inventory.items.items() if item.uid==stack.item.uid),None)
                if key is not None:
                    # A picked gun keeps the rounds it carried on the ground;
                    # with empty hands it becomes the carried weapon.
                    self.set_weapon_magazine(key,stack.magazine)
                    if key[0]==1 and self.weapon_key() is None:
                        self.selected_slot=key[1]
                    self.refresh_magazine()
                    if self.inventory.weapon_slot() is not None:
                        replies.append(self.ammo_sync())
            return replies
        if message==0x3e80 and self.inventory is not None:
            previous_weapon=self.inventory.weapon_slot()
            if body[:1]==b'\2' and self.ground_loot is not None:
                magazine=(self.weapon_magazine((body[1],struct.unpack_from('>H',body,2)[0]))
                          if len(body)>=15 else 0)
                replies=self.ground_loot.drop(body,self.inventory,self.actor_uid,self.player_position,
                                             self.actor_ready and not self.seated,magazine)
            else:
                replies=self.inventory.handle(body)
            self.reserve=self.inventory.reserve
            survivors={item.uid for item in self.inventory.items.values() if is_weapon(item)}
            for uid in [uid for uid in self.inventory.weapon_magazines if uid not in survivors]:
                del self.inventory.weapon_magazines[uid]
            self.refresh_magazine()
            if previous_weapon is not None and not survivors:
                replies.append(self.ammo_sync(previous_weapon))
                if self.selected_slot==previous_weapon:
                    self.selected_slot=0
            if any(msg==0x3e82 for msg,_ in replies) and survivors:
                replies.append(self.ammo_sync())
            return replies
        if message in (0x049e,0x049c) and self.valid_length(body,4):
            slot = struct.unpack_from('>I',body)[0]
            if message == 0x049e:
                if slot in (0,1,2,3,4,5,6):
                    self.selected_slot = slot
                    self.refresh_magazine()
                return [self.ammo_sync(slot)] if self.has_weapon(slot) else []
            if not self.has_weapon(slot):
                return [(0x049d,struct.pack('>II',slot,1))]
            key=(1,slot)
            item=self.inventory.items[key] if self.inventory is not None else None
            spec=WEAPONS[item.template] if item is not None else WEAPONS[10201]
            available=self.inventory.reserve_for(spec.ammunition) if self.inventory is not None else self.reserve
            current=self.weapon_magazine(key)
            amount = min(spec.capacity-current,available)
            if self.inventory is None:
                self.magazine += amount
            else:
                self.set_weapon_magazine(key,current+amount)
            self.reserve -= amount
            reserve_update=self.inventory.consume(amount,spec.ammunition) if self.inventory is not None else self.reserve_sync()
            return [(0x049d,struct.pack('>II',slot,0)),self.ammo_sync(slot),reserve_update]
        if message == 0x11d3 and self.valid_length(body,29) and self.has_weapon(self.selected_slot):
            # Original 0xEA28BA calls 0x128A490 once per shot with flag 0;
            # 0xE99EEE uses flag 1 on stopping, even with nonzero coordinates.
            # The six floats are origin and target point, not a direction.
            # TCP already deduplicates transport retransmissions. Identical
            # stationary shots must each consume a round.
            coords = struct.unpack_from('>6f',body)
            if (body[28] != 0 or not all(math.isfinite(x) for x in coords)
                    or sum((a-b)**2 for a,b in zip(coords[:3],coords[3:]))<1e-12):
                return []
            self.set_weapon_magazine((1,self.selected_slot),
                                     max(0,self.weapon_magazine((1,self.selected_slot))-1))
            if self.inventory is None:
                self.magazine=max(0,self.magazine-1)
            return [self.ammo_sync()]
        if message == 0x6549 and self.valid_length(body,61):
            uid = struct.unpack_from('>Q',body)[0]
            position = struct.unpack_from('>3i',body,13)
            if uid == self.vehicle_uid and all(abs(x)<2000000 for x in position):
                self.vehicle_position = position
                self.vehicle_ready = True
                if self.can_auto_board():
                    self.auto_board = False
                    return self.board()
        if message == 0x6541 and self.valid_length(body,12):
            uid,seat = struct.unpack_from('>QI',body)
            if uid != self.vehicle_uid or seat > 4:
                return []
            distance=VEHICLE_DEFAULTS[self.vehicle_config][2]
            if distance<=0 or sum((a-b)**2 for a,b in zip(self.player_position,self.vehicle_position)) > distance**2:
                return []
            return self.board(seat or 1)
        if message == 0x6543 and self.valid_length(body,1):
            return self.leave()
        if message==0x6547 and self.valid_length(body,4) and self.vehicle_config==101 and self.seated:
            # Original 0x1288750 sends a one-based destination seat.
            # Callback 0x1288620 consumes vehicle/actor IDs, old/new seats,
            # then error; it converts both seats back to zero-based.
            destination=struct.unpack_from('>I',body)[0]
            previous=self.seat
            error=0 if 1<=destination<=4 else 1
            if not error:
                self.seat=destination
            return [(0x6548,struct.pack('>QQIII',self.vehicle_uid,self.actor_uid,
                                       previous,destination,error))]
        if message == 0x6572 and self.valid_length(body,14) and self.vehicle_config==101:
            # Native request 0x12888F0 and broadcast callback 0x1288BC0
            # share frame DWORD / time BYTE / vehicle QWORD / input BYTE.
            # Preserve the original input; never synthesize a drive command.
            uid=struct.unpack_from('>Q',body,5)[0]
            if uid==self.vehicle_uid and ((self.seated and self.seat==1) or body[13]==0x10):
                return [(0x6573,body[:14])]
        if message == 0x6566 and self.valid_length(body,1) and self.vehicle_config==4:
            if self.opening_airdrop and (not self.seated or self.jump_enable_deadline is not None
                    and time.monotonic()<self.jump_enable_deadline):
                return []
            return self.leave()
        if message == 0x002a and len(body)>=16:
            position = struct.unpack_from('>3i',body,4)
            if all(abs(x)<2000000 for x in position):
                self.player_position = position
                self.actor_ready = True
                loot_replies=[]
                if self.ground_loot is not None:
                    # In the combined opening test, avoid delivering a distant
                    # ground test range while the player is aboard the aircraft.
                    # Announce once after jumping and entering its 500 m area.
                    if not self.opening_airdrop:
                        loot_replies=self.ground_loot.announce()
                    elif (not self.ground_loot.announced and not self.seated and self.deployment_phase=='descending'
                          and any(math.dist(position,s.position)<=50000 for s in self.ground_loot.stacks.values())):
                        loot_replies=self.ground_loot.announce()
                    if self.scatter_loot:
                        loot_replies+=self.scatter(position)
                if self.inventory_selftest and self.inventory_test_started is None:
                    self.inventory_test_started=time.monotonic()
                if self.can_auto_board():
                    self.auto_board = False
                    return loot_replies+self.board()
                if self.vehicle_announced:
                    return loot_replies+self.initialize_vehicle_once()
                return loot_replies
        return []
