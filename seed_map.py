"""
seed_map.py — Backrooms Complete Seed Topology Map

Every one of the 2,147,483,648 seeds is on this map.
Cell (col, row) maps directly to a seed — no sampling, no limit.
Pan anywhere. Every cell is always filled.

The map is 46341 x 46341 cells — the full sqrt of the seed space.
Each cell's color reflects that seed's structural properties.

Controls:
    Arrow keys / WASD  — pan
    Scroll / +/-       — zoom
    R                  — reset view
    Click              — inspect seed
    Q / ESC            — quit
"""

import math
import random
import argparse
import sys
import subprocess
import os

import pygame

# ── Constants ---------------------------------------------------------------
SEED_MAX = 9_223_372_036_854_775_807
MAP_W       = 3_037_000_499   # isqrt(SEED_MAX)
MAP_H       = 3_037_000_500
CELL_SIZE   = 12      # pixels at zoom=1

PILLAR_SPACING = 400
ZONE_SIZE      = 2_965_820   # world units per seed cell

# ── Seed from grid cell -----------------------------------------------------

def cell_to_seed(col, row):
    """Map grid coordinates to a unique seed in 0..SEED_MAX."""
    return min(SEED_MAX, col + row * MAP_W)

# ── Geometry fingerprint (fast, no loops) -----------------------------------

def _border_wall(x1, z1, x2, z2, col, row):
    """True if wall lies on the cell boundary for (col, row)."""
    bx = col * ZONE_SIZE
    bz = row * ZONE_SIZE
    ex = bx + ZONE_SIZE
    ez = bz + ZONE_SIZE
    if z1 == z2 and (z1 == bz or z1 == ez): return True
    if x1 == x2 and (x1 == bx or x1 == ex): return True
    return False

