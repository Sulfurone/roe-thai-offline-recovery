"""Loopback-only control panel; game socket writes stay on the session thread."""
from collections import deque
from contextlib import AbstractContextManager
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time

from offline_environment import NATIVE_WEATHER_IDS
from offline_weapons import WEAPONS
from offline_items import EXTRA_ITEMS,SPAWNABLE_EXTRA_ITEMS
from offline_vehicles import LAND_VEHICLES

WEATHER_NAMES = dict(zip(sorted(NATIVE_WEATHER_IDS), (
    '原生默认', '晴天', '小雨', '大雨', '雷雨', '雷电', '阴天', '大风',
    '多云', '潮湿', '薄霾', '浓雾', '小雪', '大雪', '轻沙尘', '强沙尘',
    '火山天气', '花瓣', '蒲公英', '火山喷发', '沙漠雪', '尘雪', '台风', '流星')))
WEAPON_NAMES = dict(zip(sorted(WEAPONS), (
    'R700', 'Mosin-Nagant', 'MSR', 'G28', 'VKS', 'M4A1', 'AK47', 'SCAR-H',
    'LVOA', 'Groza', 'AUG', 'MP5', 'Uzi', 'Vector', 'R870', 'Citori', 'FO12',
    'USP45', 'Glock17', 'Desert Eagle')))
AMMO_NAMES = {30001: '5.56 mm', 30002: '7.62 mm', 30003: '9 mm',
              30004: '12 号霰弹', 30005: '.45 ACP', 30006: '.50'}


def integer(data, name, minimum, maximum, default=None):
    value = data.get(name, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} 必须是 {minimum}–{maximum} 之间的整数')
    return value


def validate_command(data):
    if not isinstance(data, dict):
        raise ValueError('操作必须是 JSON 对象')
    action = data.get('action')
    if action == 'weather':
        if set(data) - {'action', 'weather_id', 'transition'}:
            raise ValueError('未知天气参数')
        weather = integer(data, 'weather_id', 1, 25)
        if weather not in NATIVE_WEATHER_IDS:
            raise ValueError('该天气没有泰服资源')
        return dict(action=action, weather_id=weather,
                    transition=integer(data, 'transition', 0, 600, 30))
    if action == 'weapon':
        if set(data) - {'action', 'template', 'count', 'ammo', 'distance'}:
            raise ValueError('未知武器参数')
        template = integer(data, 'template', 1, 99999)
        if template not in WEAPONS:
            raise ValueError('不支持的武器')
        return dict(action=action, template=template,
                    count=integer(data, 'count', 1, 5, 1),
                    ammo=integer(data, 'ammo', 0, 999, 60),
                    distance=integer(data, 'distance', 2, 20, 3))
    if action == 'vehicle':
        if set(data) - {'action', 'config', 'distance'}:
            raise ValueError('未知载具参数')
        config=integer(data,'config',min(LAND_VEHICLES),max(LAND_VEHICLES),101)
        return dict(action=action, config=config,
                    distance=integer(data, 'distance', 5, 20, 6))
    if action=='item':
        if set(data)-{'action','template','count','distance'}:
            raise ValueError('未知物品参数')
        template=integer(data,'template',1,999999)
        if template not in EXTRA_ITEMS:
            raise ValueError('不支持的物品')
        if template not in SPAWNABLE_EXTRA_ITEMS:
            raise ValueError('当前泰服缺少此投掷物的原生配置，暂不能使用；请选择手雷或烟雾弹')
        return dict(action=action,template=template,
                    count=integer(data,'count',1,min(5,EXTRA_ITEMS[template].max_stack),1),
                    distance=integer(data,'distance',2,20,3))
    raise ValueError('未知操作')


