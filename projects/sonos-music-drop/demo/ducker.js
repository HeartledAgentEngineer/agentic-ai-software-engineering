(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SonosDucker = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const DEFAULTS = Object.freeze({ volume: 40, target: 15, active: false, original: null });

  function createInitialState() {
    return { ...DEFAULTS };
  }

  function validateLevel(level) {
    if (!Number.isInteger(level) || level < 0 || level > 100) {
      throw new RangeError('Level must be an integer from 0 to 100.');
    }
  }

  function setVolume(state, volume) {
    if (state.active) throw new Error('Volume is locked while ducking is active.');
    validateLevel(volume);
    return { ...state, volume };
  }

  function setTarget(state, target) {
    if (state.active) throw new Error('Target is locked while ducking is active.');
    validateLevel(target);
    return { ...state, target };
  }

  function beginDucking(state) {
    if (state.active) return state;
    return {
      ...state,
      original: state.volume,
      volume: Math.min(state.volume, state.target),
      active: true,
    };
  }

  function endDucking(state) {
    if (!state.active) return state;
    return { ...state, volume: state.original, active: false, original: null };
  }

  function resetDemo() {
    return createInitialState();
  }

  return { createInitialState, beginDucking, endDucking, resetDemo, setVolume, setTarget };
});
