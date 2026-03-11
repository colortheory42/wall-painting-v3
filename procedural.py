"""
Procedural zone generation.
Different zone types with varying properties for spatial variety.
"""


class ProceduralZone:
    """Represents a procedural zone with specific characteristics."""

    ZONE_TYPES = {
        'normal': {
            'pillar_density': 0.35,
            'wall_chance': 0.25,
            'ceiling_height_var': 8,
            'color_tint': (1.0, 1.0, 1.0)
        },
        'dense': {
            'pillar_density': 0.55,
            'wall_chance': 0.4,
            'ceiling_height_var': 5,
            'color_tint': (0.95, 0.95, 0.85)
        },
        'sparse': {
            'pillar_density': 0.15,
            'wall_chance': 0.1,
            'ceiling_height_var': 18,
            'color_tint': (1.05, 1.05, 1.15)
        },
        'maze': {
            'pillar_density': 0.7,
            'wall_chance': 0.6,
            'ceiling_height_var': 3,
            'color_tint': (0.9, 0.9, 0.8)
        },
        'open': {
            'pillar_density': 0.08,
            'wall_chance': 0.05,
            'ceiling_height_var': 30,
            'color_tint': (1.1, 1.1, 1.2)
        }
    }

    @staticmethod
    def get_zone_type(zone_x, zone_z, seed=12345):
        """Deterministic zone type selection based on coordinates."""
        hash_val = (zone_x * 73856093 + zone_z * 19349663 + seed * 83492791) & 0x7fffffff
        zone_index = hash_val % len(ProceduralZone.ZONE_TYPES)
        return list(ProceduralZone.ZONE_TYPES.keys())[zone_index]

    @staticmethod
    def get_zone_properties(zone_x, zone_z, seed=12345):
        """Get properties for a specific zone."""
        zone_type = ProceduralZone.get_zone_type(zone_x, zone_z, seed)
        props = ProceduralZone.ZONE_TYPES[zone_type].copy()

        # Add decay chance based on zone type
        decay_chances = {
            'normal': 0.20,
            'dense': 0.20,
            'sparse': 0.20,
            'maze': 0.20,
            'open': 0.20
        }
        props['decay_chance'] = decay_chances.get(zone_type, 0.05)

        return props