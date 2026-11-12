'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  createInitialState,
  beginDucking,
  endDucking,
  resetDemo,
  setVolume,
  setTarget,
} = require('./ducker.js');

test('begin stores the current volume and ducks to the target', () => {
  assert.deepEqual(beginDucking(createInitialState()), {
    volume: 15, target: 15, active: true, original: 40,
  });
});

test('repeated begin keeps the first original volume', () => {
  const active = beginDucking(beginDucking(createInitialState()));
  assert.deepEqual(active, { volume: 15, target: 15, active: true, original: 40 });
});

test('end restores the exact original volume and clears the saved value', () => {
  const ended = endDucking(beginDucking(createInitialState()));
  assert.deepEqual(ended, { volume: 40, target: 15, active: false, original: null });
});

test('end without a prior begin leaves the state unchanged', () => {
  const state = createInitialState();
  assert.deepEqual(endDucking(state), state);
});

test('begin never raises a volume that is already below the target', () => {
  const quiet = setVolume(createInitialState(), 10);
  assert.deepEqual(beginDucking(quiet), { volume: 10, target: 15, active: true, original: 10 });
  assert.deepEqual(endDucking(beginDucking(quiet)), { volume: 10, target: 15, active: false, original: null });
});

test('reset always returns the documented demo defaults', () => {
  assert.deepEqual(resetDemo(beginDucking(createInitialState())), {
    volume: 40, target: 15, active: false, original: null,
  });
});

test('volume and target accept integer boundaries from zero through one hundred', () => {
  assert.equal(setVolume(createInitialState(), 0).volume, 0);
  assert.equal(setVolume(createInitialState(), 100).volume, 100);
  assert.equal(setTarget(createInitialState(), 0).target, 0);
  assert.equal(setTarget(createInitialState(), 100).target, 100);
});

test('volume and target reject fractions and values outside the supported range', () => {
  for (const invalid of [-1, 101, 15.5, NaN, '15', null]) {
    assert.throws(() => setVolume(createInitialState(), invalid), RangeError);
    assert.throws(() => setTarget(createInitialState(), invalid), RangeError);
  }
});

test('active state cannot be changed by either slider setter', () => {
  const active = beginDucking(createInitialState());
  assert.throws(() => setVolume(active, 60), /active/i);
  assert.throws(() => setTarget(active, 25), /active/i);
  assert.deepEqual(active, { volume: 15, target: 15, active: true, original: 40 });
});
