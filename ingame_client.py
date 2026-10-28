"""Native overlay's bounded client for the per-session command mailbox."""
from pathlib import Path
import re

from offline_control import validate_command


class MailboxClient:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.sequence = 0
        self.pending = None
        self.token = None

    def state(self):
        path = self.directory / 'status.txt'
        if path.stat().st_size > 8192:
            raise ValueError('状态文件大小无效')
        state = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                     if '=' in line)
        token = state.get('token', '')
        if not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('会话标识无效')
        if self.token is not None and self.token != token:
            raise ValueError('会话已经更换，请重新启动菜单')
        self.token = token
        acknowledged = int(state.get('seq', '0'))
        self.sequence = max(self.sequence, acknowledged)
        if self.pending is not None and acknowledged >= self.pending:
            self.pending = None
        return state

    def send(self, command):
        command = validate_command(command)
        state = self.state()
        if state.get('ready') != '1':
            raise RuntimeError('等待角色进入地图后再操作')
        if self.pending is not None:
            raise RuntimeError('上一条操作正在等待服务回执')
        path = self.directory / 'commands.tsv'
        if path.stat().st_size > 260000:
            raise RuntimeError('本轮指令文件已满，请重新启动本轮服务')
        # A reopened overlay must not reuse a sequence already written but not
        # acknowledged. Only one overlay owns a session (Windows named mutex).
        for raw in path.read_text(encoding='ascii').splitlines():
            fields = raw.split('\t')
            if len(fields) == 7 and fields[0] == self.token:
                self.sequence = max(self.sequence, int(fields[1]))
        sequence = self.sequence + 1
        action = command['action']
        if action == 'weather':
            values = command['weather_id'], command['transition'], 0, 0
        elif action == 'weapon':
            values = command['template'], command['ammo'], command['distance'], command['count']
        else:
            values = command['config'], 0, command['distance'], 0
        line = '\t'.join(map(str, (self.token, sequence, action, *values))) + '\n'
        with path.open('a', encoding='ascii', newline='') as output:
            output.write(line)
        self.sequence = self.pending = sequence
        return sequence
