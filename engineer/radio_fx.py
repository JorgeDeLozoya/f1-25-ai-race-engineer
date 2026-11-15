"""Procesador DSP para dar sonido autentico de radio de Formula 1 TV + Beep FIA + Ambiente de Muro y F1 pasando."""
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


def _synth_chirp_open(sr: int, intensity: float = 0.85, style: str = "f1_tv") -> np.ndarray:
    """Sintetiza el pitido de apertura de radio segun el estilo elegido (F1 TV, FIA Pit Wall, Walkie Clasico)."""
    style = (style or "f1_tv").lower()
    if style == "off":
        return np.zeros(int(sr * 0.01), dtype=np.float32)

    rng = np.random.default_rng(42)
    click = rng.normal(0, 0.09, int(sr * 0.015)).astype(np.float32)

    if style == "fia_pitwall":
        # Chirp digital corto de intercomunicador de muro FIA (2350 Hz -> 2750 Hz)
        t1 = np.linspace(0, 0.038, int(sr * 0.038), endpoint=False, dtype=np.float32)
        tone1 = np.sin(2 * np.pi * 2350.0 * t1) * np.hanning(len(t1))
        gap = np.zeros(int(sr * 0.010), dtype=np.float32)
        t2 = np.linspace(0, 0.045, int(sr * 0.045), endpoint=False, dtype=np.float32)
        tone2 = np.sin(2 * np.pi * 2750.0 * t2) * np.hanning(len(t2))
        pad = np.zeros(int(sr * 0.015), dtype=np.float32)
        chirp = np.concatenate([click, tone1 * 0.24, gap, tone2 * 0.28, pad])
        return (chirp * (0.45 + 0.55 * intensity)).astype(np.float32)

    if style == "classic_v10":
        # Walkie analogico clasico anos 2000 (clic de rele fuerte + pitido 1560 Hz)
        relay = rng.normal(0, 0.16, int(sr * 0.022)).astype(np.float32)
        t = np.linspace(0, 0.065, int(sr * 0.065), endpoint=False, dtype=np.float32)
        tone = (0.8 * np.sin(2 * np.pi * 1560.0 * t) + 0.2 * np.sin(2 * np.pi * 3120.0 * t)) * np.hanning(len(t))
        pad = np.zeros(int(sr * 0.018), dtype=np.float32)
        chirp = np.concatenate([relay, tone * 0.28, pad])
        return (chirp * (0.45 + 0.55 * intensity)).astype(np.float32)

    # Por defecto: "f1_tv" -> Doble pitido oficial de apertura de Team Radio estilo F1 TV Broadcast
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


def _synth_squelch_close(sr: int, intensity: float = 0.85, style: str = "f1_tv") -> np.ndarray:
    """Cola de squelch + clic final y pitido grave de cierre al terminar la radio."""
    style = (style or "f1_tv").lower()
    if style == "off":
        return np.zeros(int(sr * 0.01), dtype=np.float32)

    rng = np.random.default_rng()
    dur = int(sr * 0.090)
    noise = rng.normal(0, 0.15, dur).astype(np.float32)
    noise = _bandpass_fft(noise, sr, 500.0, 2900.0)
    env = np.linspace(1.0, 0.04, dur, dtype=np.float32)

    t_end = np.linspace(0, 0.045, int(sr * 0.045), endpoint=False, dtype=np.float32)
    f_low = 1440.0 if style == "f1_tv" else (1850.0 if style == "fia_pitwall" else 1180.0)
    beep_end = (
        0.7 * np.sin(2 * np.pi * f_low * t_end)
        + 0.3 * np.sin(2 * np.pi * (f_low * 0.66) * t_end)
    ) * np.hanning(len(t_end)) * 0.18
    pad = np.zeros(int(sr * 0.022), dtype=np.float32)
    tail = np.concatenate([pad, beep_end, noise * env])
    return (tail * (0.45 + 0.55 * intensity)).astype(np.float32)


