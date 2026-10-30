"""Restricted per-session file mailbox for client Lua; no browser required."""
from contextlib import AbstractContextManager
import hashlib
import json
from pathlib import Path
import secrets
import tempfile


class IngameMailbox:
    def __init__(self, parent):
        parent = Path(parent)
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix='session-', dir=parent))
        self.token = secrets.token_hex(16)
        self.command_path = self.directory / 'commands.tsv'
        self.status_path = self.directory / 'status.txt'
        self.command_path.write_bytes(b'')
        self.offset = 0
        self.partial = b''
        self.sequence = 0
        self.command_ids = {}
        self.last_result = (0, 'waiting', '')
        self.last_status = None

    def poll(self, hub):
        if self.command_path.stat().st_size > 262144:
            self.last_result = (self.sequence, 'failed', '指令文件已达本轮上限，请重启本轮服务')
            return
        with self.command_path.open('rb') as source:
            source.seek(self.offset)
            data = source.read(4096)
            self.offset += len(data)
        self.partial += data
        lines = self.partial.split(b'\n')
        self.partial = lines.pop()
        if len(self.partial) > 512:
            self.partial = b''
            self.last_result = (self.sequence, 'failed', '指令长度无效')
        for raw in lines[:64]:
            try:
                fields = raw.decode('ascii').split('\t')
                if len(fields) != 7 or not secrets.compare_digest(fields[0], self.token):
                    raise ValueError('无效会话或指令格式')
                seq, ident, value, distance, count = (int(fields[i]) for i in (1, 3, 4, 5, 6))
                if not self.sequence < seq <= self.sequence + 1000:
                    raise ValueError('重复或过期指令')
                self.sequence = seq
                action = fields[2]
                if action == 'weather':
                    command = dict(action=action, weather_id=ident, transition=value)
                elif action == 'weapon':
                    command = dict(action=action, template=ident, ammo=value, distance=distance, count=count)
                elif action=='item':
                    command=dict(action=action,template=ident,distance=distance,count=count)
                elif action == 'vehicle':
                    command = dict(action=action, config=ident, distance=distance)
                elif action=='bots':
                    command=dict(action=action,mode=ident)
                else:
                    raise ValueError('未知指令')
                self.command_ids[hub.enqueue(command)] = seq
            except (ValueError, RuntimeError, UnicodeError) as error:
                self.last_result = (self.sequence, 'failed', str(error))

    def publish(self, snapshot):
        for event in reversed(snapshot['events']):
            seq = self.command_ids.get(event['id'])
            if seq is not None and event['status'] != 'queued' and seq > self.last_result[0]:
                self.last_result = (seq, event['status'], event['message'])
        seq, status, message = self.last_result
        message = message.replace('\n', ' ').replace('\r', ' ')[:240]
        body = f'token={self.token}\nready={int(snapshot["ready"])}\nseq={seq}\nstatus={status}\nmessage={message}\n'
        body+='bots_enabled='+str(int(snapshot.get('bots_enabled',False)))+'\nbot_mode='+str(snapshot.get('bot_mode') or '')+'\n'
        body+='round_state='+str(snapshot.get('round_state') or '')+'\n'
        position = snapshot.get('position')
        if position is not None:
            body += 'position=' + ','.join(map(str, position)) + '\n'
        for key,limit in (('vehicles',16),('peers',4)):
            body+=key+'='+json.dumps(snapshot.get(key,[])[:limit],ensure_ascii=False,separators=(',',':'))+'\n'
        if body != self.last_status:
            pending = self.status_path.with_suffix('.tmp')
            pending.write_text(body, encoding='utf-8')
            try:
                pending.replace(self.status_path)
                self.last_status = body
            except PermissionError:
                # Lua's brief read may prevent Windows replacement; retry next tick.
                pass


def lua_string(value):
    # Lua 5.1 supports JSON's simple ASCII escapes used in these paths/tokens.
    return json.dumps(str(value).replace('\\', '/'), ensure_ascii=False)


