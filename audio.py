"""
Procedural audio generation.
Creates all sound effects at runtime using NumPy waveform synthesis.
Includes microphone capture + acoustic room processing.
"""

import numpy as np
import pygame
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

from config import SAMPLE_RATE

def low_pass(signal, kernel_size):
    kernel = np.ones(kernel_size) / kernel_size
    return np.convolve(signal, kernel, mode="same")

def generate_backrooms_hum():
    """Generate ambient droning hum."""
    duration = 10
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    drone = 0.15 * np.sin(2 * np.pi * 60 * t)
    drone += 0.12 * np.sin(2 * np.pi * 55 * t)
    drone += 0.10 * np.sin(2 * np.pi * 40 * t)
    drone += 0.08 * np.sin(2 * np.pi * 120 * t)
    drone += 0.05 * np.sin(2 * np.pi * 180 * t)

    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
    drone *= modulation
    noise = np.random.normal(0, 0.02, samples)
    drone += noise

    drone = drone / np.max(np.abs(drone)) * 0.6
    audio = np.array(drone * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio, audio))

    return pygame.sndarray.make_sound(stereo_audio)


def generate_footstep_sound():
    """Generate ambient footstep sound (distant)."""
    duration = 0.3
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    impact = np.exp(-t * 20) * np.sin(2 * np.pi * 80 * t)
    impact += np.exp(-t * 15) * np.sin(2 * np.pi * 120 * t) * 0.5
    reverb = np.exp(-t * 5) * np.random.normal(0, 0.1, samples)

    sound = impact + reverb * 0.3
    sound = sound / np.max(np.abs(sound)) * 0.7

    audio = np.array(sound * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio, audio))

    return pygame.sndarray.make_sound(stereo_audio)


def generate_player_footstep_sound(turn_factor=1.0):
    """Generate deep, soft carpet footstep (pressure into fabric).
    turn_factor: 0.0 (straight) → 1.0 (hard turn)
    """
    duration = 0.14
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    # Clamp for safety
    turn_factor = max(0.0, min(turn_factor, 1.0))

    # Fabric noise (very gentle)
    noise = np.random.uniform(-1, 1, samples)

    # Soft envelope: slow rise, smooth release
    attack = int(0.35 * samples)
    decay = samples - attack
    envelope = np.concatenate([
        np.linspace(0, 1, attack),
        np.linspace(1, 0, decay)
    ])

    # Directional carpet absorption (fiber shear when turning)
    kernel_size = int(65 + turn_factor * 25)
    muffled = low_pass(noise, kernel_size=kernel_size)

    # Deep pressure "crush" (felt, not heard)
    bass = (
        0.08 * np.sin(2 * np.pi * 38 * t) +
        0.04 * np.sin(2 * np.pi * 28 * t)
    ) * np.exp(-t * 18)

    sound = muffled * envelope * 0.3 + bass

    # Extremely conservative output level
    sound = sound / np.max(np.abs(sound)) * 0.32

    # Subtle stereo smear (body rotation, not panning)
    left = sound * (1.0 - turn_factor * 0.08)
    right = sound * (1.0 + turn_factor * 0.08)

    audio_l = np.array(left * 32767, dtype=np.int16)
    audio_r = np.array(right * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio_l, audio_r))

    return pygame.sndarray.make_sound(stereo_audio)


def generate_crouch_footstep_sound(turn_factor=1.0):
    """Generate ultra-soft, deep carpet crouch footstep (slow pressure).
    turn_factor: 0.0 (straight) → 1.0 (hard turn)
    """
    duration = 0.18
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    turn_factor = max(0.0, min(turn_factor, 1.0))

    # Very gentle fabric noise
    noise = np.random.uniform(-1, 1, samples)

    # Extra-slow, smooth envelope (no perceptible onset)
    attack = int(0.45 * samples)
    decay = samples - attack
    envelope = np.concatenate([
        np.linspace(0, 1, attack),
        np.linspace(1, 0, decay)
    ])

    # Strong absorption — more smear when turning
    kernel_size = int(80 + turn_factor * 30)
    muffled = low_pass(noise, kernel_size=kernel_size)

    # Deep, slow pressure (almost sub-audible)
    bass = (
        0.06 * np.sin(2 * np.pi * 32 * t) +
        0.03 * np.sin(2 * np.pi * 24 * t)
    ) * np.exp(-t * 14)

    sound = muffled * envelope * 0.25 + bass

    # Very low output level
    sound = sound / np.max(np.abs(sound)) * 0.24

    # Extremely subtle stereo drift
    left = sound * (1.0 - turn_factor * 0.06)
    right = sound * (1.0 + turn_factor * 0.06)

    audio_l = np.array(left * 32767, dtype=np.int16)
    audio_r = np.array(right * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio_l, audio_r))

    return pygame.sndarray.make_sound(stereo_audio)