def _synth_single_f1_flyby(n_samples: int, sr: int, center_sec: float, base_hz: float = 590.0) -> np.ndarray:
    """Sintetiza un monoplaza F1 pasando a 315 km/h frente al muro de boxes con efecto Doppler real."""
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    dt = t - center_sec

    # Geometria fisica: coche a v=88 m/s (316 km/h) pasando a d=13 m del microfono del muro de boxes
    v_car = 88.0
    c_sound = 343.0
    d_min = 13.0
    dist = np.sqrt((v_car * dt) ** 2 + d_min ** 2)
    radial_vel = (v_car ** 2 * dt) / dist  # negativo al acercarse, positivo al alejarse
    doppler = 1.0 / (1.0 + radial_vel / c_sound)

    # Fase integrada de la frecuencia instantanea con ligero cambio de marcha antes del pico
    inst_freq = base_hz * doppler
    phase = 2.0 * np.pi * np.cumsum(inst_freq) / float(sr)

    # Armonicos del motor V6 Turbo Hibrido F1 a 11.800 RPM + silbido del turbo
    engine = (
        0.48 * np.sin(phase)
        + 0.65 * np.sin(2.0 * phase + 0.3)
        + 0.35 * np.sin(3.0 * phase + 0.7)
        + 0.18 * np.sin(4.0 * phase)
        + 0.10 * np.sin(6.5 * phase)
    ).astype(np.float32)

    # Soplido aerodinamico del aleron y fondo plano al pasar junto al muro
    rng = np.random.default_rng(int(abs(center_sec * 1000)) + 7)
    whoosh = rng.normal(0, 1.0, n_samples).astype(np.float32)
    whoosh = _bandpass_fft(whoosh, sr, 420.0, 2400.0)
    w_peak = float(np.max(np.abs(whoosh))) or 1.0
    whoosh = whoosh / w_peak

    # Envolvente de amplitud por ley de distancia inversa suavizada
    amp_env = (d_min / dist) ** 1.35
    flyby = (0.72 * engine + 0.28 * whoosh) * amp_env
    peak = float(np.max(np.abs(flyby))) or 1.0
    return (flyby / peak).astype(np.float32)


def _synth_wheel_gun_burst(n_samples: int, sr: int, start_sec: float) -> np.ndarray:
    """Sintetiza el sonido de una pistola neumatica (wheel gun) cambiando una rueda en el pit lane."""
    out = np.zeros(n_samples, dtype=np.float32)
    # Dos rafagas cortas tipicas de tuerca F1 (zzt - zzt!)
    for offset, dur_s, freq in ((0.0, 0.18, 1280.0), (0.25, 0.22, 1420.0)):
        idx0 = int((start_sec + offset) * sr)
        length = int(dur_s * sr)
        if idx0 < 0 or idx0 + length >= n_samples or length <= 10:
            continue
        t = np.linspace(0, dur_s, length, endpoint=False, dtype=np.float32)
        # Vibracion de impacto + silbido de aire comprimido
        hammer = np.sin(2 * np.pi * 55.0 * t) > 0.0
        whine = (
            0.65 * np.sin(2 * np.pi * freq * t)
            + 0.35 * np.sin(2 * np.pi * (freq * 1.95) * t)
        ) * (0.45 + 0.55 * hammer)
        env = np.hanning(length)
        out[idx0:idx0 + length] += (whine * env).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak).astype(np.float32)


def _synth_pitwall_ambience(
    n_samples: int,
    sr: int,
    bg_level: float = 0.65,
    bg_style: str = "pitwall_f1_flyby",
) -> np.ndarray:
    """Genera el sonido ambiente de fondo del muro de boxes (con F1 pasando, pistolas de box o telemetria)."""
    bg_style = (bg_style or "pitwall_f1_flyby").lower()
    if n_samples <= 0 or bg_level <= 0.01 or bg_style == "off":
        return np.zeros(max(0, n_samples), dtype=np.float32)

    dur_s = n_samples / float(sr)
    rng = np.random.default_rng()

    # 1. Base comun: murmullo de servidores y aire del muro de boxes
    room_noise = rng.normal(0, 1.0, n_samples).astype(np.float32)
    room_noise = _bandpass_fft(room_noise, sr, 380.0, 1650.0)
    rn_peak = float(np.max(np.abs(room_noise))) or 1.0
    room_noise = (room_noise / rn_peak) * 0.24

    if bg_style == "pitwall_telemetry":
        amb = room_noise * (0.14 * bg_level)
        return amb.astype(np.float32)

    if bg_style == "pit_garage_guns":
        guns = np.zeros(n_samples, dtype=np.float32)
        if dur_s >= 0.8:
            guns += _synth_wheel_gun_burst(n_samples, sr, min(dur_s * 0.35, 1.1))
        if dur_s >= 2.8:
            guns += 0.85 * _synth_wheel_gun_burst(n_samples, sr, dur_s * 0.72)
        amb = (room_noise + 0.85 * guns) * (0.17 * bg_level)
        return _bandpass_fft(amb, sr, 360.0, 3100.0)

    # Por defecto: "pitwall_f1_flyby" -> Monoplazas F1 pasando a fondo junto al muro de boxes (efecto Doppler)
    flybys = np.zeros(n_samples, dtype=np.float32)
    if dur_s >= 0.6:
        c1 = min(dur_s * 0.32, 1.25)
        flybys += _synth_single_f1_flyby(n_samples, sr, center_sec=c1, base_hz=610.0)
    if dur_s >= 2.5:
        c2 = dur_s * 0.74
        flybys += 0.85 * _synth_single_f1_flyby(n_samples, sr, center_sec=c2, base_hz=565.0)
    if dur_s >= 5.2:
        c3 = dur_s * 0.52
        flybys += 0.70 * _synth_single_f1_flyby(n_samples, sr, center_sec=c3, base_hz=640.0)

    amb = (room_noise + 0.90 * flybys) * (0.19 * bg_level)
    return _bandpass_fft(amb, sr, 350.0, 3150.0)


