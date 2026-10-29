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
from offline_motion import actor_motion,actor_actions
from offline_doors import DoorState
from offline_inventory import Item,OfflineInventory
from offline_ground_loot import OfflineGroundLoot,MAX_GROUND_STACKS
from offline_weapons import WEAPONS,AMMUNITION,is_weapon
from offline_vehicles import LAND_VEHICLES
from offline_vitals import Vitals
from offline_throwables import Throws
from offline_medicine import MedicineUse
import offline_world_state

ACTOR_UID = 256
JEEP_UID = 0x200101
JEEP_CONFIG = 101
TYPED_ACTOR_UID = 0x0001000000000100
TYPED_VEHICLE_UID = 0x0005000000200101
# Original EuVehicleTable rows, decoded with the 0x74FEF0 reflection schema.
# id: (initial HP, initial oil, get-on distance in cm). Oil is zero in this
# Thai table, including max oil; do not invent a modern fuel mechanic.
VEHICLE_DEFAULTS = {i:(v.hp,0,v.geton_distance) for i,v in LAND_VEHICLES.items()}
VEHICLE_DEFAULTS.update({3:(100,0,0),4:(100,0,0)})


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
    auto_board_delay: float = 0
    auto_board_not_before: float | None = field(default=None,init=False)
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
    opening_glider_body: bytes | None = None
    opening_glider: object = field(default=None,init=False,repr=False)
    landing_height: object = field(default=None,repr=False)
    landing_previous_z: int | None = field(default=None,init=False)
    landing_stable_reports: int = field(default=0,init=False)
    ground_loot_enabled: bool = False
    arsenal_enabled: bool = False
    ground_loot: OfflineGroundLoot | None = field(default=None,init=False)
    world_file: Path | None = None
    state_save_count: int = field(default=0,init=False)
    scatter_loot: bool = False
    scatter_anchor: tuple | None = field(default=None,init=False)
    scatter_random: random.Random = field(default_factory=random.Random,init=False)
    door_interactions: bool = False
    doors: DoorState = field(default_factory=DoorState,init=False)
    pickup_drop_anchor: tuple | None = field(default=None,init=False)
    pickup_drop_time: float = field(default=0,init=False)
    last_drop_event: dict | None = field(default=None,init=False)
    require_self_position_for_drop: bool = False
    self_position: tuple | None = field(default=None,init=False)
    self_position_at: float | None = field(default=None,init=False)
    vitals_enabled: bool = False
    vitals: Vitals = field(default_factory=Vitals,init=False)
    vitals_sent: bool = field(default=False,init=False)
    throwables_enabled: bool = False
    throws: Throws = field(default_factory=Throws,init=False)
    medicine: MedicineUse = field(default_factory=MedicineUse,init=False)
    last_medicine_cancel: bool = field(default=False,init=False)

    def __post_init__(self):
        if not math.isfinite(self.auto_board_delay) or not 0<=self.auto_board_delay<=30:
            raise ValueError('Auto-board delay must be between zero and 30 seconds')
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
        if self.opening_glider_body is not None:
            if not self.opening_airdrop:
                raise ValueError('Opening glider requires the opening aircraft route')
            self.glider_spawn(self.player_position)
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
        if not self.vehicle_announced:
            self.auto_board_not_before=time.monotonic()+self.auto_board_delay
        self.vehicle_position=position
        self.vehicle_announced=True

    def can_auto_board(self,now=None):
        # The unoccupied glider does not send car physics reports. Its
        # diagnostic boarding gate uses the map actor's first movement.
        now=time.monotonic() if now is None else now
        return (self.auto_board and self.actor_ready and
                (self.auto_board_not_before is None or now>=self.auto_board_not_before) and
                (self.vehicle_ready or (self.vehicle_config in (3,4) and self.vehicle_announced)))

    def reserve_sync(self):
        if self.inventory is not None:
            keys=[key for key,item in self.inventory.items.items() if item.kind==3]
            return self.inventory.delta(keys or [(2,0)])
        # Thai 0x3E82: count byte; slot ushort; container byte; OBJECT_INFO;
        # current-map flag. This updates one bag slot without resetting guns.
        item=Item(3,30001,0x100102,self.reserve) if self.reserve else Item(0,0,0,0)
        body = struct.pack('>BHB',1,0,2)
        body += item.wire()+b'\1'
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

    def board(self, seat=1, now=None):
        if self.seated:
            return []
        now=time.monotonic() if now is None else now
        self.auto_board = False
        self.seated = True
        self.seat = seat
        if self.auto_exit_after>0:
            self.exit_deadline=now+self.auto_exit_after
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
                self.route_started=now
                self.route_next=self.route_started
                replies.append((0x6564,self.aircraft_move(self.vehicle_position)))
                if self.opening_airdrop:
                    self.jump_enable_deadline=self.route_started+3
                    self.exit_deadline=self.route_started+self.auto_exit_after
                    self.deployment_phase='boarding'
        return replies

    def aircraft_move(self,position,speed=None):
        # Thai 0x6563/64: UID, integer position+flag, direction floats,
        # movement speed DWORD. 0x130DDD0 normalizes the target delta;
        # 0x130E180 integrates that direction times speed and frame delta.
        direction=(0.,1.,0.)
        if self.aircraft_route_end is not None:
            origin=self.route_origin or self.vehicle_position
            length=math.dist(origin,self.aircraft_route_end)
            if length>0:
                direction=tuple((b-a)/length for a,b in zip(origin,self.aircraft_route_end))
        return struct.pack('>Q3iB3fI',self.vehicle_uid,*position,0,*direction,
                           self.aircraft_route_speed if speed is None else speed)

    def glider_spawn(self,position):
        body=bytearray(self.opening_glider_body)
        if len(body)<40 or len(body)>65536:
            raise ValueError('Opening glider spawn must be a bounded original 0x654B body')
        name_bytes=struct.unpack_from('>I',body,8)[0]
        start=12+name_bytes
        if not 1<=name_bytes<=128 or len(body)<start+24 or body[start-1]!=0:
            raise ValueError('Opening glider spawn name is malformed')
        if struct.unpack_from('>I',body,start)[0]!=3:
            raise ValueError('Opening canopy must use the original Thai glider config 3')
        uid=self.vehicle_uid+1
        struct.pack_into('>Q',body,0,uid)
        struct.pack_into('>3i',body,start+12,*position)
        return uid,bytes(body)

    def deploy_glider(self,now=None):
        if self.opening_glider_body is None or self.opening_glider is not None:
            return []
        now=time.monotonic() if now is None else now
        uid,body=self.glider_spawn(self.player_position)
        glider=OfflineGameplay(vehicle_config=3,actor_uid=self.actor_uid,
                               vehicle_uid=uid,initialize_vehicle=True,auto_exit_after=8)
        glider.observe_spawn(0x654b,body)
        glider.player_position=self.player_position
        self.opening_glider=glider
        self.deployment_phase='gliding'
        return [(0x654b,body)]+glider.board(now=now)

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
        if self.vitals_enabled and self.actor_ready and not self.vitals_sent:
            self.vitals_sent=True
            return [self.vitals.packet(self.actor_uid)]
        healing=self.medicine.tick(self.inventory,self.vitals,self.actor_uid,
            self.actor_ready and not self.seated,now)
        if healing:
            # Persist item consumption before acknowledging it to the client.
            self.save_state()
            return healing
        if not self.seated and self.can_auto_board(now) and self.route_started is None:
            return self.board(now=now)
        glider=self.opening_glider
        if glider is not None and glider.seated:
            replies=glider.tick(now)
            if replies and not glider.seated:
                # Seated clients do not provide continuous near-ground reports.
                self.player_position=glider.player_position
                self.deployment_phase='descending'
                return replies
        if self.route_started is not None and (self.seated or self.opening_airdrop):
            self.update_route_position(now)
        if self.exit_deadline is not None and now>=self.exit_deadline:
            replies=self.leave(now)
            if self.opening_airdrop:
                replies.append((0x6563,self.aircraft_move(self.vehicle_position,speed=0)))
                self.route_started=None
                replies+=self.deploy_glider(now)
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
            replies.append((0x6563,self.aircraft_move(self.vehicle_position,speed=0)))
            self.route_started=None
            return replies
        if (self.route_started is not None and now>=self.route_next
                and (self.seated or self.opening_airdrop)):
            self.route_next=now+.25
            # Native 0x130DAC0 sets the snap threshold to max(8000cm,
            # 3 * speed). Sending the full 4km endpoint exceeds it and the
            # original 0x130E180 teleports the aircraft there. A half-second
            # lead gives the native catch-up calculation 2 * distance = speed.
            target=self.route_position_at(now-self.route_started+.5)
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

    def accept_self_position(self,position,now=None):
        if (not self.actor_ready or self.seated or len(position)!=3
                or any(type(v) is not int or abs(v)>=2000000 for v in position)):
            return False
        self.self_position=tuple(position)
        self.self_position_at=time.monotonic() if now is None else now
        self.player_position=tuple(position)
        return True

    def has_fresh_self_position(self,now=None):
        now=time.monotonic() if now is None else now
        return (self.self_position is not None and self.self_position_at is not None
                and 0<=now-self.self_position_at<=1)

    def _handle(self, message, body):
        self.last_drop_event=None
        self.last_medicine_cancel=False
        if self.vitals_enabled and not self.vitals.current:
            if message==0x49c and self.valid_length(body,4):
                return [(0x49d,struct.pack('>II',struct.unpack_from('>I',body)[0],1))]
            if message==0x3e80 and body and self.inventory is not None:
                return [self.inventory.reply(body[0],1)]
            if message in (0x11d3,0x49e,0x3b63,0x6541,0x6f57):return []
        if self.vitals_enabled and message==0x2a and 20 in (actor_actions(body) or ()):
            self.last_medicine_cancel=self.medicine.cancel()
        if self.vitals_enabled and message==0x3e80 and body[:1]==b'\3':
            return self.medicine.begin(body,self.inventory,self.vitals,
                self.actor_ready and not self.seated
                and not (self.opening_glider is not None and self.opening_glider.seated))
        if self.throwables_enabled and message in (0x1004,0x1007):
            return self.throws.handle(message,body,self.inventory,self.actor_uid,
                self.actor_ready and not self.seated and self.vitals.current>0
                and not (self.opening_glider is not None and self.opening_glider.seated))
        if message == 0x6f57 and self.door_interactions:
            return self.doors.handle(body)
        glider=self.opening_glider
        if glider is not None and glider.seated:
            if message in (0x6543,0x6549):
                replies=glider.handle(message,body)
                if not glider.seated:
                    self.player_position=glider.player_position
                    self.deployment_phase='descending'
                return replies
            if message==0x002a:
                motion=actor_motion(body)
                if motion is not None:
                    position,_=motion
                    glider.player_position=glider.vehicle_position=position
                    ground=self.landing_height(*position[:2]) if self.landing_height else None
                    if ground is not None and abs(position[2]-ground)<=300:
                        replies=glider.leave()
                        self.deployment_phase='landing'
                        # Keep the existing position/loot path and announce at landing.
                        return replies+self._handle(message,body)
        if message==0x3b63 and self.ground_loot is not None:
            stack=(self.ground_loot.stacks.get(struct.unpack_from('>I',body)[0])
                   if len(body) in (33,41) else None)
            replies=self.ground_loot.pickup(body,self.inventory,self.actor_uid,self.player_position,
                                            self.actor_ready and not self.seated
                                            and not (glider is not None and glider.seated))
            if stack is not None and any(msg==0x3e82 for msg,_ in replies):
                camera=struct.unpack_from('>3i',body,20)
                # The drop DTO has no position. Successful pickup supplies a
                # newer camera than intermittent walking keyframes. Use its
                # XY with the nearby item's floor, never the elevated camera Z.
                if (any(camera) and all(abs(v)<2000000 for v in camera)
                        and math.dist(camera,stack.position)<=500):
                    self.pickup_drop_anchor=(*camera[:2],stack.position[2])
                    self.pickup_drop_time=time.monotonic()
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
            return replies
        if message==0x3e80 and self.inventory is not None:
            if body[:1]==b'\2' and self.ground_loot is not None:
                magazine=(self.weapon_magazine((body[1],struct.unpack_from('>H',body,2)[0]))
                          if len(body)>=15 else 0)
                anchor=self.pickup_drop_anchor
                fresh_self=self.has_fresh_self_position()
                if self.require_self_position_for_drop and not fresh_self:
                    self.last_drop_event=dict(accepted=False,reason='self_position_not_fresh')
                    key=(body[1],struct.unpack_from('>H',body,2)[0]) if len(body) in (15,23) else None
                    restore_slot=([self.inventory.delta([key])]
                                  if key in self.inventory.items and self.inventory.valid_slot(key) else [])
                    return restore_slot+[self.inventory.reply(2,1)]
                use_anchor=(anchor is not None and 0<=time.monotonic()-self.pickup_drop_time<=30
                            and math.dist(anchor,self.player_position)>500)
                position=((*self.self_position[:2],self.self_position[2]+30) if fresh_self else
                          anchor if use_anchor else self.player_position)
                replies=self.ground_loot.drop(body,self.inventory,self.actor_uid,position,
                                             self.actor_ready and not self.seated
                                             and not (glider is not None and glider.seated),magazine)
                if any(msg==0x821 for msg,_ in replies):
                    stack=list(self.ground_loot.stacks.values())[-1]
                    self.last_drop_event=dict(entity=stack.entity,template=stack.item.template,
                        position=list(stack.position),source='client_self_read' if fresh_self else
                        'recent_pickup_camera_floor' if use_anchor else 'actor_keyframe')
            else:
                replies=self.inventory.handle(body)
            self.reserve=self.inventory.reserve
            survivors={item.uid for item in self.inventory.items.values() if is_weapon(item)}
            for uid in [uid for uid in self.inventory.weapon_magazines if uid not in survivors]:
                del self.inventory.weapon_magazines[uid]
            self.refresh_magazine()
            if not survivors:
                self.selected_slot=0
            return replies
        if message in (0x049e,0x049c) and self.valid_length(body,4):
            slot = struct.unpack_from('>I',body)[0]
            if message == 0x049e:
                if slot in (0,1,2,3,4,5,6):
                    self.selected_slot = slot
                    self.refresh_magazine()
                # This reports the active slot, not a reload request. 4A0's
                # native callback emits WEAPON_RELOADED even for equal rounds.
                # Inventory DTO row 7 already initializes each gun's magazine.
                return []
            if not self.has_weapon(slot):
                return [(0x049d,struct.pack('>II',slot,1))]
            if slot!=self.selected_slot:
                return [(0x049d,struct.pack('>II',slot,1))]
            key=(1,slot)
            item=self.inventory.items[key] if self.inventory is not None else None
            spec=WEAPONS[item.template] if item is not None else WEAPONS[10201]
            available=self.inventory.reserve_for(spec.ammunition) if self.inventory is not None else self.reserve
            current=self.weapon_magazine(key)
            amount = min(max(0,spec.capacity-current),available)
            if amount==0:
                return [(0x049d,struct.pack('>II',slot,0))]
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
            # The native firing path consumes its own displayed round. An
            # equal 4A0 receipt emits WEAPON_RELOADED and can end animations.
            return []
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
            seats=LAND_VEHICLES[self.vehicle_config].seats if self.vehicle_config in LAND_VEHICLES else 4
            if uid != self.vehicle_uid or seat > seats:
                return []
            distance=VEHICLE_DEFAULTS[self.vehicle_config][2]
            if distance<=0 or sum((a-b)**2 for a,b in zip(self.player_position,self.vehicle_position)) > distance**2:
                return []
            return self.board(seat or 1)
        if message == 0x6543 and self.valid_length(body,1):
            if self.opening_airdrop:
                if self.jump_enable_deadline is not None and time.monotonic()<self.jump_enable_deadline:
                    return []
                return self.leave()+self.deploy_glider() if self.seated else []
            return self.leave()
        if message==0x6547 and self.valid_length(body,4) and self.vehicle_config in LAND_VEHICLES and self.seated:
            # Original 0x1288750 sends a one-based destination seat.
            # Callback 0x1288620 consumes vehicle/actor IDs, old/new seats,
            # then error; it converts both seats back to zero-based.
            destination=struct.unpack_from('>I',body)[0]
            previous=self.seat
            error=0 if 1<=destination<=LAND_VEHICLES[self.vehicle_config].seats else 1
            if not error:
                self.seat=destination
            return [(0x6548,struct.pack('>QQIII',self.vehicle_uid,self.actor_uid,
                                       previous,destination,error))]
        if message == 0x6572 and self.valid_length(body,14) and self.vehicle_config in LAND_VEHICLES:
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
            return self.leave()+self.deploy_glider()
        if message == 0x002a:
            motion=actor_motion(body)
            if motion is not None:
                position,_ = motion
                self.player_position = position
                self.pickup_drop_anchor=None
                self.actor_ready = True
                if self.deployment_phase=='landing' and self.landing_height is not None:
                    ground=self.landing_height(*position[:2])
                    stable=(ground is not None and abs(position[2]-ground)<=400
                            and self.landing_previous_z is not None
                            and abs(position[2]-self.landing_previous_z)<=25)
                    self.landing_stable_reports=self.landing_stable_reports+1 if stable else 0
                    self.landing_previous_z=position[2]
                    if self.landing_stable_reports>=2:
                        self.deployment_phase='landed'
                loot_replies=[]
                if self.ground_loot is not None:
                    # In the combined opening test, avoid delivering a distant
                    # ground test range while the player is aboard the aircraft.
                    # Announce once after jumping and entering its 500 m area.
                    if not self.opening_airdrop:
                        loot_replies=self.ground_loot.announce()
                    elif (not self.ground_loot.announced and not self.seated
                          and self.deployment_phase in ('descending','landing','landed')
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
