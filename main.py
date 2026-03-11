"""
The Backrooms - Main Game Loop
Destructible walls with pixel debris physics.

Includes:
- MENU / PLAYING / PAUSED states
- DRAWING SYSTEM: right-click to draw on walls/pillars
"""

import pygame
import sys
from enum import Enum, auto

from config import *
from engine import BackroomsEngine
from drawing_system import (
    DRAW_COLORS,
    world_to_wall_uv, pillar_world_to_uv,
    get_wall_hit_point, get_pillar_hit_point_and_face
)
from audio import (
    generate_backrooms_hum,
    generate_footstep_sound,
    generate_player_footstep_sound,
    generate_crouch_footstep_sound,
    generate_electrical_buzz,
    generate_destroy_sound,
    MicProcessor
)
from save_system import SaveSystem


class GameState(Enum):
    MENU = auto()
    PLAYING = auto()
    PAUSED = auto()


def set_mouse_locked(engine, locked: bool):
    if engine.mouse_look != locked:
        engine.toggle_mouse()


def _draw_dim_overlay(screen, alpha=180):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, max(0, min(255, alpha))))
    screen.blit(overlay, (0, 0))


def _draw_centered_text(screen, font, text, y, color=(220, 220, 220)):
    surf = font.render(text, True, color)
    x = WIDTH // 2 - surf.get_width() // 2
    screen.blit(surf, (x, y))
    return surf


def _start_hum(hum_sound):
    if hum_sound:
        hum_sound.play(loops=-1)
        hum_sound.set_volume(0.4)


def _stop_hum(hum_sound):
    if hum_sound:
        hum_sound.stop()


