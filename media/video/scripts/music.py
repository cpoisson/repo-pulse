"""Synthesize a short, light, royalty-free background track (original; no samples).

uv run python media/video/scripts/music.py [seconds] -> media/video/public/music.wav
Warm major-seventh pads, a soft plucked arpeggio, a gentle sub bass and a quiet shaker at 92 BPM.
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 92
BEAT = 60 / BPM
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 72.0
OUT = Path(__file__).resolve().parents[1] / "public" / "music.wav"
rng = np.random.default_rng(7)

# Fmaj7 – Am7 – Dm9 – Bbmaj7(#11)-ish – C6 : bright, calm, "insight" mood
PROG = [
    [53, 57, 60, 64],   # F A C E
    [57, 60, 64, 67],   # A C E G
    [50, 57, 60, 64],   # D A C E
    [46, 53, 57, 62],   # Bb F A D
    [48, 55, 60, 64],   # C G C E
]
BARS_PER_CHORD = 2
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
t_all = np.arange(int(DUR * SR)) / SR
mix = np.zeros_like(t_all)


def env_adsr(n, a, d, s, r):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    e = np.full(n, s, dtype=float)
    e[:a] = np.linspace(0, 1, a) if a else 1
    e[a:a + d] = np.linspace(1, s, min(d, max(n - a, 0)))[: len(e[a:a + d])]
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def add(start, sig):
    i = int(start * SR)
    j = min(len(mix), i + len(sig))
    if i < len(mix):
        mix[i:j] += sig[: j - i]


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for k, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[k] = acc
    return y


bar = 4 * BEAT
chord_len = BARS_PER_CHORD * bar
n_chords = int(np.ceil(DUR / chord_len))
for ci in range(n_chords):
    chord = PROG[ci % len(PROG)]
    t0 = ci * chord_len
    n = int((chord_len + 1.2) * SR)
    t = np.arange(n) / SR
    # pad: detuned sines + soft 3rd harmonic, slow attack/release
    pad = np.zeros(n)
    for m in chord:
        f = hz(m + 12)
        for det in (-0.12, 0.0, 0.11):
            pad += np.sin(2 * np.pi * f * (1 + det / 100) * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    pad *= env_adsr(n, 1.4, 0.6, 0.85, 1.2) * 0.020
    add(t0, pad)
    # bass on beat 1 and 3
    for b in range(BARS_PER_CHORD * 4):
        if b % 2 == 0:
            nb = int(1.6 * BEAT * SR)
            tb = np.arange(nb) / SR
            f = hz(chord[0] - 12)
            bass = (np.sin(2 * np.pi * f * tb) + 0.25 * np.sin(4 * np.pi * f * tb)) * np.exp(-tb * 2.2)
            bass *= env_adsr(nb, 0.035, 0.1, 1.0, 0.2) * 0.09
            add(t0 + b * BEAT, bass)
    # pluck arpeggio in eighths after the intro
    if t0 >= 2 * bar:
        pattern = [0, 2, 1, 3, 2, 1, 3, 2]
        for e in range(BARS_PER_CHORD * 8):
            m = chord[pattern[e % 8]] + 24
            ne = int(0.9 * SR)
            te = np.arange(ne) / SR
            f = hz(m)
            pl = (np.sin(2 * np.pi * f * te) + 0.3 * np.sin(4 * np.pi * f * te) + 0.08 * np.sin(6 * np.pi * f * te))
            pl *= np.exp(-te * 6.0) * env_adsr(ne, 0.004, 0.05, 1.0, 0.05)
            vel = 0.026 if e % 2 == 0 else 0.018
            add(t0 + e * BEAT / 2, pl * vel)

# soft shaker on off-beats from bar 5, filtered noise
noise = rng.standard_normal(int(0.12 * SR))
shake = (noise - lowpass(noise, 5000)) * np.exp(-np.arange(len(noise)) / SR * 40) * 0.010
for k in range(int(DUR / (BEAT / 2))):
    tk = k * BEAT / 2
    if tk >= 4 * bar and k % 2 == 1:
        add(tk, shake * (1.0 if k % 4 == 3 else 0.6))

# gentle stereo: slightly different delays per channel, plus a short room echo
left = mix + 0.18 * np.concatenate([np.zeros(int(0.23 * SR)), mix])[: len(mix)]
right = mix + 0.18 * np.concatenate([np.zeros(int(0.31 * SR)), mix])[: len(mix)]
stereo = np.stack([left, right], 1)
fade_in, fade_out = int(1.5 * SR), int(4.0 * SR)
stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
stereo[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.5
stereo /= np.max(np.abs(stereo)) / 0.5   # peak -6 dBFS; it is background music
OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((stereo * 32767).astype("<i2").tobytes())
print(f"wrote {OUT} ({DUR:.0f}s)")