def apply_f1_radio_effect(
    samples: np.ndarray,
    sr: int,
    intensity: float = 0.85,
    volume: float = 1.0,
    beep_enabled: bool = True,
    beep_style: str = "f1_tv",
    bg_enabled: bool = True,
    bg_style: str = "pitwall_f1_flyby",
    bg_level: float = 0.65,
) -> np.ndarray:
    """Aplica el efecto de radio de Formula 1 TV + Beep oficial + ambiente de muro / F1 pasando."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = samples.astype(np.float32)
    intensity = float(np.clip(intensity, 0.0, 1.0))
    bg_level = float(np.clip(bg_level, 0.0, 1.0)) if bg_enabled else 0.0

    # Normalizar la voz original primero
    raw_peak = float(np.max(np.abs(samples))) or 1.0
    norm_voice = samples / raw_peak

    if intensity <= 0.02:
        voice_out = norm_voice * 0.82
        if bg_enabled and bg_level > 0.01 and bg_style != "off":
            voice_out = voice_out + _synth_pitwall_ambience(len(voice_out), sr, bg_level, bg_style)
    else:
        # 1. Paso banda telefonico/radio + realce de medios
        filtered = _bandpass_fft(norm_voice, sr, low_hz=350.0, high_hz=3200.0)

        # 2. Normalizacion previa y compresion / saturacion suave (walkie overdrive)
        peak = float(np.max(np.abs(filtered))) or 1.0
        normed = filtered / peak
        drive = 1.6 + 2.4 * intensity
        saturated = np.tanh(normed * drive) / np.tanh(drive)

        # 3. Ruido de portadora de radio + ambiente de muro / F1 pasando de fondo
        rng = np.random.default_rng()
        hiss = rng.normal(0, 1.0, len(saturated)).astype(np.float32)
        hiss = _bandpass_fft(hiss, sr, 450.0, 3000.0)
        hiss_peak = float(np.max(np.abs(hiss))) or 1.0
        hiss = hiss / hiss_peak
        voice_env = np.minimum(1.0, np.abs(saturated) * 3.0 + 0.35)

        pit_amb = (
            _synth_pitwall_ambience(len(saturated), sr, bg_level, bg_style)
            if (bg_enabled and bg_level > 0.01 and bg_style != "off")
            else np.zeros(len(saturated), dtype=np.float32)
        )
        mixed = (
            saturated * (1.0 - 0.10 * intensity)
            + hiss * (0.038 * intensity) * voice_env
            + pit_amb
        )

        # 4. Segundo paso banda ligero para integrar voz + ambiente dentro del microfono del muro
        mixed = _bandpass_fft(mixed, sr, low_hz=340.0, high_hz=3300.0)
        m_peak = float(np.max(np.abs(mixed))) or 1.0
        mixed = mixed / m_peak * 0.82

        # 5. Mezcla dry/wet segun intensidad
        voice_out = intensity * mixed + (1.0 - intensity) * (norm_voice * 0.80)

    # 6. Anadir pitido oficial de apertura y cierre si esta activado
    active_beep_style = beep_style if beep_enabled else "off"
    if active_beep_style != "off":
        full = np.concatenate([
            _synth_chirp_open(sr, max(0.5, intensity), style=active_beep_style),
            voice_out.astype(np.float32),
            _synth_squelch_close(sr, max(0.5, intensity), style=active_beep_style),
        ])
    else:
        full = voice_out.astype(np.float32)

    return np.clip(full * float(volume), -0.98, 0.98)


def play_ack_beep(intensity: float = 0.85, volume: float = 1.0, style: str = "f1_tv") -> None:
    """Reproduce el pitido oficial de apertura de radio cuando se abre el microfono o aparece el HUD."""
    if (style or "f1_tv").lower() == "off":
        return
    sr = 24000
    beep = _synth_chirp_open(sr, max(0.5, intensity), style=style) * float(volume)
    try:
        sd.play(beep, samplerate=sr, blocking=False)
    except Exception:
        pass


def play_close_beep(intensity: float = 0.85, volume: float = 1.0, style: str = "f1_tv") -> None:
    """Reproduce el pitido / squelch de cierre de radio cuando se oculta el HUD."""
    if (style or "f1_tv").lower() == "off":
        return
    sr = 24000
    beep = _synth_squelch_close(sr, max(0.5, intensity), style=style) * float(volume)
    try:
        sd.play(beep, samplerate=sr, blocking=False)
    except Exception:
        pass
