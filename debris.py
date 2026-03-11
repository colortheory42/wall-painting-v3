"""
Debris physics + structural failure system.
Includes:
- Pixel debris
- Cracks
- Stress accumulation
- Leaning walls
- Falling slabs
- Rubble piles
"""

import random
import math
from enum import Enum
from config import NEAR


# ============================================================
# DAMAGE STATES
# ============================================================

class DamageState(Enum):
    INTACT = 0
    CRACKED = 1
    FRACTURED = 2
    LEANING = 3
    FALLING = 4
    RUBBLE = 5


# ============================================================
# CRACKS (stress guides, not particles)
# ============================================================

class Crack:
    """
    Represents a growing crack on a wall surface.
    """

    def __init__(self, origin, angle):
        self.origin = origin        # (u, v) on wall face (0–1)
        self.angle = angle          # radians
        self.length = 0.0
        self.max_length = random.uniform(0.8, 2.5)
        self.growth_rate = random.uniform(0.4, 1.0)

    def grow(self, dt):
        if self.length < self.max_length:
            self.length += self.growth_rate * dt
            if self.length > self.max_length:
                self.length = self.max_length


# ============================================================
# PIXEL DEBRIS (unchanged, your original class)
# ============================================================

class Debris:
    """Individual pixel-sized piece of debris from destroyed walls."""

    def __init__(self, position, color, velocity=None):
        self.cx, self.cy, self.cz = position
        self.color = color
        self.active = True

        if velocity is None:
            self.vx = self.vy = self.vz = 0
            self.is_settled = True
        else:
            self.vx, self.vy, self.vz = velocity
            self.is_settled = False

        self.settle_timer = 0
        self.pixel_size = 0.15

        self.age = 0.0
        self.settled_age = 0.0
        self.max_age = random.uniform(8.0, 18.0)
        self.max_settled_age = random.uniform(2.0, 6.0)

    def update(self, dt, floor_y):
        if not self.active:
            return

        self.age += dt
        if self.age > self.max_age:
            self.active = False
            return

        if self.is_settled:
            self.settled_age += dt
            if self.settled_age > self.max_settled_age:
                self.active = False
            return

        self.vy -= 40 * dt
        self.cx += self.vx * dt
        self.cy += self.vy * dt
        self.cz += self.vz * dt

        if self.cy <= floor_y:
            self.cy = floor_y
            self.vy = -self.vy * 0.1
            self.vx *= 0.6
            self.vz *= 0.6

        speed = math.sqrt(self.vx**2 + self.vy**2 + self.vz**2)
        if speed < 0.5 and abs(self.cy - floor_y) < 0.5:
            self.settle_timer += dt
            if self.settle_timer > 0.3:
                self.is_settled = True
                self.vx = self.vy = self.vz = 0
                self.cy = floor_y
                self.settled_age = 0.0

    def get_screen_pos(self, engine):
        cam_pos = engine.world_to_camera(self.cx, self.cy, self.cz)
        if cam_pos[2] <= NEAR:
            return None
        return engine.project_camera(cam_pos)


# ============================================================
# RUBBLE CHUNKS (heavy, persistent)
# ============================================================

class RubbleChunk:
    """
    Heavy rubble piece that settles and persists.
    """

    def __init__(self, position, color, velocity):
        self.cx, self.cy, self.cz = position
        self.color = color
        self.vx, self.vy, self.vz = velocity

        self.size = random.uniform(0.25, 0.6)
        self.is_settled = False
        self.settle_timer = 0.0
        self.active = True

    def update(self, dt, floor_y):
        if not self.active:
            return

        self.vy -= 60 * dt
        self.cx += self.vx * dt
        self.cy += self.vy * dt
        self.cz += self.vz * dt

        if self.cy <= floor_y:
            self.cy = floor_y
            self.vy = -self.vy * 0.05
            self.vx *= 0.4
            self.vz *= 0.4

            speed = math.sqrt(self.vx**2 + self.vy**2 + self.vz**2)
            if speed < 0.3:
                self.settle_timer += dt
                if self.settle_timer > 0.5:
                    self.is_settled = True
                    self.vx = self.vy = self.vz = 0


# ============================================================
# DAMAGED WALL CONTROLLER (Steps 1–4)
# ============================================================

class DamagedWall:
    """
    Structural damage controller for a wall.
    """

    def __init__(self):
        self.state = DamageState.INTACT
        self.stress = 0.0
        self.cracks = []

        self.rotation = 0.0
        self.angular_velocity = 0.0
        self.max_lean = math.radians(8)
        self.pressure_y = random.uniform(0.1, 0.9)

        self.vy = 0.0
        self.has_impacted = False

        self.rubble_chunks = []
        self.dust_debris = []

    # ------------------------
    # APPLY DAMAGE
    # ------------------------

    def apply_hit(self, hit_uv, force=1.0):
        self.stress += force

        if self.state == DamageState.INTACT:
            self.state = DamageState.CRACKED
            self.cracks.append(Crack(hit_uv, random.uniform(0, math.pi)))

        elif self.state == DamageState.CRACKED and self.stress > 2.0:
            self.state = DamageState.FRACTURED
            self.cracks.append(Crack(hit_uv, random.uniform(0, math.pi)))

        elif self.state == DamageState.FRACTURED and self.stress > 4.0:
            self.state = DamageState.LEANING

    # ------------------------
    # UPDATE
    # ------------------------

    def update(self, dt, floor_y=0.0):
        for crack in self.cracks:
            crack.grow(dt)

        if self.state == DamageState.LEANING:
            torque = (1.0 - self.pressure_y) * 3.5
            self.angular_velocity += torque * dt
            self.angular_velocity *= 0.98
            self.rotation += self.angular_velocity * dt

            if self.rotation >= self.max_lean:
                self.state = DamageState.FALLING
                self.vy = 0.0

        elif self.state == DamageState.FALLING:
            self.vy -= 30.0 * dt
            if not self.has_impacted and abs(self.vy) > 6.0:
                self._on_impact()

        elif self.state == DamageState.RUBBLE:
            for chunk in self.rubble_chunks:
                chunk.update(dt, floor_y)
            for d in self.dust_debris:
                d.update(dt, floor_y)

    # ------------------------
    # IMPACT → RUBBLE
    # ------------------------

    def _on_impact(self):
        self.has_impacted = True
        self.state = DamageState.RUBBLE

        # Spawn rubble
        for _ in range(random.randint(4, 9)):
            self.rubble_chunks.append(
                RubbleChunk(
                    position=(0, 0, 0),
                    color=(180, 170, 160),
                    velocity=(
                        random.uniform(-1.5, 1.5),
                        random.uniform(0.5, 2.5),
                        random.uniform(-1.5, 1.5),
                    )
                )
            )

        # Spawn dust
        for _ in range(random.randint(20, 50)):
            self.dust_debris.append(
                Debris(
                    position=(0, 0, 0),
                    color=(200, 190, 180),
                    velocity=(
                        random.uniform(-2.5, 2.5),
                        random.uniform(1.0, 4.0),
                        random.uniform(-2.5, 2.5),
                    )
                )
            )

        self.vy = 0.0
        self.angular_velocity = 0.0
