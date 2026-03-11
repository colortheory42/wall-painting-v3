"""
Save/load system.
Handles game state persistence to JSON files.
"""

import os
import json
from datetime import datetime
from config import SAVE_DIR


class SaveSystem:

    @staticmethod
    def ensure_save_dir():
        if not os.path.exists(SAVE_DIR):
            os.makedirs(SAVE_DIR)

    @staticmethod
    def get_save_path(slot=1):
        SaveSystem.ensure_save_dir()
        return os.path.join(SAVE_DIR, f"save_slot_{slot}.json")

    @staticmethod
    def save_game(engine, slot=1):
        save_data = {
            'version': '1.1',
            'timestamp': datetime.now().isoformat(),
            'player': {
                'x': engine.x,
                'y': engine.y,
                'z': engine.z,
                'pitch': engine.pitch,
                'yaw': engine.yaw
            },
            'world': {
                'seed': engine.world_seed,
                'destroyed_walls': [list(wall) for wall in engine.destroyed_walls]
            },
            'stats': {
                'play_time': engine.play_time
            },
            'drawings': engine.drawing_system.get_state_for_save(),
        }
        save_path = SaveSystem.get_save_path(slot)
        with open(save_path, 'w') as f:
            json.dump(save_data, f, indent=2)
        print(f"Game saved to slot {slot}")
        return True

    @staticmethod
    def load_game(slot=1):
        save_path = SaveSystem.get_save_path(slot)
        if not os.path.exists(save_path):
            print(f"No save found in slot {slot}")
            return None
        try:
            with open(save_path, 'r') as f:
                save_data = json.load(f)
            print(f"Game loaded from slot {slot}")
            return save_data
        except Exception as e:
            print(f"Error loading save: {e}")
            return None

    @staticmethod
    def list_saves():
        SaveSystem.ensure_save_dir()
        saves = []
        for i in range(1, 6):
            save_path = SaveSystem.get_save_path(i)
            if os.path.exists(save_path):
                try:
                    with open(save_path, 'r') as f:
                        data = json.load(f)
                    saves.append({
                        'slot': i,
                        'timestamp': data.get('timestamp', 'Unknown'),
                        'play_time': data.get('stats', {}).get('play_time', 0)
                    })
                except:
                    pass
        return saves