def _draw_drawing_ui(screen, ds, font, small_font):
    """Draw drawing mode indicator."""
    color_rgb = ds.draw_color
    label = f"DRAW: {ds.color_name()}"
    surf = small_font.render(label, True, (240, 240, 240))
    bw = surf.get_width() + 14
    bh = surf.get_height() + 10
    bx = WIDTH - bw - 10
    by = HEIGHT - bh - 10
    pygame.draw.rect(screen, (20, 20, 30), (bx, by, bw, bh))
    pygame.draw.rect(screen, color_rgb, (bx, by, bw, bh), 2)
    screen.blit(surf, (bx + 7, by + 5))
    pygame.draw.circle(screen, color_rgb, (bx - 10, by + bh // 2), 6)

    hints = small_font.render("RMB:Draw  1-9:Color", True, (140, 140, 160))
    screen.blit(hints, (10, HEIGHT - hints.get_height() - 8))


def main():
    import argparse
    _SEED_MAX = 9_223_372_036_854_775_807
    parser = argparse.ArgumentParser()
    parser.add_argument("seed", nargs="?", default=None)
    args = parser.parse_args()

    if args.seed is not None:
        try:
            seed_arg = max(0, min(_SEED_MAX, int(args.seed)))
            print(f"[main] Using seed: {seed_arg:,}")
        except ValueError:
            seed_arg = None
    else:
        raw = input(f"Enter seed (0-{_SEED_MAX}) or press Enter for random: ").strip()
        seed_arg = max(0, min(_SEED_MAX, int(raw))) if raw.isdigit() else None

    pygame.init()
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, AUDIO_BUFFER_SIZE)
    pygame.mixer.init()

    SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN if FULLSCREEN else 0)
    pygame.display.set_caption("The Backrooms - Destructible")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 14)
    small_font = pygame.font.SysFont("consolas", 12)
    title_font = pygame.font.SysFont("consolas", 28, bold=True)

    engine = BackroomsEngine(WIDTH, HEIGHT, world_seed=seed_arg)
    engine.mouse_look = False
    pygame.mouse.set_visible(True)
    pygame.event.set_grab(False)

    # drawing_system is created inside engine.__init__
    ds = engine.drawing_system

    print("Generating ambient sounds...")
    hum_sound = generate_backrooms_hum()
    footstep_sound = generate_footstep_sound()
    player_footstep_sound = generate_player_footstep_sound()
    crouch_footstep_sound = generate_crouch_footstep_sound()
    buzz_sound = generate_electrical_buzz()
    destroy_sound = generate_destroy_sound()

    mic = MicProcessor()
    mic.start()

    sound_effects = {
        'footstep': footstep_sound,
        'player_footstep': player_footstep_sound,
        'crouch_footstep': crouch_footstep_sound,
        'buzz': buzz_sound,
        'destroy': destroy_sound
    }

    show_help = True
    help_timer = 5.0
    save_message = ""
    save_message_timer = 0.0

    state = GameState.MENU

    if not engine.mouse_look:
        engine.toggle_mouse()

    hum_playing = False

    # Drawing input state
    drawing_mode = False
    drawing_surface_key = None
    drawing_surface_type = None
    drawing_pillar_face = None

    running = True
    while running:
        dt = clock.tick(FPS) / 1000
        mouse_rel = None

        if state == GameState.PLAYING:
            if show_help and help_timer > 0:
                help_timer -= dt
                if help_timer <= 0:
                    show_help = False
            if save_message_timer > 0:
                save_message_timer -= dt
                if save_message_timer <= 0:
                    save_message = ""

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEMOTION and state == GameState.PLAYING and engine.mouse_look:
                mouse_rel = event.rel

            if event.type == pygame.KEYDOWN:

                if state == GameState.MENU:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        state = GameState.PLAYING
                        set_mouse_locked(engine, True)
                        show_help = True
                        help_timer = 5.0
                        save_message = ""
                        save_message_timer = 0.0
                        if not hum_playing:
                            _start_hum(hum_sound)
                            hum_playing = True
                    if event.key == pygame.K_F9:
                        save_data = SaveSystem.load_game(slot=1)
                        if save_data:
                            engine.load_from_save(save_data)
                            save_message = "Loaded slot 1."
                            save_message_timer = 2.0
                        else:
                            save_message = "No save found in slot 1."
                            save_message_timer = 2.0

                elif state == GameState.PLAYING:
                    if event.key == pygame.K_ESCAPE:
                        if engine.mouse_look:
                            engine.toggle_mouse()
                        set_mouse_locked(engine, False)
                        state = GameState.PAUSED
                        continue

                    if event.key == pygame.K_r:
                        engine.toggle_render_scale()
                    if event.key == pygame.K_h:
                        show_help = not show_help
                        if show_help:
                            help_timer = 999
                    if event.key == pygame.K_F5:
                        SaveSystem.save_game(engine, slot=1)
                        save_message = "Game saved to slot 1!"
                        save_message_timer = 3.0
                    if event.key == pygame.K_F9:
                        save_data = SaveSystem.load_game(slot=1)
                        if save_data:
                            engine.load_from_save(save_data)
                            save_message = "Game loaded from slot 1!"
                            save_message_timer = 3.0
                        else:
                            save_message = "No save found in slot 1!"
                            save_message_timer = 3.0
                    if event.key == pygame.K_e:
                        target = engine.find_targeted_wall_or_pillar()
                        if target:
                            target_type, target_key = target
                            if target_type == 'wall':
                                engine.destroy_wall(target_key, sound_effects['destroy'])
                            elif target_type == 'pillar':
                                engine.destroy_pillar(target_key, sound_effects['destroy'])

                    # Color 1-9
                    color_keys = {
                        pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3,
                        pygame.K_4: 4, pygame.K_5: 5, pygame.K_6: 6,
                        pygame.K_7: 7, pygame.K_8: 8, pygame.K_9: 9,
                    }
                    if event.key in color_keys:
                        ds.set_color(color_keys[event.key])

                elif state == GameState.PAUSED:
                    if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                        state = GameState.PLAYING
                        set_mouse_locked(engine, True)
                        continue
                    if event.key == pygame.K_BACKSPACE:
                        state = GameState.MENU
                        if not engine.mouse_look:
                            engine.toggle_mouse()
                        continue
                    if event.key == pygame.K_q:
                        running = False

            # Mouse buttons
            if event.type == pygame.MOUSEBUTTONDOWN and state == GameState.PLAYING:

                # LEFT CLICK — destroy
                if event.button == 1:
                    target = engine.find_targeted_wall_or_pillar()
                    if target:
                        target_type, target_key = target
                        if target_type == 'wall':
                            engine.destroy_wall(target_key, sound_effects['destroy'])
                        elif target_type == 'pillar':
                            engine.destroy_pillar(target_key, sound_effects['destroy'])

                # RIGHT CLICK — draw
                if event.button == 3 and not ds.drawing_active:
                    target = engine.find_targeted_wall_or_pillar()
                    if target:
                        target_type, target_key = target
                        if target_type == 'wall':
                            hit_pt, wall_key = get_wall_hit_point(engine, target)
                            if hit_pt and wall_key:
                                uv = world_to_wall_uv(hit_pt, wall_key)
                                ds.start_stroke(wall_key, uv)
                                drawing_mode = True
                                drawing_surface_key = wall_key
                                drawing_surface_type = 'wall'
                                drawing_pillar_face = None
                        elif target_type == 'pillar':
                            hit_pt, pillar_key, face = get_pillar_hit_point_and_face(engine, target)
                            if hit_pt and pillar_key is not None and face is not None:
                                uv = pillar_world_to_uv(hit_pt, pillar_key, face)
                                ds.start_pillar_stroke(pillar_key, face, uv)
                                drawing_mode = True
                                drawing_surface_key = pillar_key
                                drawing_surface_type = 'pillar'
                                drawing_pillar_face = face

            if event.type == pygame.MOUSEBUTTONUP and state == GameState.PLAYING:
                if event.button == 3 and drawing_mode:
                    ds.end_stroke()
                    drawing_mode = False
                    drawing_surface_key = None
                    drawing_surface_type = None
                    drawing_pillar_face = None

        # Continuous draw while RMB held
        if drawing_mode and state == GameState.PLAYING:
            target = engine.find_targeted_wall_or_pillar()
            if target:
                target_type, target_key = target
                if drawing_surface_type == 'wall' and target_type == 'wall' and target_key == drawing_surface_key:
                    hit_pt, wall_key = get_wall_hit_point(engine, target)
                    if hit_pt:
                        uv = world_to_wall_uv(hit_pt, wall_key)
                        ds.add_to_stroke(uv)
                elif drawing_surface_type == 'pillar' and target_type == 'pillar' and target_key == drawing_surface_key:
                    hit_pt, pillar_key, face = get_pillar_hit_point_and_face(engine, target)
                    if hit_pt and face == drawing_pillar_face:
                        uv = pillar_world_to_uv(hit_pt, pillar_key, face)
                        ds.add_to_stroke(uv)

        # Update + Render
        if state == GameState.MENU:
            engine.render(SCREEN)
            _draw_dim_overlay(SCREEN, alpha=190)
            _draw_centered_text(SCREEN, title_font, "THE BACKROOMS", HEIGHT // 2 - 120, (250, 240, 150))
            _draw_centered_text(SCREEN, font, "Destructible • Procedural • Infinite", HEIGHT // 2 - 80, (200, 220, 250))
            _draw_centered_text(SCREEN, font, "Press ENTER to enter", HEIGHT // 2 - 10, (220, 220, 220))
            _draw_centered_text(SCREEN, font, "Press ESC to quit", HEIGHT // 2 + 20, (180, 180, 180))
            _draw_centered_text(SCREEN, small_font, "Tip: F9 loads Slot 1 from the menu", HEIGHT // 2 + 60, (160, 160, 160))
            if save_message and save_message_timer > 0:
                _draw_centered_text(SCREEN, font, save_message, HEIGHT // 2 + 95, (100, 255, 100))
            pygame.display.flip()
            continue

        if state == GameState.PAUSED:
            engine.render(SCREEN)
            _draw_dim_overlay(SCREEN, alpha=170)
            _draw_centered_text(SCREEN, title_font, "PAUSED", HEIGHT // 2 - 90, (250, 240, 150))
            _draw_centered_text(SCREEN, font, "ENTER / ESC: Resume", HEIGHT // 2 - 20, (220, 220, 220))
            _draw_centered_text(SCREEN, font, "BACKSPACE: Return to Menu", HEIGHT // 2 + 10, (200, 200, 200))
            _draw_centered_text(SCREEN, font, "Q: Quit", HEIGHT // 2 + 40, (180, 180, 180))
            pygame.display.flip()
            continue

        # PLAYING
        keys = pygame.key.get_pressed()
        engine.update(dt, keys, mouse_rel)
        engine.update_sounds(dt, sound_effects)
        mic.update_acoustics(engine.acoustic_sample)
        engine.update_player_footsteps(
            dt,
            sound_effects['player_footstep'],
            sound_effects['crouch_footstep']
        )
        engine.update_flicker(dt)
        engine.update_render_scale(dt)

        engine.render(SCREEN)

        _draw_drawing_ui(SCREEN, ds, font, small_font)

        if save_message:
            save_msg_surface = font.render(save_message, True, (100, 255, 100))
            msg_x = WIDTH // 2 - save_msg_surface.get_width() // 2
            SCREEN.blit(save_msg_surface, (msg_x, 70))

        if show_help:
            help_y = HEIGHT - 310
            help_texts = [
                "=== CONTROLS ===",
                "WASD: Move | M: Mouse Look | JL: Turn",
                "SHIFT: Run | C: Crouch | SPACE: Jump",
                "LEFT CLICK or E: Destroy Wall",
                "R: Toggle Performance | H: Help | ESC: Pause",
                "=== DRAWING ===",
                "RIGHT CLICK: Draw on wall (hold to draw)",
                "1-9: Change color",
                "=== SAVE/LOAD ===",
                "F5: Quick Save (Slot 1) | F9: Quick Load (Slot 1)",
            ]
            for i, text in enumerate(help_texts):
                help_surface = font.render(text, True, (250, 240, 150))
                SCREEN.blit(help_surface, (10, help_y + i * 25))

        pygame.display.flip()

    try:
        _stop_hum(hum_sound)
    except Exception:
        pass
    mic.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
