// Sound system with mute toggle and reactive ambient loops.
// Browser autoplay policy is respected: sound is muted by default
// and only starts after the user unmutes/interacts with the page.

let _muted = true;
let _audioElements = {};
let _activeAmbient = null;
let _activeSound = null;
let _currentReactiveIntensity = null;
let _volumeRafs = {};

const DEFAULT_SOUND = {
  mode: "direct",
  min_volume: 0,
  max_volume: 0.35,
};

export function setupSound() {
  // Create the audio elements.
  const definitions = {
    smog_loop: { src: "/sounds/smog_loop.ogg", loop: true, volume: 0.25 },
    rain_loop: { src: "/sounds/rain_loop.wav", loop: true, volume: 0 },
    traffic_noise_loop: { src: "/sounds/traffic_noise_loop.wav", loop: true, volume: 0 },
    click: { src: "/sounds/click.ogg", loop: false, volume: 0.5 },
    footstep: { src: "/sounds/footstep.ogg", loop: false, volume: 0.4 },
    whoosh: { src: "/sounds/whoosh.ogg", loop: false, volume: 0.5 },
  };

  for (const [name, def] of Object.entries(definitions)) {
    const audio = new Audio(def.src);
    audio.loop = def.loop;
    audio.volume = def.volume;
    audio.preload = "auto";
    _audioElements[name] = audio;
  }

  // Hook the mute button.
  const btn = document.getElementById("muteButton");
  if (btn) {
    btn.addEventListener("click", toggleMute);
  }

  // Unlock audio on first user gesture.
  const unlock = () => {
    for (const audio of Object.values(_audioElements)) {
      const volume = audio.volume;
      audio.volume = 0;
      audio.play().catch(() => {});
      audio.pause();
      audio.currentTime = 0;
      audio.volume = volume;
    }
    if (!_muted && _activeAmbient) ensureLoopPlaying(_activeAmbient);
    document.removeEventListener("click", unlock);
    document.removeEventListener("keydown", unlock);
  };
  document.addEventListener("click", unlock, { once: false });
  document.addEventListener("keydown", unlock, { once: false });

  updateMuteIcon();
}

export function toggleMute() {
  _muted = !_muted;
  for (const audio of Object.values(_audioElements)) {
    if (audio.loop && _muted) audio.pause();
  }
  if (!_muted && _activeAmbient) {
    ensureLoopPlaying(_activeAmbient);
  }
  updateMuteIcon();
}

export function isMuted() {
  return _muted;
}

function updateMuteIcon() {
  const icon = document.getElementById("muteIcon");
  if (!icon) return;
  icon.style.backgroundImage = _muted
    ? "url('/sprites/ui/icon_sound_off.png')"
    : "url('/sprites/ui/icon_sound_on.png')";
}

export function play(name) {
  if (_muted) return;
  const audio = _audioElements[name];
  if (!audio) return;
  if (audio.loop) {
    // For loops, only start if not already playing.
    if (audio.paused) audio.play().catch(() => {});
  } else {
    audio.currentTime = 0;
    audio.play().catch(() => {});
  }
}

export function stop(name) {
  const audio = _audioElements[name];
  if (!audio) return;
  cancelVolumeRamp(name);
  audio.pause();
  audio.currentTime = 0;
}

export function setActiveAmbient(expo = {}) {
  const cfg = expo?.sound;
  if (!cfg?.ambient) {
    stopAmbient();
    return;
  }
  const nextAmbient = cfg.ambient;
  if (_activeAmbient && _activeAmbient !== nextAmbient) {
    fadeLoopTo(_activeAmbient, 0, 180, true);
  }
  _activeAmbient = nextAmbient;
  _activeSound = { ...DEFAULT_SOUND, ...cfg };
  _currentReactiveIntensity = null;
  fadeLoopTo(nextAmbient, 0, 80, false);
  if (!_muted) ensureLoopPlaying(nextAmbient);
}

export function setReactiveIntensity(intensity) {
  if (!_activeAmbient || !_activeSound) return;
  if (typeof intensity !== "number" || Number.isNaN(intensity)) {
    clearReactiveIntensity();
    return;
  }
  const t = clamp01(_activeSound.mode === "inverse" ? 1 - intensity : intensity);
  _currentReactiveIntensity = t;
  const minVol = numberOr(_activeSound.min_volume, DEFAULT_SOUND.min_volume);
  const maxVol = numberOr(_activeSound.max_volume, DEFAULT_SOUND.max_volume);
  const volume = minVol + t * Math.max(0, maxVol - minVol);
  fadeLoopTo(_activeAmbient, volume, 180, false);
  if (!_muted) ensureLoopPlaying(_activeAmbient);
}

export function clearReactiveIntensity() {
  _currentReactiveIntensity = null;
  if (_activeAmbient) fadeLoopTo(_activeAmbient, 0, 180, false);
}

export function stopAmbient() {
  if (_activeAmbient) fadeLoopTo(_activeAmbient, 0, 160, true);
  _activeAmbient = null;
  _activeSound = null;
  _currentReactiveIntensity = null;
}

export function stopAllLoops() {
  _activeAmbient = null;
  _activeSound = null;
  _currentReactiveIntensity = null;
  for (const audio of Object.values(_audioElements)) {
    if (audio.loop) audio.pause();
  }
}

function ensureLoopPlaying(name) {
  const audio = _audioElements[name];
  if (!audio || !audio.loop || _muted) return;
  if (audio.paused) audio.play().catch(() => {});
}

function fadeLoopTo(name, targetVolume, durationMs = 180, pauseAtEnd = false) {
  const audio = _audioElements[name];
  if (!audio) return;
  const target = clamp01(targetVolume);
  cancelVolumeRamp(name);
  if (typeof requestAnimationFrame !== "function") {
    audio.volume = target;
    if (pauseAtEnd && target === 0) audio.pause();
    return;
  }
  const startVolume = audio.volume;
  const start = nowMs();
  const tick = () => {
    const elapsed = nowMs() - start;
    const t = clamp01(elapsed / Math.max(1, durationMs));
    audio.volume = startVolume + (target - startVolume) * easeOut(t);
    if (t < 1) {
      _volumeRafs[name] = requestAnimationFrame(tick);
      return;
    }
    delete _volumeRafs[name];
    audio.volume = target;
    if (pauseAtEnd && target === 0) audio.pause();
  };
  _volumeRafs[name] = requestAnimationFrame(tick);
}

function cancelVolumeRamp(name) {
  const raf = _volumeRafs[name];
  if (raf && typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf);
  delete _volumeRafs[name];
}

function clamp01(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function numberOr(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function easeOut(t) {
  return 1 - Math.pow(1 - t, 3);
}

function nowMs() {
  return typeof performance !== "undefined" && performance.now
    ? performance.now()
    : Date.now();
}

export function _getSoundStateForTests() {
  return {
    muted: _muted,
    activeAmbient: _activeAmbient,
    activeSound: _activeSound,
    currentReactiveIntensity: _currentReactiveIntensity,
  };
}