def generate_electrical_buzz():
    """Generate electrical buzzing sound."""
    duration = 1.5
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    buzz = 0.2 * np.sin(2 * np.pi * 120 * t)
    buzz += 0.15 * np.sin(2 * np.pi * 240 * t)
    mod = np.sin(2 * np.pi * 8 * t) * 0.5 + 0.5
    buzz *= mod

    buzz = buzz / np.max(np.abs(buzz)) * 0.3
    audio = np.array(buzz * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio, audio))

    return pygame.sndarray.make_sound(stereo_audio)


def generate_destroy_sound():
    """Generate destruction sound for walls breaking."""
    duration = 1.0
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples, False)

    # Big impact
    impact = np.exp(-t * 8) * np.sin(2 * np.pi * 80 * t)
    impact += np.exp(-t * 10) * np.sin(2 * np.pi * 120 * t) * 0.8

    # Crumbling/debris
    crumble = np.random.normal(0, 0.4, samples) * np.exp(-t * 4)

    sound = impact + crumble * 0.7
    sound = sound / np.max(np.abs(sound)) * 0.8

    audio = np.array(sound * 32767, dtype=np.int16)
    stereo_audio = np.column_stack((audio, audio))

    return pygame.sndarray.make_sound(stereo_audio)


# =============================================================================
# MICROPHONE ACOUSTIC PROCESSOR
# =============================================================================

MIC_CHUNK     = 1024
REVERB_DELAYS = [0.013, 0.027, 0.043, 0.067]
REVERB_GAINS  = [0.50,  0.35,  0.22,  0.14]
_MAX_DELAY_S  = max(REVERB_DELAYS)


class MicProcessor:
    """
    Duplex sounddevice stream: mic in → room acoustics → speaker out.
    Everything happens inside the audio callback — no pygame, no queue,
    no dropped buffers. Continuous and gapless by design.
    """

    def __init__(self):
        self._running   = False
        self._stream    = None

        self._reverb    = 0.2
        self._left      = 0.8
        self._right     = 0.8
        self._occlusion = 1.0

        # Ring buffer for reverb delay lines (mono float32)
        self._ring      = None
        self._buf_size  = 0
        self._write_pos = 0

        self._level     = 0.0
        self._status    = "OFF"

        self.available  = SOUNDDEVICE_AVAILABLE

    def update_acoustics(self, acoustic_sample, occlusion=1.0):
        if acoustic_sample is None:
            return
        avg = 0.5 + acoustic_sample.reverb * 0.3
        l_b = min(1.0, 300.0 / max(1.0, acoustic_sample.left_dist))
        r_b = min(1.0, 300.0 / max(1.0, acoustic_sample.right_dist))
        self._left      = min(1.0, avg + r_b * 0.15)
        self._right     = min(1.0, avg + l_b * 0.15)
        self._reverb    = acoustic_sample.reverb
        self._occlusion = occlusion

    def get_status(self):
        if not self.available:
            return ("NO SOUNDDEVICE", 0.0)
        return (self._status, self._level)

    def start(self):
        if not self.available:
            print("[MicProcessor] sounddevice not installed — run: pip install sounddevice")
            return

        self._buf_size  = int(SAMPLE_RATE * (_MAX_DELAY_S + 0.02)) + MIC_CHUNK
        self._ring      = np.zeros(self._buf_size, dtype=np.float32)
        self._write_pos = 0
        self._status    = "starting"
        self._running   = True

        try:
            self._stream = sd.Stream(
                samplerate = SAMPLE_RATE,
                blocksize  = MIC_CHUNK,
                channels   = (1, 2),    # mono in, stereo out
                dtype      = 'float32',
                callback   = self._callback,
                latency    = 'low',
            )
            self._stream.start()
            self._status = "LIVE"
            print("[MicProcessor] Mic capture started.")
        except Exception as e:
            self._status  = f"ERR: {e}"
            self._running = False
            print(f"[MicProcessor] Error: {e}")

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._status = "OFF"

    def _callback(self, indata, outdata, frames, time_info, status):
        if not self._running:
            outdata[:] = 0
            return

        mono   = indata[:, 0]
        reverb = self._reverb
        l_vol  = self._left
        r_vol  = self._right
        occ    = self._occlusion

        # RMS level for HUD
        self._level = min(1.0, float(np.sqrt(np.mean(mono * mono))) * 6.0)

        ring  = self._ring
        size  = self._buf_size
        wpos  = self._write_pos

        # Write incoming samples into ring buffer
        for i in range(frames):
            ring[(wpos + i) % size] = mono[i]

        # Build output: dry signal + reverb taps
        out = mono.copy()
        if reverb > 0.02:
            for delay_s, gain in zip(REVERB_DELAYS, REVERB_GAINS):
                d = int(SAMPLE_RATE * delay_s)
                w = gain * reverb
                for i in range(frames):
                    out[i] += ring[(wpos + i - d) % size] * w

        self._write_pos = (wpos + frames) % size

        outdata[:, 0] = np.clip(out * l_vol * occ, -1.0, 1.0)
        outdata[:, 1] = np.clip(out * r_vol * occ, -1.0, 1.0)
