"""Original synthesized background-music styles (no samples, no third-party audio).

uv run python media/video/scripts/music_styles.py --style lofi --seconds 20 --out /tmp/lofi.wav
Styles: lofi, launch, ambient, acoustic, electronic. All mono-compatible stereo, 44.1 kHz, ~-16 LUFS.
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 44100
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)


class Mix:
    def __init__(self, seconds: float, seed: int = 3):
        self.n = int(seconds * SR)
        self.bus: dict[str, np.ndarray] = {}
        self.rng = np.random.default_rng(seed)

    def add(self, bus: str, t: float, sig: np.ndarray, gain: float = 1.0):
        b = self.bus.setdefault(bus, np.zeros(self.n))
        i = int(t * SR)
        if i >= self.n or i < 0:
            return
        j = min(self.n, i + len(sig))
        b[i:j] += sig[: j - i] * gain


# ---------------------------------------------------------------- DSP helpers
def tt(sec):
    return np.arange(int(sec * SR)) / SR


def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if hi:
        g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo:
        g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    return np.fft.irfft(X * g, len(x))


def reverb(x, seconds=2.2, wet=0.25, tone=6000, seed=5):
    rng = np.random.default_rng(seed)
    t = tt(seconds)
    ir = rng.standard_normal(len(t)) * np.exp(-t * 6.9 / seconds)
    ir = fft_filter(ir, lo=150, hi=tone)
    ir[: int(0.012 * SR)] = 0  # pre-delay
    ir /= np.sqrt(np.sum(ir ** 2))
    n = len(x) + len(ir)
    y = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)]
    return x * (1 - wet) + y * wet * 1.6


def adsr(n, a=0.005, d=0.1, s=0.7, r=0.2):
    e = np.full(n, float(s))
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    A = min(A, n)
    e[:A] = np.linspace(0, 1, A)
    D = min(D, max(n - A, 0))
    e[A:A + D] = np.linspace(1, s, D)
    R = min(R, n)
    if R:
        e[-R:] *= np.linspace(1, 0, R)
    return e


# ---------------------------------------------------------------- instruments
def epiano(m, dur, vel=1.0):
    """FM electric piano: decaying modulation index + small bell tine."""
    t = tt(dur)
    f = hz(m)
    idx = 1.8 * np.exp(-t * 6) + 0.25
    car = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    tine = 0.12 * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t * 14)
    return (car + tine) * np.exp(-t * 1.3) * adsr(len(t), 0.004, 0.05, 1, 0.25) * vel


def piano(m, dur, vel=1.0):
    t = tt(dur)
    f = hz(m)
    B = 0.0004
    sig = np.zeros_like(t)
    for k in range(1, 9):
        fk = k * f * np.sqrt(1 + B * k * k)
        if fk > SR / 2.2:
            break
        sig += np.sin(2 * np.pi * fk * t) / k ** 1.4 * np.exp(-t * (0.6 + 0.55 * k))
    hammer = np.random.default_rng(int(m)).standard_normal(len(t)) * np.exp(-t * 90) * 0.03
    return (sig + hammer) * adsr(len(t), 0.002, 0.05, 1, 0.3) * vel


def marimba(m, dur=0.9, vel=1.0):
    t = tt(dur)
    f = hz(m)
    sig = np.sin(2 * np.pi * f * t) * np.exp(-t * 5) + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t * 18) \
        + 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 40)
    return sig * adsr(len(t), 0.002, 0.02, 1, 0.05) * vel


def pluck(m, dur=1.4, vel=1.0, bright=0.5, seed=0):
    """Karplus-Strong string, vectorised per period."""
    f = hz(m)
    N = max(2, int(SR / f))
    n = int(dur * SR)
    y = np.zeros(n + N)
    rng = np.random.default_rng(seed + int(m))
    y[:N] = fft_filter(rng.uniform(-1, 1, N * 8), hi=2000 + 6000 * bright)[:N]
    decay = 0.996
    for start in range(N, n + N, N):
        prev = y[start - N:start]
        nxt = 0.5 * (prev + np.roll(prev, 1)) * decay
        end = min(start + N, n + N)
        y[start:end] = nxt[: end - start]
    return y[N:] * vel * adsr(n, 0.001, 0.01, 1, 0.08)


def pad(midis, dur, voices=5, detune=0.18, cutoff=2400, attack=1.2):
    t = tt(dur)
    sig = np.zeros_like(t)
    for m in midis:
        for v in range(voices):
            d = (v - (voices - 1) / 2) * detune / max(voices - 1, 1)
            f = hz(m) * 2 ** (d / 12)
            ph = np.random.default_rng(m * 10 + v).uniform(0, 1)
            saw = 2 * ((f * t + ph) % 1) - 1
            sig += saw
    sig = fft_filter(sig, hi=cutoff)
    return sig / (len(midis) * voices) * adsr(len(t), attack, 0.4, 0.9, min(1.0, dur / 3))


def sine_pad(midis, dur, attack=1.5):
    t = tt(dur)
    sig = sum(np.sin(2 * np.pi * hz(m) * t) + 0.3 * np.sin(2 * np.pi * hz(m) * 2.001 * t) for m in midis)
    return sig / len(midis) * adsr(len(t), attack, 0.5, 0.85, min(1.5, dur / 3))


def sub(m, dur):
    t = tt(dur)
    f = hz(m)
    return (np.sin(2 * np.pi * f * t) + 0.15 * np.sin(4 * np.pi * f * t)) * adsr(len(t), 0.02, 0.1, 0.9, 0.08)


def kick(soft=1.0):
    t = tt(0.45)
    f = 45 + 75 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * (7 / soft)) * adsr(len(t), 0.001, 0.02, 1, 0.05)


def snare(rng, tone=180):
    t = tt(0.3)
    noise = fft_filter(rng.standard_normal(len(t)), lo=1200, hi=9000) * np.exp(-t * 18)
    body = np.sin(2 * np.pi * tone * t) * np.exp(-t * 30)
    return noise * 0.8 + body * 0.5


def clap(rng):
    t = tt(0.35)
    env = np.zeros_like(t)
    for k, o in enumerate((0.0, 0.011, 0.022)):
        i = int(o * SR)
        env[i:] += np.exp(-(t[i:] - o) * (90 if k < 2 else 16))
    return fft_filter(rng.standard_normal(len(t)), lo=900, hi=7000) * env * 0.6


def hat(rng, open_=False):
    t = tt(0.4 if open_ else 0.07)
    return fft_filter(rng.standard_normal(len(t)), lo=7000) * np.exp(-t * (12 if open_ else 70))


def shaker(rng):
    t = tt(0.12)
    return fft_filter(rng.standard_normal(len(t)), lo=4500, hi=12000) * np.sin(np.pi * np.minimum(t / 0.12, 1)) ** 2


def vinyl(rng, n):
    hiss = fft_filter(rng.standard_normal(n), lo=800, hi=5000) * 0.012
    pops = np.zeros(n)
    idx = rng.choice(n, size=max(1, n // SR * 7), replace=False)
    pops[idx] = rng.uniform(0.2, 1, len(idx)) * rng.choice([-1, 1], len(idx))
    pops = fft_filter(pops, lo=1500) * 0.25
    return hiss + pops


def duck(n, times, depth=0.6, release=0.22):
    g = np.ones(n)
    r = int(release * SR)
    shape = 1 - depth * np.exp(-np.linspace(0, 5, r))
    for tk in times:
        i = int(tk * SR)
        j = min(n, i + r)
        if i < n:
            g[i:j] = np.minimum(g[i:j], shape[: j - i])
    return g


# ---------------------------------------------------------------- styles
def style_lofi(S):
    mx = Mix(S, 11)
    bpm, beat = 82, 60 / 82
    bar = 4 * beat
    prog = [[50, 57, 60, 64, 65], [55, 59, 62, 65, 69], [48, 55, 59, 62, 64], [57, 61, 64, 67, 70]]  # Dm9 G13 Cmaj9 A7b9
    for b in range(int(S / bar) + 1):
        ch = prog[b % 4]
        t0 = b * bar
        for k, m in enumerate(ch):  # slightly strummed
            mx.add("keys", t0 + k * 0.018, epiano(m, bar * 0.95, 0.30))
        mx.add("keys", t0 + 2.5 * beat, epiano(ch[-1] + 12, 0.8, 0.12))
        mx.add("bass", t0, sub(ch[0] - 12, beat * 1.5), 0.35)
        mx.add("bass", t0 + 2.5 * beat, sub(ch[0] - 12, beat * 1.0), 0.25)
        if b >= 1:
            for q in range(4):
                if q in (0,) or (q == 2 and b % 2):
                    mx.add("drums", t0 + q * beat, kick(1.2), 0.55)
                if q in (1, 3):
                    mx.add("drums", t0 + q * beat, snare(mx.rng, 200), 0.28)
            for e in range(8):
                swing = 0.075 * beat if e % 2 else 0
                mx.add("drums", t0 + e * beat / 2 + swing, hat(mx.rng), 0.10 if e % 2 else 0.14)
    keys = fft_filter(mx.bus["keys"], hi=3800)
    out = reverb(keys, 1.8, 0.28) + mx.bus["bass"] + fft_filter(mx.bus["drums"], hi=7000) + vinyl(mx.rng, mx.n)
    return out, "Lo-fi keys"


def style_launch(S):
    mx = Mix(S, 21)
    bpm, beat = 112, 60 / 112
    bar = 4 * beat
    prog = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]  # C G Am F
    arp = [0, 1, 2, 1, 2, 0, 1, 2]
    kicks = []
    for b in range(int(S / bar) + 1):
        ch = prog[b % 4]
        t0 = b * bar
        mx.add("pad", t0, pad([m + 12 for m in ch], bar, voices=4, cutoff=3000, attack=0.08), 0.22)
        for e in range(8):
            m = ch[arp[e]] + 12 + (12 if e in (3, 7) else 0)
            mx.add("mallet", t0 + e * beat / 2, marimba(m, 0.7, 0.5 if e % 2 else 0.65))
        mx.add("bass", t0, sub(ch[0] - 12, beat * 0.9), 0.4)
        mx.add("bass", t0 + 2 * beat, sub(ch[0] - 12, beat * 0.9), 0.35)
        if b >= 1:
            for q in range(4):
                mx.add("drums", t0 + q * beat, kick(0.9), 0.55)
                kicks.append(t0 + q * beat)
                if q in (1, 3):
                    mx.add("drums", t0 + q * beat, clap(mx.rng), 0.35)
                mx.add("drums", t0 + q * beat + beat / 2, hat(mx.rng, open_=(q == 3)), 0.12)
    g = duck(mx.n, kicks, 0.55)
    out = reverb(mx.bus["pad"] * g, 1.5, 0.3) + reverb(mx.bus["mallet"], 1.2, 0.2) + mx.bus["bass"] * g + mx.bus.get("drums", 0)
    return out, "Bright launch"


def style_ambient(S):
    mx = Mix(S, 31)
    beat = 60 / 68
    bar = 4 * beat
    prog = [[53, 60, 64, 69], [50, 57, 60, 65], [55, 62, 65, 69], [48, 55, 64, 67]]  # Fmaj7 Dm7 G7sus Cadd9
    motif = [(0, 76, 0.5), (1.5, 74, 0.4), (2, 72, 0.45), (3, 69, 0.35)]
    for b in range(int(S / bar) + 1):
        ch = prog[b % 4]
        t0 = b * bar
        mx.add("pad", t0, sine_pad(ch, bar + 1.5, attack=1.8), 0.18)
        mx.add("piano", t0, piano(ch[0] - 12, 3.0, 0.45))
        for k, (beat_off, m, v) in enumerate(motif):
            if b % 2 == 1 and k == 3:
                m = 67
            mx.add("piano", t0 + beat_off * beat, piano(m, 2.6, v))
    out = reverb(mx.bus["piano"], 3.5, 0.42, tone=5000) + reverb(fft_filter(mx.bus["pad"], hi=2500), 4.0, 0.5)
    return out, "Ambient piano"


def style_acoustic(S):
    mx = Mix(S, 41)
    bpm, beat = 100, 60 / 100
    bar = 4 * beat
    prog = [[52, 59, 64, 67, 71], [48, 55, 60, 64, 67], [55, 62, 67, 71, 74], [50, 57, 62, 66, 69]]  # Em C G D (voiced)
    pattern = [0, 2, 3, 4, 1, 3, 2, 4]
    for b in range(int(S / bar) + 1):
        ch = prog[b % 4]
        t0 = b * bar
        for e in range(8):
            m = ch[pattern[e]]
            mx.add("gtr", t0 + e * beat / 2, pluck(m, 1.6, 0.55 if e % 2 else 0.7, bright=0.45, seed=b * 8 + e))
        mx.add("bass", t0, pluck(ch[0] - 12, 2.0, 0.6, bright=0.2), 1.0)
        if b >= 1:
            for q in range(4):
                if q in (0, 2):
                    mx.add("drums", t0 + q * beat, kick(1.1), 0.45)
                if q in (1, 3):
                    mx.add("drums", t0 + q * beat, snare(mx.rng, 210), 0.18)
            for s16 in range(16):
                mx.add("drums", t0 + s16 * beat / 4, shaker(mx.rng), 0.08 if s16 % 2 else 0.12)
    out = reverb(mx.bus["gtr"], 1.6, 0.25) + fft_filter(mx.bus["bass"], hi=600) * 0.8 + mx.bus.get("drums", 0)
    return out, "Acoustic pluck"


def style_electronic(S):
    mx = Mix(S, 51)
    bpm, beat = 120, 0.5
    bar = 4 * beat
    prog = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 52, 55, 59], [55, 59, 62, 65]]  # Am7 Fmaj7 Cmaj7 G7
    kicks = []
    for b in range(int(S / bar) + 1):
        ch = prog[b % 4]
        t0 = b * bar
        mx.add("pad", t0, pad([m + 12 for m in ch], bar, voices=7, detune=0.28, cutoff=2600 + 900 * (b % 2), attack=0.02), 0.35)
        for e in (0, 3, 6):
            mx.add("bass", t0 + e * beat / 2, sub(ch[0] - 24, beat * 0.8), 0.5)
        if b >= 1:
            for q in range(4):
                mx.add("drums", t0 + q * beat, kick(0.85), 0.6)
                kicks.append(t0 + q * beat)
                if q in (1, 3):
                    mx.add("drums", t0 + q * beat, snare(mx.rng, 190), 0.22)
            for s16 in range(16):
                vel = 0.13 if s16 % 4 == 2 else 0.06
                mx.add("drums", t0 + s16 * beat / 4, hat(mx.rng, open_=(s16 % 8 == 6)), vel)
    g = duck(mx.n, kicks, 0.7, 0.3)
    out = reverb(mx.bus["pad"] * g, 2.0, 0.3) + mx.bus["bass"] * g + mx.bus.get("drums", 0)
    return out, "Chill electronic"


# ---------------------------------------------------------------- chill-electronic variations
def saw_note(m, dur, cutoff=1800, env_amt=2500, decay=6.0, voices=3, detune=0.12, seed=0):
    """Detuned saw with a decaying filter envelope (cut in two bands for speed)."""
    t = tt(dur)
    sig = np.zeros_like(t)
    for v in range(voices):
        f = hz(m) * 2 ** (((v - (voices - 1) / 2) * detune / max(voices - 1, 1)) / 12)
        sig += 2 * ((f * t + (seed * 0.37 + v * 0.21) % 1) % 1) - 1
    bright = fft_filter(sig, hi=cutoff + env_amt)
    dark = fft_filter(sig, hi=cutoff)
    w = np.exp(-t * decay)
    return (bright * w + dark * (1 - w)) / voices * adsr(len(t), 0.004, 0.08, 0.8, 0.06)


def rim(rng):
    t = tt(0.08)
    return (np.sin(2 * np.pi * 1700 * t) * 0.6 + fft_filter(rng.standard_normal(len(t)), lo=2000) * 0.4) * np.exp(-t * 60)


def bell(m, dur=1.2, vel=1.0):
    t = tt(dur)
    f = hz(m)
    return (np.sin(2 * np.pi * f * t + 2.0 * np.exp(-t * 4) * np.sin(2 * np.pi * f * 3.5 * t))) * np.exp(-t * 3.2) * vel


def style_elec_deep(S):
    """Deep-house glow: offbeat open hats, e-piano minor-9 stabs ducked by the kick, round sub."""
    mx = Mix(S, 61)
    beat = 60 / 118
    bar = 4 * beat
    prog = [[57, 60, 64, 67, 71], [53, 57, 60, 64, 67], [55, 59, 62, 65, 69], [52, 55, 59, 62, 66]]  # Am9 Fmaj9 G9 Em9
    kicks = []
    for b in range(int(S / bar) + 1):
        ch, t0 = prog[b % 4], b * bar
        mx.add("pad", t0, pad([m + 12 for m in ch[:4]], bar, voices=5, detune=0.22, cutoff=1800, attack=0.3), 0.20)
        for st in (0.5, 1.75, 2.5, 3.5):  # syncopated chord stabs
            for k, m in enumerate(ch):
                mx.add("keys", t0 + st * beat + k * 0.006, epiano(m + 12, 0.45, 0.18))
        for e in (0, 1.5, 2.5, 3.0):
            mx.add("bass", t0 + e * beat, sub(ch[0] - 24, beat * 0.45), 0.55)
        if b >= 1:
            for q in range(4):
                mx.add("drums", t0 + q * beat, kick(0.9), 0.62)
                kicks.append(t0 + q * beat)
                mx.add("drums", t0 + q * beat + beat / 2, hat(mx.rng, open_=True), 0.10)
                if q in (1, 3):
                    mx.add("drums", t0 + q * beat, clap(mx.rng), 0.22)
    g = duck(mx.n, kicks, 0.7, 0.28)
    out = reverb(mx.bus["pad"] * g, 2.2, 0.35) + reverb(mx.bus["keys"] * g, 1.4, 0.25) + mx.bus["bass"] * g + mx.bus.get("drums", 0)
    return out, "Deep-house glow"


def style_elec_synthwave(S):
    """Synthwave dusk: 16th saw-bass arpeggio, lush pad, big gated-reverb snare, slower and nostalgic."""
    mx = Mix(S, 71)
    beat = 60 / 100
    bar = 4 * beat
    prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    for b in range(int(S / bar) + 1):
        ch, t0 = prog[b % 4], b * bar
        mx.add("pad", t0, pad([m + 12 for m in ch] + [ch[0] + 24], bar, voices=7, detune=0.3, cutoff=2200, attack=0.5), 0.32)
        for s16 in range(16):
            m = ch[0] - 12 + (12 if s16 % 4 == 2 else 0)
            mx.add("bass", t0 + s16 * beat / 4, saw_note(m, beat / 4 * 0.9, cutoff=500, env_amt=1800, decay=18, seed=s16), 0.32)
        if b % 2 == 1:
            for k, m in enumerate([ch[2] + 24, ch[1] + 24, ch[0] + 24]):
                mx.add("lead", t0 + (2 + k * 0.5) * beat, saw_note(m, beat * 0.8, cutoff=1400, env_amt=2600, decay=5, voices=2), 0.16)
        if b >= 1:
            for q in range(4):
                if q in (0, 2):
                    mx.add("drums", t0 + q * beat, kick(1.0), 0.55)
                if q in (1, 3):
                    mx.add("snare", t0 + q * beat, snare(mx.rng, 170), 0.5)
                for e in range(2):
                    mx.add("drums", t0 + q * beat + e * beat / 2, hat(mx.rng), 0.07)
    sn = reverb(mx.bus.get("snare", np.zeros(mx.n)), 1.2, 0.6)
    out = reverb(mx.bus["pad"], 2.6, 0.4) + mx.bus["bass"] + reverb(mx.bus.get("lead", np.zeros(mx.n)), 2.0, 0.4) + sn * 0.6 + mx.bus.get("drums", 0)
    return out, "Synthwave dusk"


def style_elec_garage(S):
    """Future garage: shuffled 2-step drums, airy chopped pad, deep sub, minor and atmospheric."""
    mx = Mix(S, 81)
    beat = 60 / 132
    bar = 4 * beat
    prog = [[54, 57, 61, 64], [50, 54, 57, 61], [52, 56, 59, 64], [49, 52, 56, 59]]  # F#m7 Dmaj7 E C#m
    kicks = []
    for b in range(int(S / bar) + 1):
        ch, t0 = prog[b % 4], b * bar
        for chop in (0, 0.75, 1.5, 2.5, 3.25):  # rhythmic pad chops
            mx.add("pad", t0 + chop * beat, pad([m + 12 for m in ch], beat * 0.6, voices=6, detune=0.25, cutoff=3000, attack=0.01), 0.24)
        mx.add("bass", t0, sub(ch[0] - 12, bar * 0.9), 0.20)
        if b >= 1:
            for k_at in (0, 2.75):  # 2-step kick
                mx.add("drums", t0 + k_at * beat, kick(0.8), 0.55)
                kicks.append(t0 + k_at * beat)
            for sn_at in (1, 3):
                mx.add("drums", t0 + sn_at * beat, snare(mx.rng, 230), 0.25)
            for s16 in range(16):
                sw = 0.06 * beat if s16 % 2 else 0
                mx.add("drums", t0 + s16 * beat / 4 + sw, hat(mx.rng), 0.05 + 0.05 * (s16 % 4 == 2))
            mx.add("drums", t0 + 1.5 * beat, rim(mx.rng), 0.15)
    g = duck(mx.n, kicks, 0.6, 0.35)
    out = reverb(mx.bus["pad"] * g, 3.0, 0.45, tone=7000) + mx.bus["bass"] * g + mx.bus.get("drums", 0)
    return out, "Future garage"


def style_elec_downtempo(S):
    """Downtempo tech: half-time beat, filtered saw-pluck arpeggio, warm pad; relaxed but modern."""
    mx = Mix(S, 91)
    beat = 60 / 92
    bar = 4 * beat
    prog = [[57, 60, 64, 67], [53, 57, 60, 64], [50, 53, 57, 60], [55, 59, 62, 65]]  # Am7 Fmaj7 Dm7 G7
    arp = [0, 2, 1, 3, 2, 1, 3, 2]
    for b in range(int(S / bar) + 1):
        ch, t0 = prog[b % 4], b * bar
        mx.add("pad", t0, sine_pad([m + 12 for m in ch], bar + 0.6, attack=0.8), 0.16)
        for e in range(8):
            mx.add("arp", t0 + e * beat / 2, saw_note(ch[arp[e]] + 12, beat * 0.45, cutoff=700, env_amt=2200 + 400 * (b % 4), decay=10, seed=e), 0.22)
        mx.add("bass", t0, sub(ch[0] - 12, beat * 1.8), 0.26)
        mx.add("bass", t0 + 2.5 * beat, sub(ch[0] - 12, beat * 1.2), 0.20)
        if b >= 1:
            mx.add("drums", t0, kick(1.1), 0.6)
            mx.add("drums", t0 + 1.5 * beat, kick(1.1), 0.35)
            mx.add("drums", t0 + 2 * beat, snare(mx.rng, 190), 0.32)
            for s16 in range(16):
                mx.add("drums", t0 + s16 * beat / 4, hat(mx.rng), 0.04 + 0.05 * (s16 % 2 == 0))
            mx.add("drums", t0 + 3.5 * beat, rim(mx.rng), 0.12)
    out = reverb(mx.bus["pad"], 2.5, 0.4) + reverb(mx.bus["arp"], 1.6, 0.3) + mx.bus["bass"] + mx.bus.get("drums", 0)
    return out, "Downtempo tech"


def style_elec_minimal(S):
    """Minimal pulse: tight kick, clicky hats, slowly opening pad and FM bell motif; clean, data-like."""
    mx = Mix(S, 101)
    beat = 60 / 122
    bar = 4 * beat
    prog = [[57, 64, 67, 72], [53, 60, 64, 69], [55, 62, 67, 71], [52, 59, 64, 67]]
    kicks = []
    nb = int(S / bar) + 1
    for b in range(nb):
        ch, t0 = prog[b % 4], b * bar
        mx.add("pad", t0, pad(ch, bar, voices=5, detune=0.2, cutoff=900 + 2600 * b / max(nb - 1, 1), attack=0.05), 0.25)
        for k, at in enumerate((0, 0.75, 1.5, 2.5, 3.0)):
            mx.add("bell", t0 + at * beat, bell(ch[k % 4] + 12, 1.0, 0.16 if k else 0.22))
        mx.add("bass", t0, sub(ch[0] - 24, beat * 0.4), 0.45)
        mx.add("bass", t0 + 2 * beat, sub(ch[0] - 24, beat * 0.4), 0.4)
        if b >= 1:
            for q in range(4):
                mx.add("drums", t0 + q * beat, kick(0.75), 0.55)
                kicks.append(t0 + q * beat)
                mx.add("drums", t0 + q * beat + beat / 2, hat(mx.rng), 0.10)
                mx.add("drums", t0 + q * beat + 3 * beat / 4, rim(mx.rng), 0.05 if q % 2 else 0.0)
    g = duck(mx.n, kicks, 0.65, 0.25)
    out = reverb(mx.bus["pad"] * g, 2.0, 0.3) + reverb(mx.bus["bell"], 2.2, 0.35) + mx.bus["bass"] * g + mx.bus.get("drums", 0)
    return out, "Minimal pulse"


def style_video(S):
    """Final video track: E2 (synthwave) rhythm + E3 (future garage) harmony, arranged to the video scenes.

    100 BPM, bar = 2.4 s. Sections (bars): intro 0-4, build 4-8, main 8-15, breakdown 15-22, main 22-27, outro 27-.
    """
    mx = Mix(S, 111)
    beat = 60 / 100
    bar = 4 * beat
    prog = [[54, 57, 61, 64], [50, 54, 57, 61], [52, 56, 59, 64], [49, 52, 56, 59]]  # F#m7 Dmaj7 E C#m (E3 harmony)
    melody = [(0, 73), (0.75, 76), (1.5, 73), (2.5, 71), (3.25, 69)]  # airy counter-line, every other bar in the mains
    nb = int(np.ceil(S / bar))

    def section(b):
        if b < 4: return "intro"
        if b < 8: return "build"
        if b < 15: return "main"
        if b < 22: return "break"
        if b < 27: return "main"
        return "outro"

    for b in range(nb):
        ch, t0, sec = prog[b % 4], b * bar, section(b)
        # E3 melodics: rhythmic airy pad chops (always), sustained pad bed under intro/break/outro
        chop_gain = {"intro": 0.16, "build": 0.2, "main": 0.22, "break": 0.2, "outro": 0.18}[sec]
        for chop in (0, 0.75, 1.5, 2.5, 3.25):
            mx.add("chops", t0 + chop * beat, pad([m + 12 for m in ch], beat * 0.6, voices=6, detune=0.25, cutoff=3000, attack=0.01), chop_gain)
        if sec in ("intro", "break", "outro"):
            mx.add("bed", t0, sine_pad([m + 12 for m in ch], bar + 1.0, attack=1.0), 0.14)
        # E2 rhythm: 16th saw-bass arpeggio, opening filter through intro/build
        if sec != "outro" or b == 27:
            arp_cut = {"intro": 250 + 60 * b, "build": 450 + 90 * (b - 4)}.get(sec, 600 if sec == "main" else 380)
            arp_g = {"intro": 0.16 if b >= 2 else 0.0, "build": 0.26, "main": 0.32, "break": 0.22, "outro": 0.18}[sec]
            for s16 in range(16):
                m = ch[0] - 12 + (12 if s16 % 4 == 2 else 0)
                if arp_g:
                    mx.add("arp", t0 + s16 * beat / 4, saw_note(m, beat / 4 * 0.9, cutoff=arp_cut, env_amt=1800, decay=18, seed=s16), arp_g)
        mx.add("sub", t0, sub(ch[0] - 12, bar * 0.95), 0.16 if sec != "outro" else 0.12)
        # counter-melody in the mains (bell-like, airy)
        if sec == "main" and b % 2 == 1:
            for at, m in melody:
                mx.add("lead", t0 + at * beat, bell(m, 1.1, 0.14))
        # drums: E2 pattern (kick 1&3, gated snare 2&4, 8th hats)
        if sec in ("main",) or (sec == "build" and b >= 6):
            for q in range(4):
                if q in (0, 2):
                    mx.add("drums", t0 + q * beat, kick(1.0), 0.55)
                if q in (1, 3) and (sec == "main" or b == 7):
                    mx.add("snare", t0 + q * beat, snare(mx.rng, 170), 0.5)
        if sec in ("build", "main", "break"):
            for e in range(8):
                vel = 0.07 if sec != "break" else 0.05
                mx.add("hats", t0 + e * beat / 2, hat(mx.rng), vel * (1.3 if e % 2 else 1.0))
    # final ringing chord
    last = (nb - 2) * bar
    mx.add("bed", last, sine_pad([m + 12 for m in prog[0]], 4.0, attack=0.6), 0.18)
    sn = reverb(mx.bus.get("snare", np.zeros(mx.n)), 1.2, 0.6)
    out = (reverb(mx.bus["chops"], 3.0, 0.45, tone=7000) + reverb(mx.bus["bed"], 3.5, 0.45) + mx.bus["arp"] + mx.bus["sub"]
           + reverb(mx.bus.get("lead", np.zeros(mx.n)), 2.4, 0.4) + sn * 0.6 + mx.bus.get("drums", 0) + mx.bus.get("hats", 0))
    return out, "Video track (E2 rhythm x E3 harmony)"


STYLES = {"lofi": style_lofi, "launch": style_launch, "ambient": style_ambient, "acoustic": style_acoustic,
          "electronic": style_electronic, "elec_deep": style_elec_deep, "elec_synthwave": style_elec_synthwave,
          "elec_garage": style_elec_garage, "video": style_video, "elec_downtempo": style_elec_downtempo, "elec_minimal": style_elec_minimal}


def master(x, seconds, fade_in=1.0, fade_out=3.0, target_rms_db=-19.0):
    x = fft_filter(x, lo=35)
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    x = x * (10 ** (target_rms_db / 20) / rms)
    x = np.tanh(x * 1.2) / 1.2  # gentle soft clip for peaks
    n = len(x)
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    x[:fi] *= np.linspace(0, 1, fi)
    x[-fo:] *= np.linspace(1, 0, fo) ** 1.5
    # wide-ish stereo from a short Haas offset on the reverb-ish top end
    side = fft_filter(x, lo=1500)
    d = int(0.011 * SR)
    left = x + 0.15 * np.concatenate([np.zeros(d), side])[:n]
    right = x - 0.15 * np.concatenate([np.zeros(d), side])[:n]
    st = np.stack([left, right], 1)
    return st / max(1.0, np.max(np.abs(st)) / 0.89)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", choices=list(STYLES), required=True)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sig, name = STYLES[a.style](a.seconds)
    st = master(sig[: int(a.seconds * SR)], a.seconds)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())
    print(f"{a.style}: {name} -> {a.out}")


if __name__ == "__main__":
    main()