class ControlHub:
    """Small locked mailbox shared by HTTP handlers and the game thread."""

    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.pending = deque()
        self.events = deque(maxlen=20)
        self.state = dict(connected=False, ready=False, seated=False, position=None,
                          weather_id=None, ground_items=0, vehicles=[],
                          weapons_enabled=False, vehicles_enabled=False)

    def update(self, **values):
        with self.lock:
            self.state.update(copy.deepcopy(values))

    def disconnect(self):
        with self.lock:
            while self.pending:
                command = self.pending.popleft()
                self._event(command['id'], 'cancelled', '连接已结束，操作已取消')
            self.state.update(connected=False, ready=False, seated=False)

    def _event(self, ident, status, message):
        self.events.appendleft(dict(id=ident, status=status, message=message,
                                   time=time.strftime('%H:%M:%S')))

    def finish(self, ident, status, message):
        with self.lock:
            self._event(ident, status, message)

    def enqueue(self, data):
        command = validate_command(data)
        with self.lock:
            if not self.state['connected'] or not self.state['ready']:
                raise RuntimeError('等待游戏进入地图后再操作')
            if command['action'] != 'weather' and self.state['seated']:
                raise RuntimeError('请先离开载具，再刷新物品')
            capability = {'weapon': 'weapons_enabled','item':'weapons_enabled', 'vehicle': 'vehicles_enabled'}.get(command['action'])
            if capability and not self.state[capability]:
                raise RuntimeError('当前入口未启用此功能，请使用控制台专用入口')
            if len(self.pending) >= 24:
                raise RuntimeError('操作队列已满，请稍后再试')
            command['id'] = secrets.token_hex(8)
            self.pending.append(command)
            self._event(command['id'], 'queued', '操作已排队')
            return command['id']

    def take(self):
        with self.lock:
            return self.pending.popleft() if self.pending else None

    def snapshot(self):
        with self.lock:
            return dict(**copy.deepcopy(self.state), token=self.token,
                        pending=len(self.pending), events=list(self.events),
                        weather=[dict(id=k, name=v) for k, v in WEATHER_NAMES.items()],
                        weapons=[dict(id=k, name=WEAPON_NAMES[k], capacity=v.capacity,
                                      ammo=AMMO_NAMES[v.ammunition],
                                      category=('手枪' if v.kind == 2 else
                                                {101: '狙击步枪', 102: '突击步枪',
                                                 103: '冲锋枪', 104: '霰弹枪'}[k // 100]))
                                 for k, v in WEAPONS.items()])


class ControlServer(AbstractContextManager):
    def __init__(self, hub, port=8765):
        self.hub = hub
        assets = Path(__file__).resolve().parent / 'control_ui'
        allowed = {'/': ('index.html', 'text/html; charset=utf-8'),
                   '/app.css': ('app.css', 'text/css; charset=utf-8'),
                   '/app.js': ('app.js', 'text/javascript; charset=utf-8')}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, data, kind='application/json; charset=utf-8'):
                body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
                self.send_response(status)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def valid_host(self):
                return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',
                                                    f'localhost:{self.server.server_port}')

            def do_GET(self):
                if not self.valid_host():
                    return self.reply(403, {'error': 'Invalid host'})
                if self.path == '/api/state':
                    return self.reply(200, hub.snapshot())
                resource = allowed.get(self.path)
                if resource:
                    try:
                        return self.reply(200, (assets / resource[0]).read_bytes(), resource[1])
                    except OSError:
                        return self.reply(500, {'error': '界面资源缺失'})
                self.reply(404, {'error': 'Not found'})

            def do_POST(self):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2048:
                        raise ValueError('请求大小无效')
                    self.connection.settimeout(3)
                    body = self.rfile.read(length)
                except (ValueError, OSError) as error:
                    return self.reply(400, {'error': str(error)})
                origin = self.headers.get('Origin')
                if (not self.valid_host() or
                        origin is not None and origin != 'http://' + self.headers.get('Host', '') or
                        not secrets.compare_digest(self.headers.get('X-Control-Token', ''), hub.token)):
                    return self.reply(403, {'error': '请从本机控制台提交操作'})
                if self.path != '/api/commands':
                    return self.reply(404, {'error': 'Not found'})
                try:
                    data = json.loads(body)
                    ident = hub.enqueue(data)
                    self.reply(202, {'id': ident})
                except (ValueError, UnicodeError) as error:
                    self.reply(400, {'error': str(error)})
                except RuntimeError as error:
                    self.reply(409, {'error': str(error)})

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.hub.disconnect()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Preview the local control panel without a game connection')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    hub = ControlHub()
    hub.update(preview=True)
    with ControlServer(hub, args.port) as panel:
        print(panel.url, flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
