"""
Wall Drawing System.
Lets the player draw on walls and pillars in world space.
Pure data/logic layer — no rendering here.
Rendering is handled inline inside engine._draw_connecting_wall()
and engine._draw_single_pillar().
"""

import math
from raycasting import ray_intersects_triangle
from config import PILLAR_SPACING, PILLAR_SIZE, WALL_THICKNESS, get_scaled_wall_height, get_scaled_floor_y


# ── Color palette ─────────────────────────────────────────────────────────────

DRAW_COLORS = {
    1: ((220,  50,  50), "Red"),
    2: ((240, 140,  30), "Orange"),
    3: ((240, 220,  50), "Yellow"),
    4: ((50,  200,  80), "Green"),
    5: ((60,  120, 240), "Blue"),
    6: ((80,   60, 200), "Indigo"),
    7: ((180,  80, 220), "Violet"),
    8: ((20,   20,  20), "Black"),
    9: ((240, 240, 240), "White"),
}


# ── UV helpers ────────────────────────────────────────────────────────────────

def world_to_wall_uv(hit_point, wall_key):
    """
    Convert a world-space hit point on a wall to (u, v) in [0, 1].
    wall_key is tuple(sorted([(x1,z1),(x2,z2)])).
    """
    (x1, z1), (x2, z2) = wall_key
    h = get_scaled_wall_height()
    floor_y = get_scaled_floor_y()
    wall_height = h - floor_y

    hx, hy, hz = hit_point

    if x1 == x2:  # vertical wall — spans z
        length = abs(z2 - z1)
        u = (hz - min(z1, z2)) / length if length > 0 else 0.0
    else:          # horizontal wall — spans x
        length = abs(x2 - x1)
        u = (hx - min(x1, x2)) / length if length > 0 else 0.0

    v = 1.0 - (hy - floor_y) / wall_height if wall_height > 0 else 0.0
    return (max(0.0, min(1.0, u)), max(0.0, min(1.0, v)))


def pillar_world_to_uv(hit_point, pillar_key, face):
    """
    Convert a world-space hit point on a pillar face to (u, v).
    face: 0=front(z=pz), 1=back(z=pz+s), 2=left(x=px), 3=right(x=px+s)
    """
    px, pz = pillar_key
    s = PILLAR_SIZE
    h = get_scaled_wall_height()
    floor_y = get_scaled_floor_y()
    wall_height = h - floor_y

    hx, hy, hz = hit_point

    if face == 0:
        u = (hx - px) / s if s > 0 else 0.0
    elif face == 1:
        u = 1.0 - (hx - px) / s if s > 0 else 0.0
    elif face == 2:
        u = (hz - pz) / s if s > 0 else 0.0
    else:
        u = 1.0 - (hz - pz) / s if s > 0 else 0.0

    v = 1.0 - (hy - floor_y) / wall_height if wall_height > 0 else 0.0
    return (max(0.0, min(1.0, u)), max(0.0, min(1.0, v)))


def get_wall_hit_point(engine, target_info):
    """
    Cast a ray from screen center and find the exact world hit point on the wall.
    Returns (hit_point, wall_key) or (None, None).
    """
    target_type, target_key = target_info
    if target_type != 'wall':
        return None, None

    ray_origin, ray_dir = engine.get_ray_from_screen_center()
    (x1, z1), (x2, z2) = target_key

    h = get_scaled_wall_height()
    floor_y = get_scaled_floor_y()
    half_thick = WALL_THICKNESS / 2

    if x1 == x2:
        x = x1
        quads = [
            [(x - half_thick, h, z1), (x - half_thick, h, z2),
             (x - half_thick, floor_y, z2), (x - half_thick, floor_y, z1)],
            [(x + half_thick, h, z2), (x + half_thick, h, z1),
             (x + half_thick, floor_y, z1), (x + half_thick, floor_y, z2)],
        ]
    else:
        z = z1
        quads = [
            [(x1, h, z - half_thick), (x2, h, z - half_thick),
             (x2, floor_y, z - half_thick), (x1, floor_y, z - half_thick)],
            [(x2, h, z + half_thick), (x1, h, z + half_thick),
             (x1, floor_y, z + half_thick), (x2, floor_y, z + half_thick)],
        ]

    best_t = float('inf')
    best_hit = None

    for quad in quads:
        v0, v1, v2, v3 = quad
        for tri in [(v0, v1, v2), (v0, v2, v3)]:
            result = ray_intersects_triangle(ray_origin, ray_dir, *tri)
            if result and result[0] < best_t:
                best_t = result[0]
                t = result[0]
                best_hit = (
                    float(ray_origin[0] + ray_dir[0] * t),
                    float(ray_origin[1] + ray_dir[1] * t),
                    float(ray_origin[2] + ray_dir[2] * t),
                )

    return best_hit, target_key


