"""Procesador DSP para dar sonido autentico de radio de Formula 1 TV + Beep FIA + Ambiente de Muro."""
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

    mask = np.ones_like(freqs)
    low_w = 120.0
    high_w = 450.0
    mask *= np.clip((freqs - (low_hz - low_w)) / low_w, 0.0, 1.0) ** 2
    mask *= np.clip(((high_hz + high_w) - freqs) / high_w, 0.0, 1.0) ** 2

    # Realce de presencia tipico de microfono de muro de boxes (1.1 - 2.6 kHz)
    presence = 1.0 + 0.58 * np.exp(-0.5 * ((freqs - 1850.0) / 550.0) ** 2)
    spec *= mask * presence
    return np.fft.irfft(spec, n=n).astype(np.float32)


def _synth_chirp_open(sr: int, intensity: float = 0.85) -> np.ndarray:
    """Doble pitido oficial de apertura de Team Radio estilo F1 TV Broadcast."""
    rng = np.random.default_rng(42)
    click = rng.normal(0, 0.09, int(sr * 0.016)).astype(np.float32)

    # Tono 1 (1980 Hz + armonico 3960 Hz)
    t1 = np.linspace(0, 0.048, int(sr * 0.048), endpoint=False, dtype=np.float32)
    env1 = np.hanning(len(t1)) * np.exp(-t1 * 12.0)
    tone1 = (np.sin(2 * np.pi * 1980.0 * t1) + 0.25 * np.sin(2 * np.pi * 3960.0 * t1)) * env1

    gap = np.zeros(int(sr * 0.016), dtype=np.float32)

    # Tono 2 caracteristico F1 TV (2520 Hz + quinta inferior 1680 Hz con ligero decay)
    t2 = np.linspace(0, 0.078, int(sr * 0.078), endpoint=False, dtype=np.float32)
    env2 = np.hanning(len(t2)) * np.exp(-t2 * 9.5)
    tone2 = (
        0.85 * np.sin(2 * np.pi * 2520.0 * t2)
        + 0.35 * np.sin(2 * np.pi * 1680.0 * t2)
    ) * env2

    pad = np.zeros(int(sr * 0.018), dtype=np.float32)
    chirp = np.concatenate([click, tone1 * 0.26, gap, tone2 * 0.30, pad])
    return (chirp * (0.45 + 0.55 * intensity)).astype(np.float32)


def _synth_squelch_close(sr: int, intensity: float = 0.85) -> np.ndarray:
    """Cola de squelch + clic final y pitido grave de cierre al soltar el PTT."""
    rng = np.random.default_rng()
    dur = int(sr * 0.090)
    noise = rng.normal(0, 0.15, dur).astype(np.float32)
    noise = _bandpass_fft(noise, sr, 500.0, 2900.0)
    env = np.linspace(1.0, 0.04, dur, dtype=np.float32)
    t_end = np.linspace(0, 0.040, int(sr * 0.040), endpoint=False, dtype=np.float32)
    beep_end = (
        0.7 * np.sin(2 * np.pi * 1440.0 * t_end)
        + 0.3 * np.sin(2 * np.pi * 960.0 * t_end)
    ) * np.hanning(len(t_end)) * 0.16
    pad = np.zeros(int(sr * 0.022), dtype=np.float32)
    tail = np.concatenate([pad, beep_end, noise * env])
    return (tail * (0.45 + 0.55 * intensity)).astype(np.float32)


def _synth_pitwall_ambience(n_samples: int, sr: int, intensity: float) -> np.ndarray:
    """Genera un sutil ambiente de muro de boxes / garaje F1 detras de la voz del ingeniero."""
    if n_samples <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    rng = np.random.default_rng()
    # Murmullo de aire / ventiladores de servidores del muro + zumbido lejano de pista
    room_noise = rng.normal(0, 1.0, n_samples).astype(np.float32)
    room_noise = _bandpass_fft(room_noise, sr, 380.0, 1600.0)
    rn_peak = float(np.max(np.abs(room_noise))) or 1.0
    room_noise = room_noise / rn_peak
    # Armónico muy sutil de motor en la recta principal a lo lejos
    distant_v6 = (
        0.5 * np.sin(2 * np.pi * (410.0 + 18.0 * np.sin(2 * np.pi * 0.6 * t)) * t)
        + 0.3 * np.sin(2 * np.pi * (820.0 + 36.0 * np.sin(2 * np.pi * 0.6 * t)) * t)
    ).astype(np.float32)
    amb = (0.75 * room_noise + 0.25 * distant_v6) * (0.022 * intensity)
    return amb.astype(np.float32)


def apply_f1_radio_effect(samples: np.ndarray, sr: int, intensity: float = 0.85,
                          volume: float = 1.0) -> np.ndarray:
    """Aplica el efecto de radio de Formula 1 TV + ambiente de muro a una senal mono float32."""
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

    # 3. Ruido de portadora de radio + ambiente de muro de boxes modulado por la voz
    rng = np.random.default_rng()
    hiss = rng.normal(0, 1.0, len(saturated)).astype(np.float32)
    hiss = _bandpass_fft(hiss, sr, 450.0, 3000.0)
    hiss_peak = float(np.max(np.abs(hiss))) or 1.0
    hiss = hiss / hiss_peak
    voice_env = np.minimum(1.0, np.abs(saturated) * 3.0 + 0.35)
    pit_amb = _synth_pitwall_ambience(len(saturated), sr, intensity)
    mixed = (
        saturated * (1.0 - 0.12 * intensity)
        + hiss * (0.042 * intensity) * voice_env
        + pit_amb
    )

    # 4. Segundo paso banda ligero para limpiar armonicos de la distorsion
    mixed = _bandpass_fft(mixed, sr, low_hz=340.0, high_hz=3300.0)
    m_peak = float(np.max(np.abs(mixed))) or 1.0
    mixed = mixed / m_peak * 0.82

    # 5. Mezcla dry/wet segun intensidad y anadir chirp F1 TV inicial + squelch final
    voice_out = intensity * mixed + (1.0 - intensity) * (samples / (float(np.max(np.abs(samples))) or 1.0) * 0.8)
    full = np.concatenate([
        _synth_chirp_open(sr, intensity),
        voice_out.astype(np.float32),
        _synth_squelch_close(sr, intensity),
    ])
    return np.clip(full * float(volume), -0.98, 0.98)


def play_ack_beep(intensity: float = 0.85, volume: float = 1.0) -> None:
    """Reproduce el doble pitido corto oficial F1 TV cuando se abre el microfono de radio."""
    sr = 24000
    beep = _synth_chirp_open(sr, intensity) * float(volume)
    try:
        sd.play(beep, samplerate=sr, blocking=False)
    except Exception:
        pass
