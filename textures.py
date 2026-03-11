"""
Procedural texture generation.
Creates textures for floor, ceiling, walls, and pillars at runtime.
"""

import random
import math
import numpy as np
import pygame
from config import TEXTURE_SIZE


def generate_carpet_texture(size=TEXTURE_SIZE):
    """Generate blue carpet texture with noise."""
    texture = np.zeros((size, size, 3), dtype=np.uint8)
    base_r, base_g, base_b = 30, 60, 140

    for i in range(size):
        for j in range(size):
            noise = random.randint(-15, 15)
            texture[i, j] = [
                np.clip(base_r + noise, 0, 255),
                np.clip(base_g + noise, 0, 255),
                np.clip(base_b + noise, 0, 255)
            ]

    return pygame.surfarray.make_surface(texture.swapaxes(0, 1))


def generate_ceiling_tile_texture(size=TEXTURE_SIZE):
    """Generate ceiling tile texture with pattern."""
    texture = np.zeros((size, size, 3), dtype=np.uint8)
    base_r, base_g, base_b = 200, 200, 240

    for i in range(size):
        for j in range(size):
            pattern = math.sin(i * 0.5) * math.cos(j * 0.5)
            noise = random.randint(-10, 10)
            r_value = int(base_r + pattern * 10 + noise)
            g_value = int(base_g + pattern * 10 + noise)
            b_value = int(base_b + pattern * 5 + noise)

            texture[i, j] = [
                np.clip(r_value, 180, 240),
                np.clip(g_value, 180, 240),
                np.clip(b_value, 220, 255)
            ]

    return pygame.surfarray.make_surface(texture.swapaxes(0, 1))


def generate_wall_texture(size=TEXTURE_SIZE):
    """Generate yellow wall texture with vertical lines."""
    texture = np.zeros((size, size, 3), dtype=np.uint8)
    base_r, base_g, base_b = 240, 220, 80

    for i in range(size):
        for j in range(size):
            noise = random.randint(-12, 12)
            pattern = -3 if i % 8 < 2 else 0

            texture[i, j] = [
                np.clip(base_r + noise + pattern, 0, 255),
                np.clip(base_g + noise + pattern, 0, 255),
                np.clip(base_b + noise + pattern, 0, 255)
            ]

    return pygame.surfarray.make_surface(texture.swapaxes(0, 1))


def generate_pillar_texture(size=TEXTURE_SIZE):
    """Generate bright yellow pillar texture."""
    texture = np.zeros((size, size, 3), dtype=np.uint8)
    base_r, base_g, base_b = 250, 230, 90

    for i in range(size):
        for j in range(size):
            noise = random.randint(-10, 10)
            texture[i, j] = [
                np.clip(base_r + noise, 0, 255),
                np.clip(base_g + noise, 0, 255),
                np.clip(base_b + noise, 0, 255)
            ]

    return pygame.surfarray.make_surface(texture.swapaxes(0, 1))