def _doorway_val(x1, z1, x2, z2, seed, col=0, row=0):
    """Doorway value for a wall. Border walls use position-only hash."""
    if _border_wall(x1, z1, x2, z2, col, row):
        # No seed — neighbors agree
        if z1 == z2:
            ds = int(z1 * 3571 + ((x1 + x2) // 2) * 2897)
        else:
            ds = int(x1 * 3571 + ((z1 + z2) // 2) * 2897)
    else:
        if z1 == z2:
            ds = int(z1 * 3571 + ((x1 + x2) // 2) * 2897 + seed * 9973)
        else:
            ds = int(x1 * 3571 + ((z1 + z2) // 2) * 2897 + seed * 9973)
    random.seed(ds)
    r = random.random()
    if   r < 0.3: return 2
    elif r < 0.5: return 1
    return 0

def _destroyed(x1, z1, x2, z2, seed):
    ds = int(x1 * 7919 + z1 * 6577 + x2 * 4993 + z2 * 3571 + seed * 9973)
    random.seed(ds)
    if random.random() < 0.20:
        return random.uniform(0.0, 0.5) < 0.2
    return False

def seed_properties(seed, grid_n=5):
    """Count destroyed walls as fraction of total. Returns 0..1."""
    col = seed % MAP_W
    row = seed // MAP_W
    G   = PILLAR_SPACING
    ox  = col * ZONE_SIZE + G
    oz  = row * ZONE_SIZE + G
    destroyed = 0
    total = 0
    for di in range(grid_n):
        for dj in range(grid_n):
            cx = ox + di * G
            cz = oz + dj * G
            for x1,z1,x2,z2 in [(cx,cz,cx+G,cz),(cx+G,cz,cx+G,cz+G)]:
                if _destroyed(x1,z1,x2,z2,seed):
                    destroyed += 1
                total += 1
    return destroyed / total

# ── Color from seed properties ----------------------------------------------

def _color_from_props(destroyed_ratio):
    """Black=no destruction, white=fully destroyed. No remapping — 0..1 direct."""
    c = int(destroyed_ratio * 255)
    return (c, c, c)

def seed_color(seed):
    return _color_from_props(seed_properties(seed))

# ── Game launcher ----------------------------------------------------------

def _launch_game(seed):
    """
    Quit pygame, launch main.py with the selected seed, then relaunch the map.
    The map resumes exactly where it left off because we re-exec this script.
    """
    pygame.quit()

    # Find main.py relative to this file
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(here, "main.py")

    print(f"\n[seed map] Launching seed {seed:,} ...\n")
    subprocess.run([sys.executable, main_path, str(seed)])

    # After game exits, relaunch the map
    print("\n[seed map] Returning to map...\n")
    os.execv(sys.executable, [sys.executable, __file__] + sys.argv[1:])


# ── Viewer ------------------------------------------------------------------

BG         = (8,  12, 22)
GRID_LINE  = (25, 32, 50)
SELECT_COL = (255, 240, 80)
HOVER_COL  = (140, 160, 255)
TEXT_COL   = (200, 215, 240)

def run(args):
    pygame.init()
    sw, sh = 1280, 720
    screen = pygame.display.set_mode((sw, sh), pygame.FULLSCREEN)
    pygame.display.set_caption("Backrooms Seed Map — 9,223,372,036,854,775,807 worlds")
    clock  = pygame.time.Clock()

    font_sm = pygame.font.SysFont("consolas",  9)
    font_md = pygame.font.SysFont("consolas", 13)
    font_lg = pygame.font.SysFont("consolas", 17, bold=True)

    # Camera: top-left world pixel
    cam_x = 0.0
    cam_y = 0.0
    zoom  = 1.0
    ZMIN, ZMAX = 0.05, 12.0

    selected_seed = None

    # Color cache — only cache what's on screen, evict when panning
    color_cache = {}
    CACHE_MAX   = 8000

    running = True
    while running:
        sw, sh = screen.get_size()
        dt     = clock.tick(60) / 1000.0
        keys   = pygame.key.get_pressed()

        cs      = CELL_SIZE * zoom
        pan     = cs * 10 * dt
        fast    = 5.0 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 1.0

        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: cam_x -= pan * fast
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: cam_x += pan * fast
        if keys[pygame.K_UP]    or keys[pygame.K_w]: cam_y -= pan * fast
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]: cam_y += pan * fast
        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS]:
            zoom = min(ZMAX, zoom * (1 + dt * 2))
        if keys[pygame.K_MINUS]:
            zoom = max(ZMIN, zoom * (1 - dt * 2))

        # Clamp to map bounds
        cs     = CELL_SIZE * zoom
        cam_x  = max(0, min(cam_x, MAP_W * cs - sw))
        cam_y  = max(0, min(cam_y, MAP_H * cs - sh))

        mx, my = pygame.mouse.get_pos()
        hov_col = int((mx + cam_x) / cs)
        hov_row = int((my + cam_y) / cs)
        hov_seed = cell_to_seed(hov_col, hov_row) \
                   if 0 <= hov_col < MAP_W and 0 <= hov_row < MAP_H else None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                if event.key == pygame.K_r:
                    cam_x, cam_y, zoom = 0.0, 0.0, 1.0
                    color_cache.clear()

                # Launch game with selected seed
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if selected_seed is not None:
                        _launch_game(selected_seed)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:
                    old = zoom
                    zoom = min(ZMAX, zoom * 1.12)
                    cam_x = max(0, cam_x + mx * (zoom - old))
                    cam_y = max(0, cam_y + my * (zoom - old))
                    color_cache.clear()
                if event.button == 5:
                    old = zoom
                    zoom = max(ZMIN, zoom / 1.12)
                    cam_x = max(0, cam_x + mx * (zoom - old))
                    cam_y = max(0, cam_y + my * (zoom - old))
                    color_cache.clear()
                if event.button == 1:
                    selected_seed = hov_seed

        # Evict cache if too large
        if len(color_cache) > CACHE_MAX:
            color_cache.clear()

        # ── Draw ────────────────────────────────────────────────────────
        screen.fill(BG)

        cs   = CELL_SIZE * zoom
        cs_i = max(1, int(cs))

        col0 = max(0, int(cam_x / cs))
        row0 = max(0, int(cam_y / cs))
        col1 = min(MAP_W, int((cam_x + sw) / cs) + 2)
        row1 = min(MAP_H, int((cam_y + sh) / cs) + 2)

        for row in range(row0, row1):
            for col in range(col0, col1):
                seed = cell_to_seed(col, row)

                # Get/compute color
                if seed not in color_cache:
                    color_cache[seed] = seed_color(seed)
                col_fill = color_cache[seed]

                sx = int(col * cs - cam_x)
                sy = int(row * cs - cam_y)
                rect = pygame.Rect(sx, sy, cs_i, cs_i)

                is_sel = (seed == selected_seed)
                is_hov = (seed == hov_seed and not is_sel)

                pygame.draw.rect(screen, col_fill, rect)

                if is_sel:
                    pygame.draw.rect(screen, SELECT_COL, rect,
                                     max(1, int(cs * 0.08)))
                elif is_hov:
                    pygame.draw.rect(screen, HOVER_COL, rect,
                                     max(1, int(cs * 0.05)))
                elif cs > 4:
                    pygame.draw.rect(screen, GRID_LINE, rect, 1)

                # Seed number label — only when zoomed in enough
                if cs >= 40:
                    label = str(seed)
                    surf  = font_sm.render(label, True, (220, 230, 255))
                    screen.blit(surf, (sx + 2, sy + cs_i//2 - surf.get_height()//2))

        # ── HUD ─────────────────────────────────────────────────────────
        hud_lines = [
            ("BACKROOMS SEED MAP", font_lg, (250, 240, 100)),
            (f"9,223,372,036,854,775,807 worlds  |  {MAP_W}x{MAP_H} grid", font_md, (160,180,210)),
            (f"Zoom: {zoom:.3f}x   Cell: {cs:.1f}px", font_md, TEXT_COL),
            (f"Region: ({col0},{row0}) to ({col1},{row1})", font_md, TEXT_COL),
            ("", font_md, TEXT_COL),
            ("Arrows/WASD: pan  |  SHIFT: fast", font_md, TEXT_COL),
            ("+/-  Scroll: zoom  |  R: reset", font_md, TEXT_COL),
            ("Click: inspect seed", font_md, TEXT_COL),
            ("Q/ESC: quit", font_md, TEXT_COL),
        ]
        y = 10
        for text, f, col in hud_lines:
            if text:
                surf = f.render(text, True, col)
                # Dark bg behind text
                bg = pygame.Surface((surf.get_width()+6, surf.get_height()+2), pygame.SRCALPHA)
                bg.fill((0,0,0,140))
                screen.blit(bg,   (8, y-1))
                screen.blit(surf, (11, y))
            y += font_md.size("A")[1] + 3

        # Hover label
        if hov_seed is not None:
            txt  = f"Seed: {hov_seed:,}  cell ({hov_col}, {hov_row})"
            surf = font_md.render(txt, True, HOVER_COL)
            bg   = pygame.Surface((surf.get_width()+8, surf.get_height()+4), pygame.SRCALPHA)
            bg.fill((0,0,0,180))
            screen.blit(bg,   (mx+12, my-2))
            screen.blit(surf, (mx+15, my))

        # Selected panel
        if selected_seed is not None:
            _panel(screen, font_md, font_lg, selected_seed, sw, sh)

        # Legend — extremes of _color_from_props after remapping
        lx, ly = sw - 180, sh - 52
        pygame.draw.rect(screen, (255,255,255), (lx, ly,    14, 12), border_radius=2)
        pygame.draw.rect(screen, (20,  20,  20), (lx, ly+18, 14, 12), border_radius=2)
        screen.blit(font_md.render("Open void",    True, (220,220,220)), (lx+18, ly))
        screen.blit(font_md.render("Walls intact", True, (80, 80, 80)),  (lx+18, ly+18))

        pygame.display.flip()

    pygame.quit()


def _panel(screen, font, font_lg, seed, sw, sh):
    destroyed_ratio = seed_properties(seed)
    col_pos = seed % MAP_W
    row_pos = seed // MAP_W

    pw, ph = 320, 200
    px, py = sw - pw - 10, 10
    surf   = pygame.Surface((pw, ph), pygame.SRCALPHA)
    surf.fill((10, 15, 30, 220))
    screen.blit(surf, (px, py))
    pygame.draw.rect(screen, SELECT_COL, (px, py, pw, ph), 1, border_radius=3)

    lines = [
        (f"SEED  {seed:,}", font_lg, SELECT_COL),
        (f"Map cell:       ({col_pos}, {row_pos})", font, TEXT_COL),
        (f"World origin:   ({col_pos*ZONE_SIZE:,}, {row_pos*ZONE_SIZE:,})", font, TEXT_COL),
        (f"Destroyed: {destroyed_ratio:.3f}", font, TEXT_COL),
        (f"Intact:    {1.0-destroyed_ratio:.3f}", font, TEXT_COL),
        ("", font, TEXT_COL),
        ("Press ENTER to enter this world", font, (100, 255, 100)),
        (f"  seed = {seed}", font, (120,220,120)),
    ]
    y = py + 10
    for text, f, col in lines:
        if text:
            s = f.render(text, True, col)
            screen.blit(s, (px + 10, y))
        y += f.size("A")[1] + 4


def main():
    global CELL_SIZE
    parser = argparse.ArgumentParser(description="Backrooms complete seed map")
    parser.add_argument('--cell', type=int, default=CELL_SIZE,
                        help=f'Cell size in pixels at zoom=1 (default {CELL_SIZE})')
    args = parser.parse_args()
    CELL_SIZE = args.cell

    print("Backrooms Seed Map")
    print(f"Total seeds: {SEED_MAX+1:,}")
    print(f"Grid: {MAP_W} x {MAP_H} = {MAP_W*MAP_H:,} cells")
    print("Launching viewer — every cell is a real unique world.\n")

    run(args)


if __name__ == '__main__':
    main()