def get_pillar_hit_point_and_face(engine, target_info):
    """
    Cast a ray from screen center and find exact hit point + face on a pillar.
    Returns (hit_point, pillar_key, face_index) or (None, None, None).
    """
    target_type, target_key = target_info
    if target_type != 'pillar':
        return None, None, None

    ray_origin, ray_dir = engine.get_ray_from_screen_center()
    px, pz = target_key
    s = PILLAR_SIZE
    h = get_scaled_wall_height()
    floor_y = get_scaled_floor_y()

    faces = [
        (0, [(px,     h, pz),     (px + s, h, pz),     (px + s, floor_y, pz),     (px,     floor_y, pz)]),
        (1, [(px + s, h, pz + s), (px,     h, pz + s), (px,     floor_y, pz + s), (px + s, floor_y, pz + s)]),
        (2, [(px,     h, pz),     (px,     h, pz + s), (px,     floor_y, pz + s), (px,     floor_y, pz)]),
        (3, [(px + s, h, pz + s), (px + s, h, pz),     (px + s, floor_y, pz),     (px + s, floor_y, pz + s)]),
    ]

    best_t = float('inf')
    best_hit = None
    best_face = None

    for face_idx, quad in faces:
        v0, v1, v2, v3 = quad
        for tri in [(v0, v1, v2), (v0, v2, v3)]:
            result = ray_intersects_triangle(ray_origin, ray_dir, *tri)
            if result and result[0] < best_t:
                best_t = result[0]
                t = result[0]
                best_hit = (
                    float(ray_origin[0] + ray_dir[0] * t),
                    float(ray_origin[1] + ray_dir[1] * t),
                    float(ray_origin[2] + ray_dir[2] * t),
                )
                best_face = face_idx

    return best_hit, target_key, best_face


# ── Main class ────────────────────────────────────────────────────────────────

class WallDrawing:
    """Stores all player-drawn strokes on walls and pillars."""

    def __init__(self):
        # wall_key -> list of strokes; each stroke = list of (u, v, color)
        self.wall_drawings = {}

        # pillar_key -> {face_idx: [strokes]}
        self.pillar_drawings = {}

        # Active stroke state
        self.current_stroke = []
        self.current_wall = None
        self.current_pillar = None
        self.current_pillar_face = None
        self.drawing_active = False

        # Brush
        self.brush_size = 0.015
        self.current_color_index = 8
        self.draw_color = DRAW_COLORS[8][0]

    # ── Color ─────────────────────────────────────────────────────────────────

    def set_color(self, index):
        if index in DRAW_COLORS:
            self.current_color_index = index
            self.draw_color = DRAW_COLORS[index][0]

    def color_name(self):
        return DRAW_COLORS.get(self.current_color_index, ((0, 0, 0), "?"))[1]

    def mode_name(self):
        return "DRAW"

    # ── Stroke control ────────────────────────────────────────────────────────

    def start_stroke(self, wall_key, uv):
        self.current_wall = wall_key
        self.current_pillar = None
        self.current_stroke = [(uv[0], uv[1], self.draw_color)]
        self.drawing_active = True

    def start_pillar_stroke(self, pillar_key, face, uv):
        self.current_pillar = pillar_key
        self.current_pillar_face = face
        self.current_wall = None
        self.current_stroke = [(uv[0], uv[1], self.draw_color)]
        self.drawing_active = True

    def add_to_stroke(self, uv):
        if self.drawing_active and uv is not None:
            self.current_stroke.append((uv[0], uv[1], self.draw_color))

    def end_stroke(self):
        if not self.drawing_active:
            return
        if len(self.current_stroke) >= 2:
            if self.current_wall is not None:
                key = self.current_wall
                if key not in self.wall_drawings:
                    self.wall_drawings[key] = []
                self.wall_drawings[key].append(list(self.current_stroke))
            elif self.current_pillar is not None:
                pk = self.current_pillar
                fi = self.current_pillar_face
                if pk not in self.pillar_drawings:
                    self.pillar_drawings[pk] = {}
                if fi not in self.pillar_drawings[pk]:
                    self.pillar_drawings[pk][fi] = []
                self.pillar_drawings[pk][fi].append(list(self.current_stroke))
        self.current_stroke = []
        self.current_wall = None
        self.current_pillar = None
        self.drawing_active = False

    # ── Persistence ───────────────────────────────────────────────────────────

    def get_state_for_save(self):
        def key_to_str(k):
            return f"{k[0][0]},{k[0][1]},{k[1][0]},{k[1][1]}"

        def pkey_to_str(k):
            return f"{k[0]},{k[1]}"

        wall_d = {}
        for k, strokes in self.wall_drawings.items():
            wall_d[key_to_str(k)] = [
                [[u, v, list(c)] for u, v, c in stroke]
                for stroke in strokes
            ]

        pillar_d = {}
        for pk, faces in self.pillar_drawings.items():
            pillar_d[pkey_to_str(pk)] = {
                str(fi): [[[u, v, list(c)] for u, v, c in stroke] for stroke in strokes]
                for fi, strokes in faces.items()
            }

        return {
            'wall_drawings': wall_d,
            'pillar_drawings': pillar_d,
        }

    def load_state(self, data):
        if not data:
            return

        def str_to_key(s):
            parts = list(map(int, s.split(',')))
            return tuple(sorted([(parts[0], parts[1]), (parts[2], parts[3])]))

        def str_to_pkey(s):
            parts = list(map(int, s.split(',')))
            return (parts[0], parts[1])

        self.wall_drawings = {}
        for ks, strokes in data.get('wall_drawings', {}).items():
            k = str_to_key(ks)
            self.wall_drawings[k] = [
                [(u, v, tuple(c)) for u, v, c in stroke]
                for stroke in strokes
            ]

        self.pillar_drawings = {}
        for pks, faces in data.get('pillar_drawings', {}).items():
            pk = str_to_pkey(pks)
            self.pillar_drawings[pk] = {
                int(fi): [[(u, v, tuple(c)) for u, v, c in stroke] for stroke in strokes]
                for fi, strokes in faces.items()
            }
