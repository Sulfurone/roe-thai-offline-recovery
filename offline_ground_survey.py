"""Small ground patches inferred from actual Thai walking reports.

No height claim is made outside a six-metre neighbourhood of a surveyed
point. This supports nearby exploration loot, not full-map collision/AI.
"""
import math


class GroundSurvey:
    nearby_only = True

    def __init__(self):
        self.previous = None
        self.points = []

    def observe(self, position, event=0):
        if event not in (0, 2) or not 6500 <= position[2] < 50000:
            self.previous = None
            return
        previous, self.previous = self.previous, tuple(position)
        if previous is None:
            return
        travel = math.hypot(position[0] - previous[0], position[1] - previous[1])
        if travel > 5000 or abs(position[2] - previous[2]) > max(80, travel * .35):
            return
        if not self.points or math.dist(position, self.points[-1]) > 100:
            self.points.append(tuple(position))
            self.points = self.points[-1024:]

    def height_at(self, x, y):
        if not self.points:
            return None
        nearest = min(self.points, key=lambda point: math.hypot(x - point[0], y - point[1]))
        if math.hypot(x - nearest[0], y - nearest[1]) > 650:
            return None
        # Actual walking reports are foot coordinates, as independently
        # checked against the client's QSHM tiles. Initial scene spawn offsets
        # must not be subtracted from live movement reports.
        return nearest[2]
