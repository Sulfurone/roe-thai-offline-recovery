"""Apply validated control commands on the game session's owning thread."""
import json
import struct
import math
import random

from offline_control import WEATHER_NAMES, WEAPON_NAMES, validate_command
from offline_environment import environment_weather
from offline_gameplay import OfflineGameplay, TYPED_VEHICLE_UID
from offline_ground_loot import MAX_GROUND_STACKS
from offline_inventory import Item
from offline_weapons import WEAPONS
import offline_world_state


def vehicle_spawn(template, uid, position):
    """Clone a locally prepared, original-codec-validated Jeep spawn body."""
    if not 40 <= len(template) <= 65536:
        raise ValueError('吉普车样本长度无效')
    size = struct.unpack_from('>I', template, 8)[0]
    start = 12 + size
    if not 1 <= size <= 128 or len(template) < start + 24 or template[start - 1] != 0:
        raise ValueError('吉普车样本名称边界无效')
    if struct.unpack_from('>I', template, start)[0] != 101:
        raise ValueError('载具样本必须是 config 101 吉普车')
    if len(position) != 3 or any(type(v) is not int or abs(v) >= 2_000_000 for v in position):
        raise ValueError('载具坐标越界')
    body = bytearray(template)
    struct.pack_into('>Q', body, 0, uid)
    struct.pack_into('>I', body, start + 8, 24000)
    struct.pack_into('>3i', body, start + 12, *position)
    return bytes(body)


class ControlSession:
    def __init__(self, gameplay=None, vehicle_template=None):
        self.gameplay = gameplay
        self.vehicle_template = vehicle_template
        self.vehicles = {}
        self.active_vehicle = None
        self.weather_id = None
        self.placement_map = None
        self.placement_random = random.Random()
        if vehicle_template is not None:
            vehicle_spawn(vehicle_template, TYPED_VEHICLE_UID, (0, 0, 0))

    def snapshot(self):
        game = self.gameplay
        return dict(connected=True, ready=bool(game and game.actor_ready),
                    seated=bool(game and game.seated),
                    position=list(game.player_position) if game and game.actor_ready else None,
                    weather_id=self.weather_id,
                    ground_items=len(game.ground_loot.stacks) if game and game.ground_loot else 0,
                    weapons_enabled=bool(game and game.ground_loot),
                    vehicles_enabled=bool(game and self.vehicle_template),
                    vehicles=[dict(uid=str(uid), name='吉普车', position=list(car.vehicle_position),
                                   seated=car.seated) for uid, car in self.vehicles.items()])

    def execute(self, command):
        command = validate_command({k: v for k, v in command.items() if k != 'id'})
        game = self.gameplay
        if game is None or not game.actor_ready:
            raise ValueError('等待角色进入地图')
        if command['action'] == 'weather':
            self.weather_id = command['weather_id']
            return [environment_weather(self.weather_id, command['transition'])], f"已发送{WEATHER_NAMES[self.weather_id]}，过渡 {command['transition']} 秒"
        if game.seated or game.opening_glider is not None and game.opening_glider.seated:
            raise ValueError('请先离开载具')
        if game.deployment_phase not in ('ground', 'landed'):
            raise ValueError('请在地面刷新物品')
        x, y, z = game.player_position
        distance = command['distance'] * 100
        if command['action'] == 'weapon':
            if game.ground_loot is None or not game.ground_loot.announced:
                raise ValueError('地面物品功能尚未就绪')
            count, ammo = command['count'], command['ammo']
            if len(game.ground_loot.stacks) + count + bool(ammo) > MAX_GROUND_STACKS:
                raise ValueError('地面物品已达上限，请先拾取已有物品')
            previous = game.state_payload()
            announced = game.ground_loot.announced
            replies = []
            spec = WEAPONS[command['template']]
            try:
                for index in range(count):
                    stack = game.ground_loot.add(Item(spec.kind, command['template'], game.inventory.next_uid, 1),
                                                (x + distance, y + index * 100, z), spec.capacity)
                    game.inventory.next_uid += 1
                    replies.append(stack.spawn())
                if ammo:
                    stack = game.ground_loot.add(Item(3, spec.ammunition, game.inventory.next_uid, ammo),
                                                (x + distance, y - 100, z))
                    game.inventory.next_uid += 1
                    replies.append(stack.spawn())
                game.save_state()
            except (OSError, ValueError):
                game.inventory, game.ground_loot, game.magazine, game.selected_slot = offline_world_state.restore(json.loads(previous))
                game.ground_loot.announced = announced
                game.reserve = game.inventory.reserve
                raise
            return replies, f"已发送 {count} 把 {WEAPON_NAMES[command['template']]} 与 {ammo} 发弹药，距角色 {command['distance']} 米"
        if self.placement_map is not None:
            spot = self.placement_map.spawn_spot(game.player_position,self.placement_random,'vehicle',
                [car.vehicle_position[:2] for car in self.vehicles.values()])
            if spot is None:
                raise ValueError('附近道路没有合适的停车位置')
            replies=self.spawn_vehicle(spot)
            actual=round(math.dist(game.player_position[:2],spot[:2])/100)
            return replies,f'已发送路边吉普车，距角色约 {actual} 米；X {spot[0]/100:.1f}，Y {spot[1]/100:.1f}'
        replies = self.spawn_vehicle((x + distance, y, z + 100))
        return replies, f"已发送吉普车，距角色 {command['distance']} 米"

    def spawn_vehicle(self, position):
        """Shared allocator/routing for manually and automatically placed Jeeps."""
        game = self.gameplay
        if self.vehicle_template is None:
            raise ValueError('此入口未提供吉普车样本')
        if len(self.vehicles) >= 8:
            raise ValueError('本轮最多刷新 8 辆吉普车')
        uid = TYPED_VEHICLE_UID + 0x1000 + len(self.vehicles)
        body = vehicle_spawn(self.vehicle_template, uid, position)
        car = OfflineGameplay(actor_uid=game.actor_uid, vehicle_uid=uid, initialize_vehicle=True)
        car.player_position, car.actor_ready = game.player_position, True
        car.observe_spawn(0x654b, body)
        self.vehicles[uid] = car
        return [(0x654b, body)] + car.initialize_vehicle_once()

    def handle(self, message, body):
        """Return None to defer to existing gameplay, or replies for a panel car."""
        game = self.gameplay
        if not game:
            return None
        car = None
        if message in (0x6541, 0x6549) and len(body) >= 8:
            car = self.vehicles.get(struct.unpack_from('>Q', body)[0])
        elif message == 0x6572 and len(body) >= 13:
            car = self.vehicles.get(struct.unpack_from('>Q', body, 5)[0])
        elif message in (0x6543, 0x6547):
            car = self.vehicles.get(self.active_vehicle)
        if car is None:
            return None
        if message == 0x6541 and game.seated:
            return []
        car.player_position = game.player_position
        replies = car.handle(message, body)
        if car.seated:
            self.active_vehicle = car.vehicle_uid
            game.seated, game.seat = True, car.seat
            game.vehicle_position = car.vehicle_position
            game.player_position = car.vehicle_position
        elif self.active_vehicle == car.vehicle_uid:
            self.active_vehicle = None
            game.seated, game.seat = False, 0
            game.player_position = car.player_position
        return replies