def bootstrap_source(mailbox, menu_source):
    prefix = (Path(__file__).resolve().parent / 'ingame' / 'bootstrap.lua').read_text(encoding='utf-8')
    prefix = prefix.replace('__ROE_DIRECTORY__', lua_string(mailbox.directory))
    prefix = prefix.replace('__ROE_TOKEN__', lua_string(mailbox.token))
    # Keep PanelLogic/setfenv scoped to its own function, leaving the bootstrap
    # in _G. Original PanelLogic changes its caller's Lua 5.1 environment.
    return prefix + '\nlocal function load_menu()\n' + menu_source + '\nend\nload_menu()\nROE_StartControlMenu()\n'


class IngameInstallation(AbstractContextManager):
    """Add only owned Lua/debug marker files; hash-check before removing."""

    def __init__(self, game, mailbox):
        self.game = Path(game).resolve()
        if not (self.game / 'Europa_Client.exe').is_file():
            raise ValueError('Expected the user-owned Thai client directory')
        self.mailbox = mailbox
        self.owned = []
        self.receipt = mailbox.directory / 'installed-files.json'

    def save_receipt(self):
        self.receipt.write_text(json.dumps({'game': str(self.game), 'owned': self.owned}, indent=2), encoding='utf-8')

    def add(self, relative, body, preserve_existing=False):
        target = self.game / relative
        if not target.resolve().is_relative_to(self.game):
            raise ValueError('Client file target leaves the client directory')
        for ancestor in [target, *target.parents]:
            if ancestor == self.game.parent:
                break
            if ancestor.exists() and (ancestor.is_symlink() or getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('Refusing linked/reparse client paths')
        if target.exists():
            if preserve_existing and target.is_file():
                return
            raise ValueError(f'Client target already exists: {relative}')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(body)
        self.owned.append({'path': relative, 'sha256': hashlib.sha256(body).hexdigest()})
        self.save_receipt()

    def __enter__(self):
        menu = (Path(__file__).resolve().parent / 'ingame/RoeControlPanel.lua').read_text(encoding='utf-8')
        body = bootstrap_source(self.mailbox, menu).encode('utf-8')
        self.save_receipt()
        try:
            self.add('ROE_OfflineMenu.lua', body)
            self.add('Data/ScriptCustom/ROE_OfflineMenu.lua', body)
            # Preload.lua prefers an explicit LoadConfig.lua over QSDir.
            # Loose files may not appear in the archive-backed directory list.
            self.add('Data/ScriptCustom/LoadConfig.lua',
                     b'_G.ROE_MENU_LOAD_SOURCE = "LoadConfig"\nreturn {{name="ROE_OfflineMenu.lua",type="file"}}\n')
            self.add('FileDriven/_GM_CONTROL_', b'', preserve_existing=True)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        remaining = []
        for record in reversed(self.owned):
            target = self.game / record['path']
            if (target.resolve().is_relative_to(self.game) and target.is_file()
                    and not target.is_symlink()
                    and hashlib.sha256(target.read_bytes()).hexdigest() == record['sha256']):
                target.unlink()
            elif target.exists():
                remaining.append(record)
        self.owned = list(reversed(remaining))
        self.save_receipt()


if __name__ == '__main__':
    import argparse
    import re
    from types import SimpleNamespace
    parser = argparse.ArgumentParser(description='Recover only files recorded by an interrupted native-menu session')
    parser.add_argument('action', choices=['cleanup'])
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    receipt = args.receipt.resolve()
    data = json.loads(receipt.read_text(encoding='utf-8'))
    allowed = {'ROE_OfflineMenu.lua', 'Data/ScriptCustom/ROE_OfflineMenu.lua',
               'Data/ScriptCustom/LoadConfig.lua', 'FileDriven/_GM_CONTROL_'}
    if (receipt.name != 'installed-files.json' or set(data) != {'game', 'owned'}
            or not isinstance(data['owned'], list)
            or any(not isinstance(item, dict) or set(item) != {'path', 'sha256'}
                   or item['path'] not in allowed or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                   for item in data['owned'])):
        raise ValueError('Unknown installation receipt schema')
    installation = IngameInstallation(data['game'], SimpleNamespace(directory=receipt.parent))
    installation.owned = data['owned']
    installation.__exit__(None, None, None)
    print(json.dumps({'remaining_changed_files': installation.owned}, indent=2))
