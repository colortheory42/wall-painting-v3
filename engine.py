"""
Backrooms Engine - Main rendering and world engine.
Handles 3D rendering, procedural generation, physics, and destruction.
"""

import math
import random
import numpy as np
import pygame

from config import *
from debris import Debris
from procedural import ProceduralZone
from textures import (generate_carpet_texture, generate_ceiling_tile_texture,
                      generate_wall_texture, generate_pillar_texture)
from raycasting import ray_intersects_triangle, sample_room_acoustics, occlusion_between
from drawing_system import WallDrawing, world_to_wall_uv, pillar_world_to_uv


class BackroomsEngine:
    def __init__(self, width, height, world_seed=None):
        self.width = width
        self.height = height

        _MAX_SEED = 9223372033963249499
        self.world_seed = min(_MAX_SEED, world_seed) if world_seed is not None else random.randint(0, _MAX_SEED)

        # Map position — which cell on the seed map this world occupies
        # Mirrors cell_to_seed() in seed_map.py: seed = col + row * MAP_W
        MAP_W = 3_037_000_499
        MAP_H = 3_037_000_500
        self.map_col = self.world_seed % MAP_W
        self.map_row = self.world_seed // MAP_W
        self.MAP_W = MAP_W
        self.MAP_H = MAP_H

        # Player position — spawns at the world origin of this seed's map cell
        self.x = float(self.map_col * ZONE_SIZE + 200)
        self.y = CAMERA_HEIGHT_STAND
        self.z = float(self.map_row * ZONE_SIZE + 200)
        self._has_moved = False
        self.target_y = CAMERA_HEIGHT_STAND

        # Player rotation
        self.pitch = 0
        self.yaw = 0

        # Smoothed camera values
        self.x_s = self.x
        self.y_s = CAMERA_HEIGHT_STAND
        self.z_s = self.z
        self.pitch_s = 0
        self.yaw_s = 0

        # Input
        self.mouse_look = False

        # Caches
        self.pillar_cache = {}
        self.wall_cache = {}
        self.zone_cache = {}

        # Destruction system
        self.destroyed_walls = set()
        self.destroyed_pillars = set()
        self.pre_damaged_walls = {}  # wall_key -> damage_state (0.0-1.0)
        self.debris_pieces = []
        self._spawned_rubble = set()

        # Animation
        self.head_bob_time = 0
        self.is_moving = False
        self.is_rotating = False
        self.camera_shake_time = random.random() * 100
        self.last_footstep_phase = 0

        # Movement states
        self.is_running = False
        self.is_crouching = False
        self.crouch_key_pressed = False

        # Jumping
        self.is_jumping = False
        self.jump_velocity = 0
        self.on_ground = True

        # Lighting effects
        self.flicker_timer = 0
        self.is_flickering = False
        self.flicker_brightness = 1.0

        # Ambient sounds
        self.next_footstep = random.uniform(*FOOTSTEP_INTERVAL)
        self.next_buzz = random.uniform(*BUZZ_INTERVAL)
        self.sound_timer = 0

        # Audio raycasting — live acoustic snapshot, updated each frame
        self.acoustic_sample = None

        # Drawing system
        self.drawing_system = WallDrawing()

        # Stats
        self.play_time = 0

        # Render scaling
        self.render_scale = RENDER_SCALE
        self.target_render_scale = RENDER_SCALE
        self.render_scale_transition_speed = 2.0
        self.render_surface = None
        self.update_render_surface()

        # Generate textures
        print("Generating procedural textures...")
        self.carpet_texture = generate_carpet_texture()
        self.ceiling_texture = generate_ceiling_tile_texture()
        self.wall_texture = generate_wall_texture()
        self.pillar_texture = generate_pillar_texture()

        self.carpet_avg = self._get_average_color(self.carpet_texture)
        self.ceiling_avg = self._get_average_color(self.ceiling_texture)
        self.wall_avg = self._get_average_color(self.wall_texture)
        self.pillar_avg = self._get_average_color(self.pillar_texture)

        print(f"World seed: {self.world_seed}")
        print("Textures generated!")

    def _get_average_color(self, surface):
        """Extract average color from a surface."""
        arr = pygame.surfarray.array3d(surface)
        return tuple(int(arr[:, :, i].mean()) for i in range(3))

    # === RENDER SCALING ===

    def update_render_surface(self):
        render_width = int(self.width * self.render_scale)
        render_height = int(self.height * self.render_scale)
        self.render_surface = pygame.Surface((render_width, render_height))

    def toggle_render_scale(self):
        if self.target_render_scale == 1.0:
            self.target_render_scale = 0.5
            print("Render scale transitioning to: 0.5x")
        else:
            self.target_render_scale = 1.0
            print("Render scale transitioning to: 1.0x")

    def update_render_scale(self, dt):
        if abs(self.render_scale - self.target_render_scale) > 0.01:
            if self.render_scale < self.target_render_scale:
                self.render_scale = min(self.target_render_scale,
                                        self.render_scale + self.render_scale_transition_speed * dt)
            else:
                self.render_scale = max(self.target_render_scale,
                                        self.render_scale - self.render_scale_transition_speed * dt)
            self.update_render_surface()
        else:
            if self.render_scale != self.target_render_scale:
                self.render_scale = self.target_render_scale
                self.update_render_surface()

    # === ZONE SYSTEM ===

    def get_zone_at(self, x, z):
        zone_x = int(x // ZONE_SIZE)
        zone_z = int(z // ZONE_SIZE)
        return (zone_x, zone_z)

    def get_zone_properties(self, zone_x, zone_z):
        key = (zone_x, zone_z)
        if key not in self.zone_cache:
            self.zone_cache[key] = ProceduralZone.get_zone_properties(zone_x, zone_z, self.world_seed)
        return self.zone_cache[key]

    # === RAYCASTING FOR WALL TARGETING ===

    def get_ray_from_screen_center(self):
        """Get ray from center of screen for wall targeting."""
        mx, my = self.width // 2, self.height // 2

        ndc_x = (mx / self.width - 0.5) * 2
        ndc_y = (my / self.height - 0.5) * 2

        ray_dir_cam = np.array([ndc_x * self.width / FOV,
                                ndc_y * self.height / FOV,
                                1.0])
        ray_dir_cam = ray_dir_cam / np.linalg.norm(ray_dir_cam)

        # Transform to world space
        cp = math.cos(-self.pitch_s)
        sp = math.sin(-self.pitch_s)
        x1 = ray_dir_cam[0]
        y1 = ray_dir_cam[1] * cp - ray_dir_cam[2] * sp
        z1 = ray_dir_cam[1] * sp + ray_dir_cam[2] * cp

        cy = math.cos(-self.yaw_s)
        sy = math.sin(-self.yaw_s)
        x2 = x1 * cy - z1 * sy
        z2 = x1 * sy + z1 * cy

        ray_dir = np.array([x2, y1, z2])
        ray_dir = ray_dir / np.linalg.norm(ray_dir)

        ray_origin = np.array([self.x_s, self.y_s, self.z_s])

        return ray_origin, ray_dir

    def find_targeted_wall_or_pillar(self):
        """Find wall segment or pillar being looked at."""
        ray_origin, ray_dir = self.get_ray_from_screen_center()
        max_distance = 100

        closest_hit = None
        closest_dist = float('inf')
        hit_type = None

        render_range = 200
        start_x = int((self.x_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_x = int((self.x_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING
        start_z = int((self.z_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_z = int((self.z_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING

        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()

        # Check walls (existing code)
        for px in range(start_x, end_x + PILLAR_SPACING, PILLAR_SPACING):
            for pz in range(start_z, end_z + PILLAR_SPACING, PILLAR_SPACING):
                # Horizontal walls
                if self._has_wall_between(px, pz, px + PILLAR_SPACING, pz):
                    wall_key = tuple(sorted([(px, pz), (px + PILLAR_SPACING, pz)]))
                    if wall_key not in self.destroyed_walls:
                        half_thick = WALL_THICKNESS / 2
                        z = pz
                        x1, x2 = px, px + PILLAR_SPACING

                        v0 = (x1, h, z - half_thick)
                        v1 = (x2, h, z - half_thick)
                        v2 = (x2, floor_y, z - half_thick)
                        v3 = (x1, floor_y, z - half_thick)

                        for tri in [(v0, v1, v2), (v0, v2, v3)]:
                            hit = ray_intersects_triangle(ray_origin, ray_dir, *tri)
                            if hit and hit[0] < max_distance and hit[0] < closest_dist:
                                closest_dist = hit[0]
                                closest_hit = wall_key
                                hit_type = 'wall'

                # Vertical walls
                if self._has_wall_between(px, pz, px, pz + PILLAR_SPACING):
                    wall_key = tuple(sorted([(px, pz), (px, pz + PILLAR_SPACING)]))
                    if wall_key not in self.destroyed_walls:
                        half_thick = WALL_THICKNESS / 2
                        x = px
                        z1, z2 = pz, pz + PILLAR_SPACING

                        v0 = (x - half_thick, h, z1)
                        v1 = (x - half_thick, h, z2)
                        v2 = (x - half_thick, floor_y, z2)
                        v3 = (x - half_thick, floor_y, z1)

                        for tri in [(v0, v1, v2), (v0, v2, v3)]:
                            hit = ray_intersects_triangle(ray_origin, ray_dir, *tri)
                            if hit and hit[0] < max_distance and hit[0] < closest_dist:
                                closest_dist = hit[0]
                                closest_hit = wall_key
                                hit_type = 'wall'

        # Check pillars (NEW CODE)
        offset = PILLAR_SPACING // 2
        for px in range(start_x, end_x + PILLAR_SPACING, PILLAR_SPACING):
            for pz in range(start_z, end_z + PILLAR_SPACING, PILLAR_SPACING):
                pillar_x = px + offset
                pillar_z = pz + offset

                if self._get_pillar_at(pillar_x, pillar_z):
                    pillar_key = (pillar_x, pillar_z)
                    if pillar_key not in self.destroyed_pillars:
                        s = PILLAR_SIZE

                        # Check all 4 faces
                        faces = [
                            [(pillar_x, h, pillar_z), (pillar_x + s, h, pillar_z),
                             (pillar_x + s, floor_y, pillar_z), (pillar_x, floor_y, pillar_z)],
                            [(pillar_x + s, h, pillar_z + s), (pillar_x, h, pillar_z + s),
                             (pillar_x, floor_y, pillar_z + s), (pillar_x + s, floor_y, pillar_z + s)],
                            [(pillar_x, h, pillar_z), (pillar_x, h, pillar_z + s),
                             (pillar_x, floor_y, pillar_z + s), (pillar_x, floor_y, pillar_z)],
                            [(pillar_x + s, h, pillar_z + s), (pillar_x + s, h, pillar_z),
                             (pillar_x + s, floor_y, pillar_z), (pillar_x + s, floor_y, pillar_z + s)]
                        ]

                        for face in faces:
                            v0, v1, v2, v3 = face
                            for tri in [(v0, v1, v2), (v0, v2, v3)]:
                                hit = ray_intersects_triangle(ray_origin, ray_dir, *tri)
                                if hit and hit[0] < max_distance and hit[0] < closest_dist:
                                    closest_dist = hit[0]
                                    closest_hit = pillar_key
                                    hit_type = 'pillar'

        if closest_hit:
            return (hit_type, closest_hit)
        return None


    # === WALL DESTRUCTION ===

    def destroy_wall(self, wall_key, destroy_sound):
        """Destroy a wall and create pixel debris."""
        if wall_key in self.destroyed_walls:
            return

        self.destroyed_walls.add(wall_key)
        destroy_sound.play()

        (x1, z1), (x2, z2) = wall_key
        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()
        half_thick = WALL_THICKNESS / 2

        # Determine wall bounds
        if x1 == x2:  # Vertical wall
            x = x1
            min_x, max_x = x - half_thick, x + half_thick
            min_z, max_z = min(z1, z2), max(z1, z2)
        else:  # Horizontal wall
            z = z1
            min_z, max_z = z - half_thick, z + half_thick
            min_x, max_x = min(x1, x2), max(x1, x2)

        min_y, max_y = floor_y, h

        # Spawn debris particles
        base = 1200
        num_particles = max(250, int(base * (1.0 / (1.0 + len(self.destroyed_walls) / 20))))

        for i in range(num_particles):
            px = random.uniform(min_x, max_x)
            py = random.uniform(min_y, max_y)
            pz = random.uniform(min_z, max_z)

            center_x = (min_x + max_x) / 2
            center_z = (min_z + max_z) / 2

            dx = px - center_x
            dz = pz - center_z
            dist = math.sqrt(dx ** 2 + dz ** 2) + 0.1

            speed = random.uniform(8, 20)
            vx = (dx / dist) * speed + random.uniform(-3, 3)
            vy = random.uniform(-20, -5)
            vz = (dz / dist) * speed + random.uniform(-3, 3)

            color_var = random.randint(-30, 30)
            particle_color = (
                max(0, min(255, WALL_COLOR[0] + color_var)),
                max(0, min(255, WALL_COLOR[1] + color_var)),
                max(0, min(255, WALL_COLOR[2] + color_var))
            )

            self.debris_pieces.append(Debris(
                (px, py, pz),
                particle_color,
                velocity=(vx, vy, vz)
            ))

    def destroy_pillar(self, pillar_key, destroy_sound):
        """Destroy a pillar and create debris."""
        if pillar_key in self.destroyed_pillars:
            return

        self.destroyed_pillars.add(pillar_key)
        destroy_sound.play()

        pillar_x, pillar_z = pillar_key
        s = PILLAR_SIZE
        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()

        min_x, max_x = pillar_x, pillar_x + s
        min_z, max_z = pillar_z, pillar_z + s
        min_y, max_y = floor_y, h

        base = 1200
        num_particles = max(250, int(base * (1.0 / (1.0 + len(self.destroyed_pillars) / 20))))

        for i in range(num_particles):
            px = random.uniform(min_x, max_x)
            py = random.uniform(min_y, max_y)
            pz = random.uniform(min_z, max_z)

            center_x = (min_x + max_x) / 2
            center_z = (min_z + max_z) / 2

            dx = px - center_x
            dz = pz - center_z
            dist = math.sqrt(dx ** 2 + dz ** 2) + 0.1

            speed = random.uniform(8, 20)
            vx = (dx / dist) * speed + random.uniform(-3, 3)
            vy = random.uniform(-20, -5)
            vz = (dz / dist) * speed + random.uniform(-3, 3)

            color_var = random.randint(-30, 30)
            particle_color = (
                max(0, min(255, PILLAR_COLOR[0] + color_var)),
                max(0, min(255, PILLAR_COLOR[1] + color_var)),
                max(0, min(255, PILLAR_COLOR[2] + color_var))
            )

            self.debris_pieces.append(Debris(
                (px, py, pz),
                particle_color,
                velocity=(vx, vy, vz)
            ))
    # === SOUND SYSTEM ===

    def _refresh_acoustics(self):
        """Cast audio rays from the player to build a live acoustic snapshot."""
        self.acoustic_sample = sample_room_acoustics(
            self.x_s, self.z_s, self.yaw_s,
            self._has_wall_between
        )

    def update_sounds(self, dt, sound_effects):
        # Refresh acoustic snapshot every frame (rays are cheap 2-D marches)
        self._refresh_acoustics()

        self.sound_timer += dt

        if self.sound_timer >= self.next_footstep:
            # Place the virtual footstep emitter somewhere in the world at a
            # random distance and direction, then occlude it through walls.
            angle = random.uniform(0, 2 * math.pi)
            emit_dist = random.uniform(200, 600)
            ex = self.x_s + math.cos(angle) * emit_dist
            ez = self.z_s + math.sin(angle) * emit_dist
            occ = occlusion_between(self.x_s, self.z_s, ex, ez,
                                    self._has_wall_between, self.destroyed_walls)
            self.play_directional_sound(sound_effects['footstep'], angle, occlusion=occ)
            self.next_footstep = self.sound_timer + random.uniform(*FOOTSTEP_INTERVAL)

        if self.sound_timer >= self.next_buzz:
            angle = random.uniform(0, 2 * math.pi)
            emit_dist = random.uniform(100, 400)
            ex = self.x_s + math.cos(angle) * emit_dist
            ez = self.z_s + math.sin(angle) * emit_dist
            occ = occlusion_between(self.x_s, self.z_s, ex, ez,
                                    self._has_wall_between, self.destroyed_walls)
            self.play_directional_sound(sound_effects['buzz'], angle, occlusion=occ)
            self.next_buzz = self.sound_timer + random.uniform(*BUZZ_INTERVAL)

    def play_directional_sound(self, sound, world_angle, occlusion=1.0):
        """
        Play a sound spatialised by real room geometry.

        world_angle  — direction the sound is coming from (world radians)
        occlusion    — 0-1 factor from occlusion_between(); 1 = clear line of sight
        """
        if self.acoustic_sample is None:
            self._refresh_acoustics()

        left_vol, right_vol = self.acoustic_sample.stereo_for_world_angle(world_angle)

        # Base volume shaped by room openness:
        #   open spaces feel quieter (sound escapes), tight rooms feel louder
        room_gain = 0.5 + self.acoustic_sample.reverb * 0.35

        # Occlusion cuts volume — muffled through walls
        final_left  = left_vol  * room_gain * occlusion
        final_right = right_vol * room_gain * occlusion

        channel = sound.play()
        if channel:
            channel.set_volume(
                max(0.0, min(1.0, final_left)),
                max(0.0, min(1.0, final_right))
            )

    def update_player_footsteps(self, dt, footstep_sound, crouch_footstep_sound):
        if self.is_moving:
            current_phase = self.head_bob_time % 1.0
            if ((self.last_footstep_phase > 0.5 and current_phase < 0.5) or
                    (self.last_footstep_phase > current_phase and current_phase < 0.1)):
                if self.is_crouching:
                    crouch_footstep_sound.play()
                else:
                    footstep_sound.play()
            self.last_footstep_phase = current_phase
        else:
            self.last_footstep_phase = 0

    def update_flicker(self, dt):
        if self.is_flickering:
            self.flicker_timer += dt
            if self.flicker_timer >= FLICKER_DURATION:
                self.is_flickering = False
                self.flicker_brightness = 1.0
        else:
            if random.random() < FLICKER_CHANCE:
                self.is_flickering = True
                self.flicker_timer = 0
                self.flicker_brightness = 1.0 - FLICKER_BRIGHTNESS

    # === VISUAL EFFECTS ===

    def apply_fog(self, color, distance):
        if not FOG_ENABLED:
            return tuple(int(c * self.flicker_brightness) for c in color)

        if distance < FOG_START:
            return tuple(int(c * self.flicker_brightness) for c in color)
        if distance > FOG_END:
            fog_color = tuple(int(c * self.flicker_brightness) for c in FOG_COLOR)
            return fog_color

        fog_amount = (distance - FOG_START) / (FOG_END - FOG_START)
        adjusted_color = tuple(int(c * self.flicker_brightness) for c in color)
        fog_color = tuple(int(c * self.flicker_brightness) for c in FOG_COLOR)

        return tuple(
            int(adjusted_color[i] * (1 - fog_amount) + fog_color[i] * fog_amount)
            for i in range(3)
        )

    def apply_surface_noise(self, color, x, z):
        noise = ((int(x) * 13 + int(z) * 17) % 5) - 2
        return tuple(max(0, min(255, c + noise)) for c in color)

    def apply_zone_tint(self, color, zone_x, zone_z):
        props = self.get_zone_properties(zone_x, zone_z)
        tint = props['color_tint']
        return tuple(int(min(255, c * tint[i])) for i, c in enumerate(color))

    # === COLLISION DETECTION ===

    def check_collision(self, x, z):
        """Check if position collides with walls or pillars."""
        if not math.isfinite(x) or not math.isfinite(z):
            return True

        # Hard wall at map edges — player cannot leave the seed map
        MAP_W = 3_037_000_499
        MAP_H = 3_037_000_500
        r = 18.0
        if x < r or z < r:
            return True
        if x > MAP_W * ZONE_SIZE - r or z > MAP_H * ZONE_SIZE - r:
            return True

        r = 18.0  # player radius
        half_thick = WALL_THICKNESS / 2

        # Only need to check the immediate surrounding cells
        gx = int(x // PILLAR_SPACING) * PILLAR_SPACING
        gz = int(z // PILLAR_SPACING) * PILLAR_SPACING

        for cx in (gx - PILLAR_SPACING, gx, gx + PILLAR_SPACING):
            for cz in (gz - PILLAR_SPACING, gz, gz + PILLAR_SPACING):

                # --- Horizontal wall along cz ---
                if self._has_wall_between(cx, cz, cx + PILLAR_SPACING, cz):
                    wall_key = tuple(sorted([(cx, cz), (cx + PILLAR_SPACING, cz)]))
                    if wall_key not in self.destroyed_walls:
                        # Wall runs along Z = cz, from X = cx to cx+PILLAR_SPACING
                        # Check Z overlap first (thickness)
                        if abs(z - cz) < half_thick + r:
                            # Check X overlap (length)
                            if cx - r < x < cx + PILLAR_SPACING + r:
                                # Allow passage through opening
                                opening_type = self._has_doorway_in_wall(cx, cz, cx + PILLAR_SPACING, cz)
                                if opening_type:
                                    opening_width = HALLWAY_WIDTH if opening_type == "hallway" else 60
                                    mid = cx + PILLAR_SPACING / 2
                                    o_start = mid - opening_width / 2
                                    o_end   = mid + opening_width / 2
                                    # Only block if NOT inside the opening
                                    if not (o_start + r < x < o_end - r):
                                        return True
                                else:
                                    return True

                # --- Vertical wall along cx ---
                if self._has_wall_between(cx, cz, cx, cz + PILLAR_SPACING):
                    wall_key = tuple(sorted([(cx, cz), (cx, cz + PILLAR_SPACING)]))
                    if wall_key not in self.destroyed_walls:
                        if abs(x - cx) < half_thick + r:
                            if cz - r < z < cz + PILLAR_SPACING + r:
                                opening_type = self._has_doorway_in_wall(cx, cz, cx, cz + PILLAR_SPACING)
                                if opening_type:
                                    opening_width = HALLWAY_WIDTH if opening_type == "hallway" else 60
                                    mid = cz + PILLAR_SPACING / 2
                                    o_start = mid - opening_width / 2
                                    o_end   = mid + opening_width / 2
                                    if not (o_start + r < z < o_end - r):
                                        return True
                                else:
                                    return True

                # --- Pillar at cell centre ---
                offset = PILLAR_SPACING // 2
                px = cx + offset
                pz = cz + offset
                if (px, pz) not in self.destroyed_pillars and self._get_pillar_at(px, pz):
                    # AABB: pillar occupies [px, px+PILLAR_SIZE] x [pz, pz+PILLAR_SIZE]
                    nearest_x = max(px, min(x, px + PILLAR_SIZE))
                    nearest_z = max(pz, min(z, pz + PILLAR_SIZE))
                    dx = x - nearest_x
                    dz = z - nearest_z
                    if dx * dx + dz * dz < r * r:
                        return True

        return False

    # === PLAYER UPDATE ===

    def update(self, dt, keys, mouse_rel):
        """Main update loop for player movement and physics."""
        self.play_time += dt

        # Mouse look
        if self.mouse_look and mouse_rel:
            dx, dy = mouse_rel
            self.yaw += dx * 0.002
            self.pitch -= dy * 0.002

        # Keyboard rotation
        self.is_rotating = False
        rot = ROTATION_SPEED * dt
        if keys[pygame.K_j]:
            self.yaw -= rot
            self.is_rotating = True
        if keys[pygame.K_l]:
            self.yaw += rot
            self.is_rotating = True

        self.pitch = max(-math.pi / 2 + 0.01, min(math.pi / 2 - 0.01, self.pitch))

        # Crouch toggle
        crouch_key_down = keys[pygame.K_c]
        if crouch_key_down and not self.crouch_key_pressed:
            self.is_crouching = not self.is_crouching
            if self.is_crouching:
                self.target_y = CAMERA_HEIGHT_CROUCH
            else:
                self.target_y = CAMERA_HEIGHT_STAND
        self.crouch_key_pressed = crouch_key_down

        # Jump
        if keys[pygame.K_SPACE] and self.on_ground and not self.is_crouching:
            self.is_jumping = True
            self.jump_velocity = JUMP_STRENGTH
            self.on_ground = False

        # Movement speed
        if keys[pygame.K_LSHIFT] and not self.is_crouching:
            self.is_running = True
            speed = RUN_SPEED * dt
        elif self.is_crouching:
            self.is_running = False
            speed = CROUCH_SPEED * dt
        else:
            self.is_running = False
            speed = WALK_SPEED * dt

        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)

        new_x = self.x
        new_z = self.z
        self.is_moving = False

        move_x = 0
        move_z = 0

        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_x += sy * speed
            move_z += cy * speed
            self.is_moving = True
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_x -= sy * speed
            move_z -= cy * speed
            self.is_moving = True
        if keys[pygame.K_a]:
            move_x -= cy * speed
            move_z += sy * speed
            self.is_moving = True
        if keys[pygame.K_d]:
            move_x += cy * speed
            move_z -= sy * speed
            self.is_moving = True

        if move_x != 0 or move_z != 0:
            if not self.check_collision(self.x + move_x, self.z + move_z):
                new_x = self.x + move_x
                new_z = self.z + move_z
            else:
                if not self.check_collision(self.x + move_x, self.z):
                    new_x = self.x + move_x
                if not self.check_collision(self.x, self.z + move_z):
                    new_z = self.z + move_z

        self.x = new_x
        self.z = new_z

        if not self._has_moved and self.is_moving:
            self._has_moved = True

        # Check if player crossed into a new seed cell.
        # Deadzone: require the player to be at least 30 units past the boundary
        # before confirming a crossing — prevents floating-point ping-pong.
        _CROSS_DEADZONE = 30.0
        new_col = int(self.x // ZONE_SIZE)
        new_row = int(self.z // ZONE_SIZE)
        if self._has_moved and (new_col != self.map_col or new_row != self.map_row):
            # How far past the boundary are we?
            local_x = self.x - new_col * ZONE_SIZE
            local_z = self.z - new_row * ZONE_SIZE
            past_boundary = min(local_x, local_z,
                                ZONE_SIZE - local_x, ZONE_SIZE - local_z)
            if past_boundary >= _CROSS_DEADZONE:
                new_seed = min(9223372033963249499, max(0, new_col + new_row * 3_037_000_499))
                self.world_seed = new_seed
                self.map_col = new_col
                self.map_row = new_row
                self.wall_cache.clear()
                self.zone_cache.clear()
                self.pre_damaged_walls.clear()
                # Keep destroyed_walls so player destruction persists across border
                print(f"[seed] crossed to {new_seed} at cell ({new_col}, {new_row})")

        if self.is_moving:
            self.head_bob_time += dt * HEAD_BOB_SPEED

        # Smooth camera height (ONLY when grounded, so it doesn't cancel jumps)
        if self.on_ground and not self.is_jumping:
            if abs(self.y - self.target_y) > 0.1:
                self.y += (self.target_y - self.y) * CROUCH_TRANSITION_SPEED * dt
            else:
                self.y = self.target_y

        # Jump physics
        if self.is_jumping or not self.on_ground:
            self.jump_velocity -= GRAVITY * dt  # gravity pulls down
            self.y += self.jump_velocity * dt

            # Land only when falling downward
            if self.jump_velocity < 0 and self.y <= self.target_y:
                self.y = self.target_y
                self.jump_velocity = 0
                self.is_jumping = False
                self.on_ground = True

        # Head bob
        bob_y = 0
        bob_x = 0
        if self.is_moving:
            bob_y = math.sin(self.head_bob_time * 2 * math.pi) * get_scaled_head_bob_amount()
            bob_x = math.sin(self.head_bob_time * math.pi) * get_scaled_head_bob_sway()

        # Camera shake
        self.camera_shake_time += dt
        shake_x = math.sin(self.camera_shake_time * 13.7) * CAMERA_SHAKE_AMOUNT
        shake_y = math.cos(self.camera_shake_time * 11.3) * CAMERA_SHAKE_AMOUNT * CEILING_HEIGHT_MULTIPLIER

        effective_y = self.y + bob_y + shake_y
        effective_x = self.x + bob_x + shake_x

        # Camera smoothing
        movement_smooth = CAMERA_SMOOTHING if self.is_moving else 1.0
        self.x_s += (effective_x - self.x_s) * movement_smooth
        self.y_s += (effective_y - self.y_s) * movement_smooth
        self.z_s += (self.z - self.z_s) * movement_smooth

        rotation_smooth = ROTATION_SMOOTHING if self.is_rotating else 1.0
        self.pitch_s += (self.pitch - self.pitch_s) * rotation_smooth
        self.yaw_s += (self.yaw - self.yaw_s) * rotation_smooth

        # Update debris
        floor_y = get_scaled_floor_y()
        MAX_DEBRIS = 12000
        DEBRIS_CULL_DIST = 900.0

        px, pz = self.x_s, self.z_s
        for d in self.debris_pieces:
            d.update(dt, floor_y)
            if not d.active:
                continue

            dx = d.cx - px
            dz = d.cz - pz
            if (dx * dx + dz * dz) > (DEBRIS_CULL_DIST * DEBRIS_CULL_DIST):
                d.active = False

        self.debris_pieces = [d for d in self.debris_pieces if d.active]

        if len(self.debris_pieces) > MAX_DEBRIS:
            self.debris_pieces = self.debris_pieces[-MAX_DEBRIS:]

    # === CAMERA TRANSFORMS ===

    def world_to_camera(self, x, y, z):
        """Transform world coordinates to camera space."""
        x -= self.x_s
        y -= self.y_s
        z -= self.z_s

        cy = math.cos(self.yaw_s)
        sy = math.sin(self.yaw_s)
        x1 = x * cy - z * sy
        z1 = x * sy + z * cy

        cp = math.cos(self.pitch_s)
        sp = math.sin(self.pitch_s)
        y2 = y * cp - z1 * sp
        z2 = y * sp + z1 * cp

        return (x1, y2, z2)

    def project_camera(self, p):
        """Project camera space to screen space."""
        x, y, z = p
        if z <= NEAR:
            return None
        aspect = self.height / self.width
        FOV_ANGLE = 90  # degrees
        focal_length = (self.width * 0.5) / math.tan(math.radians(FOV_ANGLE * 0.5))
        scale = focal_length / z
        sx = self.width * 0.5 + x * scale
        sy = self.height * 0.5 - y * scale * aspect
        if not (math.isfinite(sx) and math.isfinite(sy)):
            return None
        return (sx, sy)

    def clip_poly_near(self, poly):
        """Clip polygon against near plane."""
        if not poly or len(poly) < 3:
            return []

        def inside(p):
            return p[2] >= NEAR

        def intersect(a, b):
            ax, ay, az = a
            bx, by, bz = b

            dz = bz - az
            if abs(dz) < 0.00001:
                return None

            t = (NEAR - az) / dz

            if t < -0.001 or t > 1.001:
                return None

            t = max(0.0, min(1.0, t))

            return (ax + (bx - ax) * t, ay + (by - ay) * t, NEAR + 0.001)

        out = []
        prev = poly[-1]
        prev_in = inside(prev)

        for cur in poly:
            cur_in = inside(cur)

            if cur_in and prev_in:
                out.append(cur)
            elif cur_in and not prev_in:
                intersection = intersect(prev, cur)
                if intersection:
                    out.append(intersection)
                out.append(cur)
            elif (not cur_in) and prev_in:
                intersection = intersect(prev, cur)
                if intersection:
                    out.append(intersection)

            prev, prev_in = cur, cur_in

        if len(out) < 3:
            return []

        if any(not math.isfinite(p[2]) or p[2] < NEAR for p in out):
            return []

        return out

    # === RENDERING ===

    def draw_world_poly(self, surface, world_pts, color, width_edges=0, edge_color=None,
                        is_wall=False, is_floor=False, is_ceiling=False):
        """Draw a 3D polygon with all effects applied."""
        cam_pts = [self.world_to_camera(*p) for p in world_pts]

        behind_count = sum(1 for p in cam_pts if p[2] < NEAR)
        if behind_count == len(cam_pts):
            return

        distances = [math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in cam_pts]
        avg_dist = sum(distances) / len(distances) if distances else 0

        if avg_dist > RENDER_DISTANCE * 1.5:
            return

        avg_x = sum(p[0] for p in world_pts) / len(world_pts)
        avg_z = sum(p[2] for p in world_pts) / len(world_pts)
        avg_y = sum(p[1] for p in world_pts) / len(world_pts)

        zone = self.get_zone_at(avg_x, avg_z)
        tinted_color = self.apply_zone_tint(color, *zone)
        noisy_color = self.apply_surface_noise(tinted_color, avg_x, avg_z)

        # Ambient occlusion
        ao_factor = 1.0
        if is_wall:
            if avg_y < get_scaled_floor_y() + 20:
                ao_factor = 0.7
            elif avg_y > get_scaled_wall_height() - 20:
                ao_factor = 0.8

        ao_color = tuple(int(c * ao_factor) for c in noisy_color)
        fogged_color = self.apply_fog(ao_color, avg_dist)

        cam_pts = self.clip_poly_near(cam_pts)
        if len(cam_pts) < 3:
            return

        screen_pts = [self.project_camera(p) for p in cam_pts]
        if any(p is None for p in screen_pts):
            return

        min_x = min(p[0] for p in screen_pts)
        max_x = max(p[0] for p in screen_pts)
        min_y = min(p[1] for p in screen_pts)
        max_y = max(p[1] for p in screen_pts)

        margin = 500
        if (max_x < -margin or min_x > self.width + margin or
                max_y < -margin or min_y > self.height + margin):
            return

        if (max_x - min_x) < 0.5 and (max_y - min_y) < 0.5:
            return

        try:
            pygame.draw.polygon(surface, fogged_color, screen_pts)
        except:
            return

        if width_edges > 0 and edge_color is not None:
            tinted_edge = self.apply_zone_tint(edge_color, *zone)
            noisy_edge = self.apply_surface_noise(tinted_edge, avg_x, avg_z)
            fogged_edge = self.apply_fog(noisy_edge, avg_dist)
            try:
                for i in range(len(screen_pts)):
                    pygame.draw.line(surface, fogged_edge, screen_pts[i],
                                     screen_pts[(i + 1) % len(screen_pts)], width_edges)
            except:
                pass

    def render(self, surface):
        """Main render method."""
        target_surface = self.render_surface
        target_surface.fill(BLACK)

        original_width, original_height = self.width, self.height
        self.width = target_surface.get_width()
        self.height = target_surface.get_height()

        render_queue = []
        render_queue.extend(self._get_floor_tiles())
        render_queue.extend(self._get_ceiling_tiles())
        render_queue.extend(self._get_pillars())
        render_queue.extend(self._get_walls())

        render_queue.sort(key=lambda item: item[0], reverse=True)

        for depth, draw_func in render_queue:
            draw_func(target_surface)

        # Draw debris
        DEBRIS_RENDER_DIST = 600.0
        px, pz = self.x_s, self.z_s

        debris_to_render = []
        for d in self.debris_pieces:
            if not d.active:
                continue

            dx = d.cx - px
            dz = d.cz - pz
            dist_sq = dx * dx + dz * dz
            if dist_sq > DEBRIS_RENDER_DIST * DEBRIS_RENDER_DIST:
                continue

            cam_pos = self.world_to_camera(d.cx, d.cy, d.cz)
            if cam_pos[2] <= NEAR:
                continue

            screen_pos = self.project_camera(cam_pos)
            if screen_pos is None:
                continue

            sx, sy = screen_pos
            if 0 <= sx < self.width and 0 <= sy < self.height:
                dist = math.sqrt(dist_sq)
                size = max(1, int(3 * (1.0 - dist / DEBRIS_RENDER_DIST)))
                debris_to_render.append((cam_pos[2], sx, sy, size, d.color))

        debris_to_render.sort(key=lambda x: x[0], reverse=True)
        for _, sx, sy, size, color in debris_to_render:
            if size == 1:
                try:
                    target_surface.set_at((int(sx), int(sy)), color)
                except:
                    pass
            else:
                pygame.draw.circle(target_surface, color, (int(sx), int(sy)), size)

        self.width, self.height = original_width, original_height

        if self.render_scale < 1.0:
            final_surface = pygame.Surface((self.width, self.height))
            pygame.transform.smoothscale(target_surface, (self.width, self.height), final_surface)
        else:
            final_surface = target_surface.copy()

        surface.blit(final_surface, (0, 0))

        # Crosshair
        cx, cy = self.width // 2, self.height // 2
        pygame.draw.circle(surface, (255, 255, 100), (cx, cy), 3, 1)

        # Seed minimap HUD
        self._draw_seed_hud(surface)

    def _draw_seed_hud(self, surface):
        """Draw a small seed minimap in the bottom-right corner."""
        HUD_SIZE  = 80    # pixels, the square
        MARGIN    = 12
        PAD       = 4

        # Position: bottom-right
        hx = self.width  - HUD_SIZE - MARGIN
        hy = self.height - HUD_SIZE - MARGIN

        # Background
        bg = pygame.Surface((HUD_SIZE, HUD_SIZE), pygame.SRCALPHA)
        bg.fill((10, 15, 30, 200))
        surface.blit(bg, (hx, hy))
        pygame.draw.rect(surface, (80, 120, 200), (hx, hy, HUD_SIZE, HUD_SIZE), 1)

        # Seed color — mirrors seed_map.py destroyed ratio logic exactly
        import random as _rnd
        G = PILLAR_SPACING
        seed = self.world_seed
        col  = self.map_col
        row  = self.map_row
        ox = col * ZONE_SIZE + G
        oz = row * ZONE_SIZE + G
        destroyed = 0
        total = 0
        for di in range(5):
            for dj in range(5):
                cx = ox + di * G
                cz = oz + dj * G
                for x1,z1,x2,z2 in [(cx,cz,cx+G,cz),(cx+G,cz,cx+G,cz+G)]:
                    ds = int(x1*7919 + z1*6577 + x2*4993 + z2*3571 + seed*9973)
                    _rnd.seed(ds)
                    if _rnd.random() < 0.20 and _rnd.uniform(0.0,0.5) < 0.2:
                        destroyed += 1
                    total += 1
        destroyed_ratio = destroyed / max(1, total)
        c = int(destroyed_ratio * 255)
        cell_col = (c, c, c)

        # Fill with seed color
        inner = pygame.Rect(hx+1, hy+1, HUD_SIZE-2, HUD_SIZE-2)
        pygame.draw.rect(surface, cell_col, inner)

        # Player dot — position within cell (0..1)
        local_x = (self.x - self.map_col * ZONE_SIZE) / ZONE_SIZE
        local_z = (self.z - self.map_row * ZONE_SIZE) / ZONE_SIZE
        local_x = max(0.02, min(0.98, local_x))
        local_z = max(0.02, min(0.98, local_z))
        dot_x = int(hx + local_x * HUD_SIZE)
        dot_y = int(hy + local_z * HUD_SIZE)
        pygame.draw.circle(surface, (255, 255, 80),  (dot_x, dot_y), 4)
        pygame.draw.circle(surface, (20,  20,  20),  (dot_x, dot_y), 4, 1)

        # Direction tick
        import math as _math
        tick_len = 6
        tx = int(dot_x + _math.sin(self.yaw) * tick_len)
        ty = int(dot_y + _math.cos(self.yaw) * tick_len)
        pygame.draw.line(surface, (255, 255, 80), (dot_x, dot_y), (tx, ty), 1)

        # Seed label below
        try:
            f = pygame.font.SysFont("consolas", 9)
            label = f.render(f"seed {self.world_seed}", True, (180, 200, 255))
            lx2 = hx + HUD_SIZE // 2 - label.get_width() // 2
            surface.blit(label, (lx2, hy + HUD_SIZE + 2))
            cell_label = f.render(f"({self.map_col}, {self.map_row})", True, (120, 140, 180))
            surface.blit(cell_label, (hx + HUD_SIZE // 2 - cell_label.get_width() // 2,
                                      hy + HUD_SIZE + 12))
        except Exception:
            pass

    # === RUBBLE SPAWNING ===

    def _spawn_rubble_pile(self, x1, z1, x2, z2):
        """Spawn a persistent rubble pile for pre-destroyed walls."""
        wall_key = tuple(sorted([(x1, z1), (x2, z2)]))

        # Only spawn once
        if wall_key in self._spawned_rubble:
            return

        self._spawned_rubble.add(wall_key)

        floor_y = get_scaled_floor_y()
        half_thick = WALL_THICKNESS / 2

        # Determine bounds
        if x1 == x2:
            min_x, max_x = x1 - half_thick, x1 + half_thick
            min_z, max_z = min(z1, z2), max(z1, z2)
        else:
            min_x, max_x = min(x1, x2), max(x1, x2)
            min_z, max_z = z1 - half_thick, z1 + half_thick

        # Spawn settled debris
        for _ in range(80):
            px = random.uniform(min_x, max_x)
            pz = random.uniform(min_z, max_z)

            color_var = random.randint(-40, 20)
            particle_color = (
                max(0, min(255, 200 + color_var)),
                max(0, min(255, 180 + color_var)),
                max(0, min(255, 160 + color_var))
            )

            # Settled debris (no velocity)
            self.debris_pieces.append(Debris(
                (px, floor_y, pz),
                particle_color,
                velocity=None  # Settled from the start
            ))

    # === WORLD GENERATION ===

    """
    Replace your existing _get_pillar_at() method in engine.py with this:
    """

    def _get_pillar_at(self, px, pz):
        """Check if there's a pillar at this position based on PILLAR_MODE."""
        # Outside map bounds — no pillars
        map_max_x = self.MAP_W * ZONE_SIZE
        map_max_z = self.MAP_H * ZONE_SIZE
        if px < 0 or pz < 0 or px > map_max_x or pz > map_max_z:
            return False

        key = (px, pz)
        if key in self.pillar_cache:
            return self.pillar_cache[key]

        if PILLAR_MODE == "none":
            self.pillar_cache[key] = False
            return False

        offset = PILLAR_SPACING // 2
        is_on_pillar_grid = (px % PILLAR_SPACING == offset) and (pz % PILLAR_SPACING == offset)

        if not is_on_pillar_grid:
            self.pillar_cache[key] = False
            return False

        if PILLAR_MODE == "all":
            self.pillar_cache[key] = True
            return True

        import random as rnd
        seed = hash((px, pz, self.world_seed)) % 100000
        rnd.seed(seed)

        probability_map = {
            "sparse": 0.10,
            "normal": 0.30,
            "dense": 0.60,
        }

        probability = probability_map.get(PILLAR_MODE, 0.0)
        has_pillar = rnd.random() < probability

        self.pillar_cache[key] = has_pillar
        return has_pillar

    def _has_wall_between(self, x1, z1, x2, z2):
        """Check if there's a wall between two points."""
        # Outside map bounds — no walls
        map_max_x = self.MAP_W * ZONE_SIZE
        map_max_z = self.MAP_H * ZONE_SIZE
        if x1 < 0 or z1 < 0 or x2 < 0 or z2 < 0:
            return False
        if x1 > map_max_x or x2 > map_max_x or z1 > map_max_z or z2 > map_max_z:
            return False

        # Border walls between seed cells are always open — no wall, free passage
        if self._is_border_wall(x1, z1, x2, z2):
            return False

        key = tuple(sorted([(x1, z1), (x2, z2)]))

        if key in self.wall_cache:
            return self.wall_cache[key]

        is_horizontal = (z1 == z2)
        is_vertical = (x1 == x2)

        if not (is_horizontal or is_vertical):
            self.wall_cache[key] = False
            return False

        # Check if this wall should spawn pre-damaged
        if key not in self.pre_damaged_walls:
            zone = self.get_zone_at((x1 + x2) / 2, (z1 + z2) / 2)
            props = self.get_zone_properties(*zone)

            # Deterministic decay check
            decay_seed = int(x1 * 7919 + z1 * 6577 + x2 * 4993 + z2 * 3571 + self.world_seed * 9973)
            random.seed(decay_seed)

            if random.random() < props['decay_chance']:
                # Randomly damaged (0.0 = rubble, 0.3 = heavily damaged, 0.7 = cracked, 1.0 = intact)
                self.pre_damaged_walls[key] = random.uniform(0.0, 0.5)

                # If completely destroyed, add to destroyed_walls
                if self.pre_damaged_walls[key] < 0.2:
                    self.destroyed_walls.add(key)

        has_wall = True
        self.wall_cache[key] = has_wall
        return has_wall

    def _is_border_wall(self, x1, z1, x2, z2):
        """
        Returns True if this wall lies on a seed map cell boundary.
        Each cell is ZONE_SIZE x ZONE_SIZE world units.
        Border walls use position-only hashes so neighboring seeds agree.
        """
        bx = self.map_col * ZONE_SIZE   # left border x
        bz = self.map_row * ZONE_SIZE   # top border z
        ex = bx + ZONE_SIZE             # right border x
        ez = bz + ZONE_SIZE             # bottom border z

        is_horizontal = (z1 == z2)
        is_vertical   = (x1 == x2)

        if is_horizontal and (z1 == bz or z1 == ez):
            return True
        if is_vertical and (x1 == bx or x1 == ex):
            return True
        return False

    def _has_doorway_in_wall(self, x1, z1, x2, z2):
        """Determine if a wall has a doorway or hallway.
        Border walls (at seed map cell edges) use position-only hash
        so both neighboring seeds produce identical openings.
        Interior walls use world_seed as normal.
        """
        is_horizontal = (z1 == z2)

        if self._is_border_wall(x1, z1, x2, z2):
            # Position-only hash — no world_seed, so neighbors agree
            if is_horizontal:
                door_seed = int(z1 * 3571 + ((x1 + x2) // 2) * 2897)
            else:
                door_seed = int(x1 * 3571 + ((z1 + z2) // 2) * 2897)
        else:
            # Interior wall — seed-dependent as normal
            if is_horizontal:
                door_seed = int(z1 * 3571 + ((x1 + x2) // 2) * 2897 + self.world_seed * 9973)
            else:
                door_seed = int(x1 * 3571 + ((z1 + z2) // 2) * 2897 + self.world_seed * 9973)

        random.seed(door_seed)
        roll = random.random()

        if roll < 0.3:
            return "hallway"
        elif roll < 0.5:
            return "doorway"
        else:
            return None

    def _get_floor_tiles(self):
        """Generate floor tile render queue."""
        render_items = []
        render_range = RENDER_DISTANCE
        tile_size = PILLAR_SPACING

        start_x = int((self.x_s - render_range) // tile_size) * tile_size
        end_x = int((self.x_s + render_range) // tile_size) * tile_size
        start_z = int((self.z_s - render_range) // tile_size) * tile_size
        end_z = int((self.z_s + render_range) // tile_size) * tile_size

        floor_y = get_scaled_floor_y()

        for px in range(start_x, end_x, tile_size):
            for pz in range(start_z, end_z, tile_size):
                tile_center_x = px + tile_size / 2
                tile_center_z = pz + tile_size / 2

                dist = math.sqrt((tile_center_x - self.x_s) ** 2 +
                                 (tile_center_z - self.z_s) ** 2)

                if dist > render_range + tile_size:
                    continue

                def make_draw_func(px=px, pz=pz, floor_y=floor_y, tile_size=tile_size):
                    return lambda surface: self.draw_world_poly(
                        surface,
                        [(px, floor_y, pz), (px + tile_size, floor_y, pz),
                         (px + tile_size, floor_y, pz + tile_size),
                         (px, floor_y, pz + tile_size)],
                        self.carpet_avg,
                        width_edges=0,
                        edge_color=None,
                        is_floor=True
                    )

                render_items.append((dist, make_draw_func()))

        return render_items

    def _get_ceiling_tiles(self):
        """Generate ceiling tile render queue."""
        render_items = []
        render_range = RENDER_DISTANCE
        tile_size = PILLAR_SPACING

        start_x = int((self.x_s - render_range) // tile_size) * tile_size
        end_x = int((self.x_s + render_range) // tile_size) * tile_size
        start_z = int((self.z_s - render_range) // tile_size) * tile_size
        end_z = int((self.z_s + render_range) // tile_size) * tile_size

        ceiling_y = get_scaled_wall_height()

        for px in range(start_x, end_x, tile_size):
            for pz in range(start_z, end_z, tile_size):
                tile_center_x = px + tile_size / 2
                tile_center_z = pz + tile_size / 2

                dist = math.sqrt((tile_center_x - self.x_s) ** 2 +
                                 (tile_center_z - self.z_s) ** 2)

                if dist > render_range + tile_size:
                    continue

                def make_draw_func(px=px, pz=pz, ceiling_y=ceiling_y, tile_size=tile_size):
                    return lambda surface: self.draw_world_poly(
                        surface,
                        [(px, ceiling_y, pz), (px + tile_size, ceiling_y, pz),
                         (px + tile_size, ceiling_y, pz + tile_size),
                         (px, ceiling_y, pz + tile_size)],
                        self.ceiling_avg,
                        width_edges=0,
                        edge_color=None,
                        is_ceiling=True
                    )

                render_items.append((dist, make_draw_func()))

        return render_items

    def _get_pillars(self):
        """Generate pillar render queue."""
        render_items = []
        render_range = RENDER_DISTANCE

        offset = PILLAR_SPACING // 2

        start_x = int((self.x_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_x = int((self.x_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING
        start_z = int((self.z_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_z = int((self.z_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING

        for px in range(start_x, end_x + PILLAR_SPACING, PILLAR_SPACING):
            for pz in range(start_z, end_z + PILLAR_SPACING, PILLAR_SPACING):
                pillar_x = px + offset
                pillar_z = pz + offset

                pillar_key = (pillar_x, pillar_z)

                if pillar_key in self.destroyed_pillars:
                    continue

                if self._get_pillar_at(pillar_x, pillar_z):
                    dist = math.sqrt((pillar_x - self.x_s) ** 2 + (pillar_z - self.z_s) ** 2)
                    if dist < RENDER_DISTANCE:
                        def make_draw_func(pillar_x=pillar_x, pillar_z=pillar_z):
                            return lambda surface: self._draw_single_pillar(surface, pillar_x, pillar_z)

                        render_items.append((dist, make_draw_func()))

        return render_items

    def _draw_single_pillar(self, surface, px, pz):
        """Draw a single pillar."""
        s = PILLAR_SIZE
        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()
        edge_color = (220, 200, 70)

        self.draw_world_poly(
            surface,
            [(px, h, pz), (px + s, h, pz), (px + s, floor_y, pz), (px, floor_y, pz)],
            self.pillar_avg,
            width_edges=1,
            edge_color=edge_color
        )

        self.draw_world_poly(
            surface,
            [(px + s, h, pz + s), (px, h, pz + s), (px, floor_y, pz + s), (px + s, floor_y, pz + s)],
            self.pillar_avg,
            width_edges=1,
            edge_color=edge_color
        )

        self.draw_world_poly(
            surface,
            [(px, h, pz), (px, h, pz + s), (px, floor_y, pz + s), (px, floor_y, pz)],
            self.pillar_avg,
            width_edges=1,
            edge_color=edge_color
        )

        self.draw_world_poly(
            surface,
            [(px + s, h, pz + s), (px + s, h, pz), (px + s, floor_y, pz), (px + s, floor_y, pz + s)],
            self.pillar_avg,
            width_edges=1,
            edge_color=edge_color
        )

        # Draw strokes on all four pillar faces
        pillar_key = (px, pz)
        for face in range(4):
            self._render_pillar_drawings(surface, pillar_key, face)

    def _draw_thick_wall_segment(self, surface, x1, z1, x2, z2, h, floor_y,
                                 edge_color, baseboard_color, baseboard_height):
        """Draw a thick wall segment with baseboard."""
        half_thick = WALL_THICKNESS / 2
        wall_side_color = (230, 210, 70)

        if x1 == x2:  # Vertical wall
            x = x1

            # Front face (main wall)
            self.draw_world_poly(
                surface,
                [(x - half_thick, h, z1), (x - half_thick, h, z2),
                 (x - half_thick, floor_y + baseboard_height, z2), (x - half_thick, floor_y + baseboard_height, z1)],
                self.wall_avg, width_edges=1, edge_color=edge_color, is_wall=True
            )
            # Front baseboard
            self.draw_world_poly(
                surface,
                [(x - half_thick, floor_y + baseboard_height, z1), (x - half_thick, floor_y + baseboard_height, z2),
                 (x - half_thick, floor_y, z2), (x - half_thick, floor_y, z1)],
                baseboard_color, width_edges=0, is_wall=True
            )

            # Back face (main wall)
            self.draw_world_poly(
                surface,
                [(x + half_thick, h, z2), (x + half_thick, h, z1),
                 (x + half_thick, floor_y + baseboard_height, z1), (x + half_thick, floor_y + baseboard_height, z2)],
                self.wall_avg, width_edges=1, edge_color=edge_color, is_wall=True
            )
            # Back baseboard
            self.draw_world_poly(
                surface,
                [(x + half_thick, floor_y + baseboard_height, z2), (x + half_thick, floor_y + baseboard_height, z1),
                 (x + half_thick, floor_y, z1), (x + half_thick, floor_y, z2)],
                baseboard_color, width_edges=0, is_wall=True
            )

            # End caps
            self.draw_world_poly(
                surface,
                [(x - half_thick, h, z1), (x + half_thick, h, z1),
                 (x + half_thick, floor_y, z1), (x - half_thick, floor_y, z1)],
                wall_side_color, width_edges=1, edge_color=edge_color, is_wall=True
            )
            self.draw_world_poly(
                surface,
                [(x + half_thick, h, z2), (x - half_thick, h, z2),
                 (x - half_thick, floor_y, z2), (x + half_thick, floor_y, z2)],
                wall_side_color, width_edges=1, edge_color=edge_color, is_wall=True
            )
        else:  # Horizontal wall
            z = z1

            # Front face (main wall)
            self.draw_world_poly(
                surface,
                [(x1, h, z - half_thick), (x2, h, z - half_thick),
                 (x2, floor_y + baseboard_height, z - half_thick), (x1, floor_y + baseboard_height, z - half_thick)],
                self.wall_avg, width_edges=1, edge_color=edge_color, is_wall=True
            )
            # Front baseboard
            self.draw_world_poly(
                surface,
                [(x1, floor_y + baseboard_height, z - half_thick), (x2, floor_y + baseboard_height, z - half_thick),
                 (x2, floor_y, z - half_thick), (x1, floor_y, z - half_thick)],
                baseboard_color, width_edges=0, is_wall=True
            )

            # Back face (main wall)
            self.draw_world_poly(
                surface,
                [(x2, h, z + half_thick), (x1, h, z + half_thick),
                 (x1, floor_y + baseboard_height, z + half_thick), (x2, floor_y + baseboard_height, z + half_thick)],
                self.wall_avg, width_edges=1, edge_color=edge_color, is_wall=True
            )
            # Back baseboard
            self.draw_world_poly(
                surface,
                [(x2, floor_y + baseboard_height, z + half_thick), (x1, floor_y + baseboard_height, z + half_thick),
                 (x1, floor_y, z + half_thick), (x2, floor_y, z + half_thick)],
                baseboard_color, width_edges=0, is_wall=True
            )

            # End caps
            self.draw_world_poly(
                surface,
                [(x1, h, z + half_thick), (x1, h, z - half_thick),
                 (x1, floor_y, z - half_thick), (x1, floor_y, z + half_thick)],
                wall_side_color, width_edges=1, edge_color=edge_color, is_wall=True
            )
            self.draw_world_poly(
                surface,
                [(x2, h, z - half_thick), (x2, h, z + half_thick),
                 (x2, floor_y, z + half_thick), (x2, floor_y, z - half_thick)],
                wall_side_color, width_edges=1, edge_color=edge_color, is_wall=True
            )

    def _get_walls(self):
        """Generate wall render queue."""
        render_items = []
        render_range = RENDER_DISTANCE

        start_x = int((self.x_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_x = int((self.x_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING
        start_z = int((self.z_s - render_range) // PILLAR_SPACING) * PILLAR_SPACING
        end_z = int((self.z_s + render_range) // PILLAR_SPACING) * PILLAR_SPACING

        for px in range(start_x, end_x + PILLAR_SPACING, PILLAR_SPACING):
            for pz in range(start_z, end_z + PILLAR_SPACING, PILLAR_SPACING):
                # Horizontal walls
                wall_key_h = tuple(sorted([(px, pz), (px + PILLAR_SPACING, pz)]))
                if self._has_wall_between(px, pz, px + PILLAR_SPACING, pz) and wall_key_h not in self.destroyed_walls:
                    wall_center_x = px + PILLAR_SPACING / 2
                    wall_center_z = pz
                    dist = math.sqrt((wall_center_x - self.x_s) ** 2 + (wall_center_z - self.z_s) ** 2)

                    def make_draw_func(px=px, pz=pz):
                        return lambda surface: self._draw_connecting_wall(surface, px, pz, px + PILLAR_SPACING, pz)

                    render_items.append((dist, make_draw_func()))

                # Vertical walls
                wall_key_v = tuple(sorted([(px, pz), (px, pz + PILLAR_SPACING)]))
                if self._has_wall_between(px, pz, px, pz + PILLAR_SPACING) and wall_key_v not in self.destroyed_walls:
                    wall_center_x = px
                    wall_center_z = pz + PILLAR_SPACING / 2
                    dist = math.sqrt((wall_center_x - self.x_s) ** 2 + (wall_center_z - self.z_s) ** 2)

                    def make_draw_func(px=px, pz=pz):
                        return lambda surface: self._draw_connecting_wall(surface, px, pz, px, pz + PILLAR_SPACING)

                    render_items.append((dist, make_draw_func()))

        return render_items

    def _draw_connecting_wall(self, surface, x1, z1, x2, z2):
        """Draw a connecting wall with doorways/hallways and damage."""
        wall_key = tuple(sorted([(x1, z1), (x2, z2)]))

        # Check for pre-existing damage
        damage_state = self.pre_damaged_walls.get(wall_key, 1.0)

        if damage_state < 0.2:
            # Wall is rubble - spawn debris piles if not already done
            self._spawn_rubble_pile(x1, z1, x2, z2)
            return  # Don't draw wall

        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()

        # Modify colors based on damage
        if damage_state < 0.5:
            # Heavily damaged - darker, dirtier
            edge_color = (180, 160, 40)
            baseboard_color = (170, 150, 50)
        elif damage_state < 0.8:
            # Cracked - slightly darker
            edge_color = (200, 180, 45)
            baseboard_color = (190, 170, 55)
        else:
            # Normal
            edge_color = (220, 190, 50)
            baseboard_color = (210, 190, 60)

        baseboard_height = 8

        opening_type = self._has_doorway_in_wall(x1, z1, x2, z2)

        if opening_type is None:
            self._draw_thick_wall_segment(surface, x1, z1, x2, z2, h, floor_y,
                                          edge_color, baseboard_color, baseboard_height)
        else:
            opening_width = HALLWAY_WIDTH if opening_type == "hallway" else 60

            if x1 == x2:  # Vertical wall
                wall_length = abs(z2 - z1)
                opening_start = min(z1, z2) + (wall_length - opening_width) / 2
                opening_end = opening_start + opening_width

                if opening_start > min(z1, z2):
                    self._draw_thick_wall_segment(surface, x1, min(z1, z2), x2, opening_start,
                                                  h, floor_y, edge_color, baseboard_color, baseboard_height)

                if opening_end < max(z1, z2):
                    self._draw_thick_wall_segment(surface, x1, opening_end, x2, max(z1, z2),
                                                  h, floor_y, edge_color, baseboard_color, baseboard_height)
            else:  # Horizontal wall
                wall_length = abs(x2 - x1)
                opening_start = min(x1, x2) + (wall_length - opening_width) / 2
                opening_end = opening_start + opening_width

                if opening_start > min(x1, x2):
                    self._draw_thick_wall_segment(surface, min(x1, x2), z1, opening_start, z2,
                                                  h, floor_y, edge_color, baseboard_color, baseboard_height)

                if opening_end < max(x1, x2):
                    self._draw_thick_wall_segment(surface, opening_end, z1, max(x1, x2), z2,
                                                  h, floor_y, edge_color, baseboard_color, baseboard_height)

        # Draw strokes on this wall
        self._render_wall_drawings(surface, wall_key, x1, z1, x2, z2, h, floor_y)

    # === DRAWING RENDER ===

    def _uv_to_world_wall(self, u, v, x1, z1, x2, z2, h, floor_y):
        """Convert (u,v) on a wall to world coords for rendering."""
        wall_height = h - floor_y
        wy = floor_y + (1.0 - v) * wall_height
        if x1 == x2:
            wz = min(z1, z2) + u * abs(z2 - z1)
            wx = float(x1)
            # Offset slightly toward player to avoid z-fighting
            offset = 0.5 if self.x_s < x1 else -0.5
            wx += offset
        else:
            wx = min(x1, x2) + u * abs(x2 - x1)
            wz = float(z1)
            offset = 0.5 if self.z_s < z1 else -0.5
            wz += offset
        return wx, wy, wz

    def _uv_to_world_pillar(self, u, v, pillar_key, face):
        """Convert (u,v) on a pillar face to world coords."""
        from config import PILLAR_SIZE
        px, pz = pillar_key
        s = PILLAR_SIZE
        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()
        wall_height = h - floor_y
        wy = floor_y + (1.0 - v) * wall_height
        off = 0.5
        if face == 0:    # front z=pz
            wx = px + u * s
            wz = pz - off
        elif face == 1:  # back z=pz+s
            wx = px + (1.0 - u) * s
            wz = pz + s + off
        elif face == 2:  # left x=px
            wx = px - off
            wz = pz + u * s
        else:            # right x=px+s
            wx = px + s + off
            wz = pz + (1.0 - u) * s
        return wx, wy, wz

    def _render_wall_drawings(self, surface, wall_key, x1, z1, x2, z2, h, floor_y):
        """Render all strokes for a wall, including live stroke preview."""
        ds = self.drawing_system

        # Collect saved strokes + live preview
        all_strokes = list(ds.wall_drawings.get(wall_key, []))
        if ds.drawing_active and ds.current_wall == wall_key and len(ds.current_stroke) >= 2:
            all_strokes.append(ds.current_stroke)

        for stroke in all_strokes:
            pts = []
            for u, v, color in stroke:
                wx, wy, wz = self._uv_to_world_wall(u, v, x1, z1, x2, z2, h, floor_y)
                cam = self.world_to_camera(wx, wy, wz)
                if cam[2] <= NEAR:
                    pts.append(None)
                    continue
                sp = self.project_camera(cam)
                pts.append((sp, color))

            for i in range(len(pts) - 1):
                if pts[i] and pts[i+1] and pts[i][0] and pts[i+1][0]:
                    try:
                        pygame.draw.line(surface, pts[i][1], pts[i][0], pts[i+1][0], 2)
                    except Exception:
                        pass

    def _render_pillar_drawings(self, surface, pillar_key, face):
        """Render all strokes for a pillar face, including live preview."""
        ds = self.drawing_system
        h = get_scaled_wall_height()
        floor_y = get_scaled_floor_y()

        all_strokes = []
        face_strokes = ds.pillar_drawings.get(pillar_key, {}).get(face, [])
        all_strokes.extend(face_strokes)
        if ds.drawing_active and ds.current_pillar == pillar_key and ds.current_pillar_face == face and len(ds.current_stroke) >= 2:
            all_strokes.append(ds.current_stroke)

        for stroke in all_strokes:
            pts = []
            for u, v, color in stroke:
                wx, wy, wz = self._uv_to_world_pillar(u, v, pillar_key, face)
                cam = self.world_to_camera(wx, wy, wz)
                if cam[2] <= NEAR:
                    pts.append(None)
                    continue
                sp = self.project_camera(cam)
                pts.append((sp, color))

            for i in range(len(pts) - 1):
                if pts[i] and pts[i+1] and pts[i][0] and pts[i+1][0]:
                    try:
                        pygame.draw.line(surface, pts[i][1], pts[i][0], pts[i+1][0], 2)
                    except Exception:
                        pass

    # === UTILITIES ===

    def toggle_mouse(self):
        """Toggle mouse look on/off."""
        self.mouse_look = not self.mouse_look
        pygame.mouse.set_visible(not self.mouse_look)
        pygame.event.set_grab(self.mouse_look)

    def load_from_save(self, save_data):
        """Load game state from save data."""
        if save_data:
            player = save_data.get('player', {})
            self.x = player.get('x', self.x)
            self.y = player.get('y', self.y)
            self.z = player.get('z', self.z)
            self.pitch = player.get('pitch', self.pitch)
            self.yaw = player.get('yaw', self.yaw)

            self.x_s = self.x
            self.y_s = self.y
            self.z_s = self.z
            self.pitch_s = self.pitch
            self.yaw_s = self.yaw

            world = save_data.get('world', {})
            self.world_seed = world.get('seed', self.world_seed)

            destroyed_walls_list = world.get('destroyed_walls', [])
            self.destroyed_walls = {tuple(tuple(point) for point in wall) for wall in destroyed_walls_list}

            stats = save_data.get('stats', {})
            self.play_time = stats.get('play_time', 0)

            self.pillar_cache.clear()
            self.wall_cache.clear()
            self.zone_cache.clear()

            # Load drawings
            self.drawing_system.load_state(save_data.get('drawings', {}))

            print(f"Loaded world with seed: {self.world_seed}")
            print(f"Loaded {len(self.destroyed_walls)} destroyed walls")
