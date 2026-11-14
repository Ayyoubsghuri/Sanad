"""Original soundtrack for the Sanad promo: airy build-up with whooshes for 8.6 s, an impact, then a half-time beat (86 BPM) to the end."""
import numpy as np, wave
SR = 44100; DUR = 16.0; N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)
L = np.zeros(N); R = np.zeros(N)

def lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)):
        s = (1 - a) * x[i] + a * s; y[i] = s
    return y
def lp_fast(x, fc):  # vectorised one-pole via lfilter-like cumulative trick (chunked)
    from scipy.signal import lfilter
    a = np.exp(-2 * np.pi * fc / SR); return lfilter([1 - a], [1, -a], x)
def hp(x, fc):
    return x - lp_fast(x, fc)
def env(n, a, d):
    e = np.ones(n); ai = int(a * SR); e[:ai] = np.linspace(0, 1, ai) if ai else 1
    e[ai:] = np.exp(-np.arange(n - ai) / (d * SR)); return e
def add(sig, start, gl=1.0, gr=1.0):
    i = int(start * SR); j = min(N, i + len(sig)); L[i:j] += sig[:j - i] * gl; R[i:j] += sig[:j - i] * gr
def saw(f, tt): return 2 * ((tt * f) % 1) - 1

# chords (A minor feel): Am - F - C - G, 2.79 s each (4 beats at 86 BPM)
B = 60 / 86
chords = [[220, 261.63, 329.63], [174.61, 220, 261.63], [196, 261.63, 329.63], [196, 246.94, 293.66]]
# pad over the whole piece, swelling up to the drop
pad = np.zeros(N)
for k in range(6):
    s0 = k * 4 * B * 0.75 if False else k * 2.79
    for f in chords[k % 4]:
        for det in (-0.12, 0.12):
            seg = slice(int(s0 * SR), min(N, int((s0 + 2.95) * SR)))
            tt = t[seg] - s0
            pad[seg] += saw(f * (1 + det / 100), tt) * np.minimum(1, tt / 0.6) * np.minimum(1, (2.95 - tt) / 0.4)
pad = lp_fast(pad, 1400) * 0.035
swell = np.clip(t / 8.6, 0, 1) ** 1.5 * 0.8 + 0.3
pad *= np.where(t < 8.6, swell, 1.0) * np.where(t > 15.0, np.clip((16 - t) / 1.0, 0, 1), 1)
L += pad * 0.95; R += pad * 1.05

# whooshes on the scene changes (band-passed noise sweeping up)
def whoosh(length, f0, f1, gain):
    n = int(length * SR); x = rng.standard_normal(n)
    fc = np.linspace(f0, f1, n); y = np.zeros(n); s1 = s2 = 0.0
    out = hp(lp_fast(x, f1), f0)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    return out * e * gain
for at in (0.05, 2.3, 4.1, 6.0, 7.4):
    w = whoosh(0.7, 400, 6000, 0.18); add(w, at, 0.8, 1.0)
# soft UI ticks
def tick(f=2400, g=0.12):
    n = int(0.06 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.012) * g
for at in (2.55, 4.3, 4.9, 5.5, 4.55, 4.67, 4.79, 6.4, 6.55, 6.69, 7.6):
    add(tick(), at, 1.0, 0.8)
# riser into the drop
n = int(1.2 * SR); tt = np.arange(n) / SR
riser = (rng.standard_normal(n) * 0.5 + saw(200 * 2 ** (tt * 2.2), tt) * 0.4)
riser = hp(riser, 600) * (tt / 1.2) ** 2 * 0.22
add(riser, 7.4)
# impact at the drop
def kick(g=0.9, f0=120, f1=42, d=0.32):
    n = int(0.5 * SR); tt = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-tt / 0.045)) / SR
    return np.sin(ph) * np.exp(-tt / d) * g
boom = kick(1.0, 90, 34, 0.9)
noise = hp(rng.standard_normal(int(0.8 * SR)), 300) * env(int(0.8 * SR), 0.002, 0.18) * 0.35
add(boom, 8.6); add(noise, 8.6)
# beat from the drop: kick on 1 and 3, clap on 2 and 4, hats on eighths (172 feel), sub bass on the chord roots
def clap():
    n = int(0.25 * SR); x = hp(lp_fast(rng.standard_normal(n), 5000), 900)
    e = np.zeros(n)
    for o in (0, 0.01, 0.02):
        i = int(o * SR); e[i:] += np.exp(-np.arange(n - i) / (0.06 * SR))
    return x * e * 0.22
def hat(open_=False):
    n = int((0.12 if open_ else 0.04) * SR); x = hp(rng.standard_normal(n), 7000)
    return x * np.exp(-np.arange(n) / ((0.05 if open_ else 0.012) * SR)) * 0.10
start = 8.6; beat = 0
while start + beat * B < 15.1:
    at = start + beat * B
    if beat % 2 == 0: add(kick(), at)
    else: add(clap(), at, 0.9, 1.0)
    add(hat(), at + B / 2, 0.7, 1.0); add(hat(beat % 4 == 3), at + B / 4 * 3, 1.0, 0.7)
    beat += 1
roots = [55, 43.65, 49, 49]
for k in range(3):
    s0 = 8.6 + k * 4 * B; root = roots[k % 4]
    n = int(4 * B * SR); tt = np.arange(n) / SR
    sub = np.sin(2 * np.pi * root * tt) * 0.28 * np.minimum(1, tt / 0.02) * np.minimum(1, (4 * B - tt) / 0.05)
    add(sub, s0)
# logo shimmer at the end (bell)
for f, g in ((880, .1), (1318.5, .07), (1760, .05)):
    n = int(2.4 * SR); tt = np.arange(n) / SR
    add(np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.7) * g, 13.05, 0.9, 1.0)
add(kick(0.7, 80, 34, 0.6), 13.05)
# simple reverb: convolve with a decaying noise tail
from scipy.signal import fftconvolve
ir = rng.standard_normal(int(1.6 * SR)) * np.exp(-np.arange(int(1.6 * SR)) / (0.35 * SR)); ir /= np.abs(ir).sum() / 6
L = L + fftconvolve(L, ir)[:N] * 0.18; R = R + fftconvolve(R, ir[::-1].copy())[:N] * 0.18
mix = np.stack([L, R], 1)
mix *= np.clip((16 - t) / 0.5, 0, 1)[:, None]
mix = np.tanh(mix * 1.4) / np.tanh(1.4)
mix /= max(1e-9, np.abs(mix).max()) / 0.89
with wave.open('music.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype('<i2').tobytes())
print('ok')
