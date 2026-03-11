# THE BACKROOMS

A mathematically infinite, procedurally generated 3D Backrooms engine built entirely in Python and Pygame — no Unity, no Unreal, no 3D libraries. Every wall, floor, ceiling, pillar, sound, and texture is generated from scratch at runtime using pure math and NumPy.

---

## Features

- **Genuinely infinite world** — 9,223,372,036,854,775,807 unique seeds, each a distinct procedural world. No edges, no seams, no loops.
- **Pure software 3D rendering** — perspective projection, Sutherland-Hodgman near-plane clipping, painter's algorithm depth sorting, all written from first principles.
- **Destructible walls** — left-click or press E to punch through walls. Pixel debris physics, crack progression, rubble piles.
- **Wall painting system** — right-click to draw on any wall or pillar surface in world space. Drawings persist across sessions via save files. Leave messages for nobody.
- **Geometry-aware audio** — acoustic raycasting casts 16 rays per frame to model room size, reverb, and stereo panning through actual wall geometry.
- **Microphone duplex stream** — your voice echoes back with live room acoustics applied via `sounddevice`.
- **Procedural textures and audio** — everything generated at startup with NumPy waveform synthesis and pixel-level texture generation.
- **Seed map viewer** — a separate 9.2 quintillion cell atlas you can pan and zoom, click any cell to launch that world (`seed_map.py`).
- **Blue carpet** — a deliberate departure from canonical yellow.

---

## Requirements

```
python 3.10+
pygame
numpy
sounddevice   (optional — mic echo works without it, just disabled)
```

Install dependencies:

```bash
pip install pygame numpy sounddevice
```

---

## Running

```bash
# Random seed
python main.py

# Specific seed
python main.py 12345

# Seed map atlas
python seed_map.py
```

On first launch you will be prompted for a seed if no argument is given. Press Enter for random.

---

## Controls

| Key / Button | Action |
|---|---|
| WASD | Move |
| J / L | Turn left / right |
| SHIFT | Run |
| C | Toggle crouch |
| SPACE | Jump |
| Mouse (when locked) | Look |
| LEFT CLICK | Destroy wall or pillar |
| E | Destroy targeted wall or pillar |
| **RIGHT CLICK** | **Draw on wall / pillar (hold to draw)** |
| **T** | **Toggle Draw / Text mode** |
| **1 – 9** | **Change draw color** |
| R | Toggle performance mode (0.5x render scale) |
| H | Toggle help overlay |
| F5 | Quick save (slot 1) |
| F9 | Quick load (slot 1) |
| ESC | Pause |
| M | Toggle mouse look |

---

## Drawing System

Right-click any wall or pillar surface to draw on it in world space. Strokes are stored in UV coordinates relative to the wall, so they stay correctly positioned if you walk away and return.

**Draw mode** — hold right-click and move your crosshair across a surface to paint a stroke.

**Text mode** — press T to switch, then right-click a surface. A text input box appears. Type your message and press Enter. Text is depth-scaled so it looks correct from any distance.

**Colors** — press 1–9 to select: Red, Orange, Yellow, Green, Blue, Indigo, Violet, Black, White.

All drawings are saved with the world via F5 and loaded via F9.

---

## World Seeds

Each seed deterministically generates an entire infinite world. The same seed always produces the same rooms, walls, doorways, and pre-damaged walls — everywhere, forever.

Worlds are divided into zones with different structural densities (normal, dense, sparse, maze, open). Zone boundaries are seamless.

The seed map (`seed_map.py`) visualizes the entire seed space as a grid where brightness reflects structural destruction density. Click any cell and press Enter to enter that world.

---

## File Structure

| File | Purpose |
|---|---|
| `main.py` | Game loop, state machine, input handling |
| `engine.py` | Monolithic engine — rendering, physics, world generation, player |
| `drawing_system.py` | Wall painting data layer and UV math |
| `config.py` | All tunable constants |
| `audio.py` | Procedural sound synthesis and mic processor |
| `save_system.py` | JSON save / load |
| `seed_map.py` | Seed atlas viewer |
| `textures.py` | Procedural texture generation |
| `raycasting.py` | Möller–Trumbore ray-triangle intersection, audio raycasting |
| `debris.py` | Pixel debris physics and damage states |
| `procedural.py` | Zone type definitions |

---

## Configuration

All settings live in `config.py`. Notable options:

```python
FULLSCREEN = True          # Set False for windowed
WIDTH, HEIGHT = 960, 540   # Resolution
RENDER_SCALE = 1           # 0.5 for performance mode default
PILLAR_MODE = "none"       # "none" | "sparse" | "normal" | "dense" | "all"
FOG_ENABLED = False        # Distance fog
FLICKER_CHANCE = 0.0003    # Light flicker probability per frame
```

---

## Technical Notes

- No external 3D libraries. The renderer is a software rasterizer written entirely in Python.
- The world is mathematically infinite — coordinates are 64-bit floats, player position is seeded at the world origin of their seed map cell.
- Acoustic raycasting runs every frame using 2D horizontal ray marching — cheap enough to do in pure Python at 60 fps.
- Wall drawings are stored in UV space (0–1 normalized) so they are resolution-independent and scale correctly with any wall geometry.
- Text is rendered deferred — collected during the geometry pass, then drawn onto the final screen surface after upscaling to stay sharp at any render scale.

---

*Built by Gulp of Wealth LLC*
