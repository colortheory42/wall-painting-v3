"""
Raycasting utilities.
Möller–Trumbore algorithm for ray-triangle intersection.
Audio raycasting for geometry-aware spatial sound.
"""

import math
import numpy as np

# Audio ray constants
AUDIO_RAY_STEP = 20.0       # world-units per march step
AUDIO_RAY_MAX  = 2000.0     # max range before "open" is assumed
AUDIO_RAY_COUNT = 16        # rays cast per update


def cast_audio_ray(origin_x, origin_z, angle, has_wall_fn, max_dist=AUDIO_RAY_MAX, step=AUDIO_RAY_STEP):
    """
    March a 2D horizontal ray from (origin_x, origin_z) in world_angle direction.
    has_wall_fn(x1, z1, x2, z2) is the engine's _has_wall_between — called on the
    nearest grid edges as the ray crosses them (DDA-style).

    Returns the distance to the first wall hit, or max_dist if nothing hit.
    """
    dx = math.cos(angle)
    dz = math.sin(angle)

    from config import PILLAR_SPACING

    # DDA: step to each grid crossing
    grid = PILLAR_SPACING

    # Current position
    x, z = origin_x, origin_z
    dist  = 0.0

    while dist < max_dist:
        # Advance one step
        dist += step
        x += dx * step
        z += dz * step

        # Snap to nearest grid cell
        gx = int(x // grid) * grid
        gz = int(z // grid) * grid

        # Check the four walls of the cell we're in
        # horizontal top/bottom and vertical left/right
        if has_wall_fn(gx, gz, gx + grid, gz):
            # Are we close to this wall?
            if abs(z - gz) < step * 1.5:
                return dist
        if has_wall_fn(gx, gz, gx + grid, gz + grid) if False else \
           has_wall_fn(gx, gz + grid, gx + grid, gz + grid):
            if abs(z - (gz + grid)) < step * 1.5:
                return dist
        if has_wall_fn(gx, gz, gx, gz + grid):
            if abs(x - gx) < step * 1.5:
                return dist
        if has_wall_fn(gx + grid, gz, gx + grid, gz + grid):
            if abs(x - (gx + grid)) < step * 1.5:
                return dist

    return max_dist


def sample_room_acoustics(origin_x, origin_z, player_yaw, has_wall_fn):
    """
    Cast AUDIO_RAY_COUNT rays in all directions and return an AcousticSample.
    """
    angles = [(i / AUDIO_RAY_COUNT) * 2 * math.pi for i in range(AUDIO_RAY_COUNT)]
    dists  = [cast_audio_ray(origin_x, origin_z, a, has_wall_fn) for a in angles]
    return AcousticSample(angles, dists, player_yaw)


def occlusion_between(origin_x, origin_z, target_x, target_z, has_wall_fn, destroyed_walls=None):
    """
    March from origin to target and count wall crossings.
    Returns a 0–1 factor (1 = clear, 0 = heavily occluded).
    Each wall hit attenuates by ~exp(-1.4) ≈ 0.25.
    """
    dx = target_x - origin_x
    dz = target_z - origin_z
    dist = math.sqrt(dx * dx + dz * dz)
    if dist < 1.0:
        return 1.0

    nx, nz  = dx / dist, dz / dist
    steps   = max(3, int(dist / AUDIO_RAY_STEP))
    step    = dist / steps
    walls   = 0

    from config import PILLAR_SPACING

    grid = PILLAR_SPACING
    prev_gx = int(origin_x // grid) * grid
    prev_gz = int(origin_z // grid) * grid

    for s in range(1, steps):
        t  = s * step
        wx = origin_x + nx * t
        wz = origin_z + nz * t

        gx = int(wx // grid) * grid
        gz = int(wz // grid) * grid

        # Detect grid boundary crossings
        if gx != prev_gx:
            wall_key = tuple(sorted([(gx, gz), (gx, gz + grid)]))
            if destroyed_walls and wall_key in destroyed_walls:
                pass
            elif has_wall_fn(gx, gz, gx, gz + grid):
                walls += 1
        if gz != prev_gz:
            wall_key = tuple(sorted([(gx, gz), (gx + grid, gz)]))
            if destroyed_walls and wall_key in destroyed_walls:
                pass
            elif has_wall_fn(gx, gz, gx + grid, gz):
                walls += 1

        prev_gx, prev_gz = gx, gz

    return math.exp(-walls * 1.4)


class AcousticSample:
    """
    Snapshot of room acoustics around a point.
    Derived from a ring of audio rays.
    """

    def __init__(self, angles, dists, player_yaw):
        self.angles = angles
        self.dists  = dists
        self.yaw    = player_yaw
        self._compute()

    def _compute(self):
        n = len(self.dists)

        self.avg_dist = sum(self.dists) / n

        # Left/right nearest reflector (relative to player facing)
        left_min  = AUDIO_RAY_MAX
        right_min = AUDIO_RAY_MAX

        for angle, d in zip(self.angles, self.dists):
            rel = (angle - self.yaw + math.pi) % (2 * math.pi) - math.pi
            if rel < 0:          # left of player
                left_min  = min(left_min,  d)
            else:                # right of player
                right_min = min(right_min, d)

        self.left_dist  = left_min
        self.right_dist = right_min

        open_count = sum(1 for d in self.dists if d >= AUDIO_RAY_MAX * 0.95)
        self.openness = open_count / n   # 1.0 = fully open, 0.0 = sealed

        # Reverb mix: tight room → more reverb
        self.reverb = 1.0 - min(1.0, self.avg_dist / AUDIO_RAY_MAX)

    def stereo_for_world_angle(self, world_angle):
        """
        Return (left_vol, right_vol) for a sound at world_angle, shaped
        by real reflector distances on each side.
        """
        rel  = (world_angle - self.yaw + math.pi) % (2 * math.pi) - math.pi
        pan  = math.sin(rel)   # -1 = hard left, +1 = hard right

        # Walls close on one side → that side's reflection pushes energy back
        l_norm = min(1.0, self.left_dist  / 300.0)
        r_norm = min(1.0, self.right_dist / 300.0)
        bias   = (r_norm - l_norm) * 0.18
        pan    = max(-1.0, min(1.0, pan + bias))

        # Constant-power panning
        t          = (pan + 1.0) * 0.5 * (math.pi * 0.5)
        left_vol   = math.cos(t)
        right_vol  = math.sin(t)
        return left_vol, right_vol


def ray_intersects_triangle(ray_origin, ray_dir, v0, v1, v2):
    """
    Möller–Trumbore intersection algorithm.
    Returns (distance, triangle) if hit, None otherwise.
    """
    epsilon = 0.0000001

    edge1 = np.array(v1) - np.array(v0)
    edge2 = np.array(v2) - np.array(v0)

    h = np.cross(ray_dir, edge2)
    a = np.dot(edge1, h)

    if -epsilon < a < epsilon:
        return None

    f = 1.0 / a
    s = np.array(ray_origin) - np.array(v0)
    u = f * np.dot(s, h)

    if u < 0.0 or u > 1.0:
        return None

    q = np.cross(s, edge1)
    v = f * np.dot(ray_dir, q)

    if v < 0.0 or u + v > 1.0:
        return None

    t = f * np.dot(edge2, q)

    if t > epsilon:
        return (t, (v0, v1, v2))

    return None
