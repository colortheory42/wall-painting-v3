"""
Configuration constants for the Backrooms engine.
All tunable parameters in one place.
"""

# Display settings
WIDTH = 960
HEIGHT = 540
FULLSCREEN = True
FPS = 60

# Performance settings
RENDER_SCALE = 1

# Aesthetic colors (blue and yellow theme)
WALL_COLOR = (240, 220, 80)  # Yellow walls
FLOOR_COLOR = (30, 60, 120)  # Deep blue floor
CEILING_COLOR = (200, 200, 240)  # Light blue ceiling
PILLAR_COLOR = (250, 230, 90)  # Bright yellow pillars
BLACK = (20, 40, 80)  # Dark blue background

# Camera settings
CAMERA_SMOOTHING = 0.25
ROTATION_SMOOTHING = 0.3
ROTATION_SPEED = 2.0

# Movement speeds
WALK_SPEED = 50
RUN_SPEED = 100
CROUCH_SPEED = 10

# Camera heights
CAMERA_HEIGHT_STAND = 50
CAMERA_HEIGHT_CROUCH = 30
CROUCH_TRANSITION_SPEED = 5.0

# Jumping physics
JUMP_STRENGTH = 150
GRAVITY = 300

# Rendering settings
NEAR = 1
FOV = 500.0
RENDER_DISTANCE = 2000

# Room generation
PILLAR_SPACING = 400
HALLWAY_WIDTH = 100
PILLAR_SIZE = 80
WALL_THICKNESS = 20
WALL_HEIGHT = 400
CAMERA_HEIGHT = 50
CEILING_HEIGHT_MULTIPLIER = 1
ZONE_SIZE = 2_965_820  # max float64-safe zone width

# === PILLAR GENERATION CONTROL ===
# Control internal pillar density:
# "none" = no pillars (default)
# "sparse" = few pillars (10% chance per grid point)
# "normal" = some pillars (30% chance per grid point)
# "dense" = many pillars (60% chance per grid point)
# "all" = pillar at every grid point (warning: very dense!)
PILLAR_MODE = "none"  # <-- CHANGE THIS LINE

# Camera effects
HEAD_BOB_SPEED = 3.0
HEAD_BOB_AMOUNT = 4
HEAD_BOB_SWAY = 1.5
CAMERA_SHAKE_AMOUNT = 0.08

# Fog settings
FOG_ENABLED = False
FOG_START = 200
FOG_END = 350
FOG_COLOR = (20, 40, 80)

# Flickering settings
FLICKER_CHANCE = 0.0003
FLICKER_DURATION = 0.08
FLICKER_BRIGHTNESS = 0.15

# Ambient sound settings
FOOTSTEP_INTERVAL = (10, 30)
BUZZ_INTERVAL = (5, 15)

# Audio settings
SAMPLE_RATE = 22050
AUDIO_BUFFER_SIZE = 2048

# Texture settings
TEXTURE_SIZE = 256

# Save/load settings
SAVE_DIR = "backrooms_saves"


# Helper functions for scaled heights
def get_scaled_wall_height():
    return WALL_HEIGHT * CEILING_HEIGHT_MULTIPLIER


def get_scaled_camera_height():
    return CAMERA_HEIGHT * CEILING_HEIGHT_MULTIPLIER


def get_scaled_floor_y():
    return -2 * CEILING_HEIGHT_MULTIPLIER


def get_scaled_head_bob_amount():
    return HEAD_BOB_AMOUNT * CEILING_HEIGHT_MULTIPLIER


def get_scaled_head_bob_sway():
    return HEAD_BOB_SWAY * CEILING_HEIGHT_MULTIPLIER