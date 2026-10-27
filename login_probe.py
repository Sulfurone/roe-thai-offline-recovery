"""Observe local client traffic; this is NOT a login/game server emulator."""
import argparse
import datetime
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--training", action="store_true")
    parser.add_argument("--no-launcher", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = root / "recovery" / "logs" / stamp
    folder.mkdir(parents=True)
    log = (folder / "probe.jsonl").open("w", encoding="utf-8")

    def emit(event, **fields):
        item = {"time": datetime.datetime.now().astimezone().isoformat(), "event": event, **fields}
        log.write(json.dumps(item) + "\n")
        log.flush()
        print(json.dumps(item), flush=True)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 8001))
        listener.listen(8)
        listener.setblocking(False)
        selector = selectors.DefaultSelector()
        selector.register(listener, selectors.EVENT_READ)
        emit("listening", address="127.0.0.1:8001", note="Diagnostic only; no protocol replies")
        if args.launch:
            command = [str(root / "32838" / "Europa_Client.exe"),
                       "-noLauncher" if args.no_launcher else "-garena", "-uid=1",
                       "-language=en", "-server=127.0.0.1:8001"]
            if args.training:
                command += ["-UseListenServer=1", "-TrainListenServer=1"]
            try:
                process = subprocess.Popen(command, cwd=root / "32838")
                emit("launched", pid=process.pid, arguments=command[1:])
            except OSError as error:
                if getattr(error, "winerror", None) != 740:
                    raise
                # This original client has an administrator manifest. Use the
                # ordinary Windows launch path and let Windows handle its UI.
                os.startfile(command[0], arguments=subprocess.list2cmdline(command[1:]),
                             cwd=str(root / "32838"))
                emit("shell_launch_requested", arguments=command[1:])
        deadline = time.monotonic() + args.seconds
        streams = {}
        total = 0
        try:
            while time.monotonic() < deadline:
                for key, _ in selector.select(timeout=min(1, max(0, deadline - time.monotonic()))):
                    if key.fileobj is listener:
                        connection, address = listener.accept()
                        connection.setblocking(False)
                        total += 1
                        streams[connection] = [total, 0]
                        selector.register(connection, selectors.EVENT_READ)
                        emit("connected", connection=total, address=list(address))
                    else:
                        connection = key.fileobj
                        number, count = streams[connection]
                        try:
                            data = connection.recv(65536)
                        except ConnectionResetError:
                            data = b""
                        if data:
                            # Limit stored traffic per connection and never echo packet bodies.
                            remaining = max(0, 1024 * 1024 - count)
                            with (folder / f"connection-{number}.bin").open("ab") as raw:
                                raw.write(data[:remaining])
                            streams[connection][1] += len(data)
                            emit("received", connection=number, bytes=len(data))
                        else:
                            emit("disconnected", connection=number, bytes=count)
                            selector.unregister(connection)
                            connection.close()
                            del streams[connection]
        finally:
            for connection in streams:
                selector.unregister(connection)
                connection.close()
            selector.close()
            emit("finished", connections=total)
            log.close()


if __name__ == "__main__":
    main()
