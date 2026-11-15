"""Procesador DSP para dar sonido autentico de radio de Formula 1."""
from __future__ import annotations

import numpy as np
import sounddevice as sd


def _bandpass_fft(samples: np.ndarray, sr: int, low_hz: float = 340.0, high_hz: float = 3300.0) -> np.ndarray:
    """Filtro paso banda suave en frecuencia + realce de medios (1.2 - 2.5 kHz)."""
    n = len(samples)
    if n == 0:
        return samples
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spec = np.fft.rfft(samples)

    # Mascara paso banda con transicion suave
    mask = np.ones_like(freqs)
    low_w = 120.0
    high_w = 450.0
    mask *= np.clip((freqs - (low_hz - low_w)) / low_w, 0.0, 1.0) ** 2
    mask *= np.clip(((high_hz + high_w) - freqs) / high_w, 0.0, 1.0) ** 2

    # Realce de presencia tipico de microfono de muro de boxes (1.1 - 2.6 kHz)
    presence = 1.0 + 0.55 * np.exp(-0.5 * ((freqs - 1850.0) / 550.0) ** 2)
    spec *= mask * presence
    return np.fft.irfft(spec, n=n).astype(np.float32)


def _synth_chirp_open(sr: int, intensity: float = 0.85) -> np.ndarray:
    """Doble tono corto estilo apertura de radio F1 FIA."""
    t1 = np.linspace(0, 0.042, int(sr * 0.042), endpoint=False, dtype=np.float32)
    t2 = np.linspace(0, 0.058, int(sr * 0.058), endpoint=False, dtype=np.float32)
    gap = np.zeros(int(sr * 0.012), dtype=np.float32)
    tone1 = np.sin(2 * np.pi * 1950.0 * t1) * np.hanning(len(t1))
    tone2 = np.sin(2 * np.pi * 2480.0 * t2) * np.hanning(len(t2))
    rng = np.random.default_rng(42)
    click = rng.normal(0, 0.08, int(sr * 0.018)).astype(np.float32)
    chirp = np.concatenate([click, tone1 * 0.22, gap, tone2 * 0.26, gap])
    return (chirp * (0.4 + 0.6 * intensity)).astype(np.float32)


def _synth_squelch_close(sr: int, intensity: float = 0.85) -> np.ndarray:
    """Cola de squelch + clic final al soltar el boton de radio."""
    rng = np.random.default_rng()
    dur = int(sr * 0.085)
    noise = rng.normal(0, 0.14, dur).astype(np.float32)
    noise = _bandpass_fft(noise, sr, 500.0, 2900.0)
    env = np.linspace(1.0, 0.05, dur, dtype=np.float32)
    t_end = np.linspace(0, 0.035, int(sr * 0.035), endpoint=False, dtype=np.float32)
    beep_end = np.sin(2 * np.pi * 1420.0 * t_end) * np.hanning(len(t_end)) * 0.15
    pad = np.zeros(int(sr * 0.025), dtype=np.float32)
    tail = np.concatenate([pad, beep_end, noise * env])
    return (tail * (0.4 + 0.6 * intensity)).astype(np.float32)


def apply_f1_radio_effect(samples: np.ndarray, sr: int, intensity: float = 0.85,
                          volume: float = 1.0) -> np.ndarray:
    """Aplica el efecto de radio de Formula 1 a una senal mono float32."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = samples.astype(np.float32)
    intensity = float(np.clip(intensity, 0.0, 1.0))

    if intensity <= 0.02:
        peak = float(np.max(np.abs(samples))) or 1.0
        return np.clip(samples / peak * 0.85 * volume, -1.0, 1.0)

    # 1. Paso banda telefonico/radio + realce de medios
    filtered = _bandpass_fft(samples, sr, low_hz=350.0, high_hz=3200.0)

    # 2. Normalizacion previa y compresion / saturacion suave (walkie overdrive)
    peak = float(np.max(np.abs(filtered))) or 1.0
    normed = filtered / peak
    drive = 1.6 + 2.4 * intensity
    saturated = np.tanh(normed * drive) / np.tanh(drive)

    # 3. Ruido de portadora de radio modulado por la envolvente de voz
    rng = np.random.default_rng()
    hiss = rng.normal(0, 1.0, len(saturated)).astype(np.float32)
    hiss = _bandpass_fft(hiss, sr, 450.0, 3000.0)
    hiss_peak = float(np.max(np.abs(hiss))) or 1.0
    hiss = hiss / hiss_peak
    voice_env = np.minimum(1.0, np.abs(saturated) * 3.0 + 0.35)
    mixed = saturated * (1.0 - 0.12 * intensity) + hiss * (0.045 * intensity) * voice_env

    # 4. Segundo paso banda ligero para limpiar armonicos de la distorsion
    mixed = _bandpass_fft(mixed, sr, low_hz=340.0, high_hz=3300.0)
    m_peak = float(np.max(np.abs(mixed))) or 1.0
    mixed = mixed / m_peak * 0.82

    # 5. Mezcla dry/wet segun intensidad y anadir chirp inicial + squelch final
    voice_out = intensity * mixed + (1.0 - intensity) * (samples / (float(np.max(np.abs(samples))) or 1.0) * 0.8)
    full = np.concatenate([
        _synth_chirp_open(sr, intensity),
        voice_out.astype(np.float32),
        _synth_squelch_close(sr, intensity),
    ])
    return np.clip(full * float(volume), -0.98, 0.98)


def play_ack_beep(intensity: float = 0.85, volume: float = 1.0) -> None:
    """Reproduce el pitido corto cuando el piloto activa la palabra clave ('Radio')."""
    sr = 24000
    beep = _synth_chirp_open(sr, intensity) * float(volume)
    try:
        sd.play(beep, samplerate=sr, blocking=False)
    except Exception:
        pass
