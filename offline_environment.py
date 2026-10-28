"""Thai environment clock and weather initialization.

The client owns the actual sky and weather resources.  The server anchors its
environment clock and selects a native weather preset after the world is
usable; ``EnvrTimeTable``, ``EnvrWeatherTable`` and
``EnvrMapWeatherResourceTable`` then select the matching resources.

Sending the clock from the map-load callback is too early for this Thai build:
real-client A/B runs reached one position report and then stopped.  Keep the
small readiness scheduler here so every launcher uses the same, testable gate.
"""
from dataclasses import dataclass
import struct
import time


# IDs backed by the Thai client's EnvrWeatherTable.  ID 23 is accepted by the
# native range check, but has no table/resource row in this build and is kept
# out of the public interface.  ID 1 is the native default/reset state; ID 2
# is explicit clear weather.
NATIVE_WEATHER_IDS = frozenset((*range(1, 23), 24, 25))


def environment_clock(hour, timestamp=None):
    # Thai registry 0x4816 -> 0x1278B60 -> 0x12BAD70. The first
    # DWORD selects the initial clock slot; the second anchors server time.
    if type(hour) is not int or not 0 <= hour < 24:
        raise ValueError('Environment hour must be an integer from 0 to 23')
    timestamp = int(time.time()) if timestamp is None else timestamp
    if type(timestamp) is not int or not 0 <= timestamp <= 0xffffffff:
        raise ValueError('Environment timestamp must fit an unsigned DWORD')
    return 0x4816, struct.pack('>II', hour, timestamp)


def environment_weather(weather_id, transition_seconds=30, mode=0, result=0):
    """Encode the Thai native weather-state message (0x4817).

    Original-codec emulation proves that the callback ignores ``result`` and
    calls the environment manager with ``weather_id``, ``transition_seconds``
    and ``mode``.  The manager converts the transition to a renderer float.
    Only mode zero is accepted by the original wire decoder in this build.
    """
    if type(weather_id) is not int or weather_id not in NATIVE_WEATHER_IDS:
        raise ValueError('Weather ID must be a native Thai table ID (1..22, 24 or 25)')
    if type(transition_seconds) is not int or not 0 <= transition_seconds <= 600:
        raise ValueError('Weather transition must be an integer from 0 to 600 seconds')
    if type(mode) is not int or mode != 0:
        raise ValueError('Thai weather mode must be zero')
    if type(result) is not int or result != 0:
        raise ValueError('Thai weather result field must be zero')
    return 0x4817, struct.pack('>4I', result, weather_id, transition_seconds, mode)


@dataclass
class EnvironmentSchedule:
    """One-shot clock delivery armed by the first valid player position.

    A short delay lets the client finish the callback that published its first
    ``SCENE_MSGID_MOVE_1``.  This is deliberately independent of gameplay
    timers: daytime/weather can be tested on a minimal ground session too.
    """

    hour: int
    delay: float = 1.0
    armed_at: float | None = None
    sent: bool = False
    position_reports: int = 0

    def __post_init__(self):
        environment_clock(self.hour, 0)
        if type(self.delay) not in (int, float) or not 0 <= self.delay <= 30:
            raise ValueError('Environment ready delay must be from 0 to 30 seconds')
        self.delay = float(self.delay)

    @staticmethod
    def valid_position(body):
        if len(body) < 16:
            return False
        position = struct.unpack_from('>3i', body, 4)
        return all(abs(value) < 2_000_000 for value in position)

    def observe(self, message_id, body, now=None):
        """Arm once after a native current-map position report."""
        if message_id != 0x002a or not self.valid_position(body):
            return False
        self.position_reports += 1
        if self.sent or self.armed_at is not None:
            return False
        now = time.monotonic() if now is None else now
        self.armed_at = now + self.delay
        return True

    def due(self, now=None):
        now = time.monotonic() if now is None else now
        return not self.sent and self.armed_at is not None and now >= self.armed_at

    def take(self, now=None, timestamp=None):
        """Return the clock packet once when due; otherwise return ``None``."""
        if not self.due(now):
            return None
        self.sent = True
        return environment_clock(self.hour, timestamp)


@dataclass
class WeatherSchedule:
    """One-shot native weather delivery armed by the first valid position."""

    weather_id: int
    transition_seconds: int = 30
    delay: float = 2.0
    armed_at: float | None = None
    sent: bool = False
    position_reports: int = 0

    def __post_init__(self):
        environment_weather(self.weather_id, self.transition_seconds)
        if type(self.delay) not in (int, float) or not 0 <= self.delay <= 30:
            raise ValueError('Weather ready delay must be from 0 to 30 seconds')
        self.delay = float(self.delay)

    def observe(self, message_id, body, now=None):
        if message_id != 0x002a or not EnvironmentSchedule.valid_position(body):
            return False
        self.position_reports += 1
        if self.sent or self.armed_at is not None:
            return False
        now = time.monotonic() if now is None else now
        self.armed_at = now + self.delay
        return True

    def due(self, now=None):
        now = time.monotonic() if now is None else now
        return not self.sent and self.armed_at is not None and now >= self.armed_at

    def take(self, now=None):
        if not self.due(now):
            return None
        self.sent = True
        return environment_weather(self.weather_id, self.transition_seconds)
