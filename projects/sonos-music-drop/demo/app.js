(function () {
  'use strict';

  const stateApi = window.SonosDucker;
  const elements = {
    volume: document.getElementById('volume'),
    target: document.getElementById('target'),
    volumeOutput: document.getElementById('volume-output'),
    targetOutput: document.getElementById('target-output'),
    volumeValue: document.getElementById('volume-value'),
    meter: document.getElementById('meter'),
    meterFill: document.getElementById('meter-fill'),
    begin: document.getElementById('begin'),
    end: document.getElementById('end'),
    reset: document.getElementById('reset'),
    status: document.getElementById('status'),
    statusText: document.getElementById('status-text'),
    caption: document.getElementById('state-caption'),
    volumeCaption: document.getElementById('volume-caption'),
  };
  let state = stateApi.createInitialState();

  function render() {
    const startingVolume = state.active ? state.original : state.volume;
    elements.volume.value = String(startingVolume);
    elements.target.value = String(state.target);
    elements.volumeOutput.value = `${startingVolume}%`;
    elements.targetOutput.value = `${state.target}%`;
    elements.volumeValue.innerHTML = `${state.volume}<span>%</span>`;
    elements.meterFill.style.width = `${state.volume}%`;
    elements.meter.setAttribute('aria-label', `Music volume ${state.volume} percent`);
    elements.volume.disabled = state.active;
    elements.target.disabled = state.active;
    elements.begin.disabled = state.active;
    elements.end.disabled = !state.active;
    elements.status.classList.toggle('active', state.active);
    elements.statusText.textContent = state.active ? 'Speaking level active' : 'Ready when you are';
    elements.volumeCaption.textContent = state.active
      ? `Lowered for speaking · original level ${state.original}%.`
      : 'Your room, your level.';
    elements.caption.textContent = state.active
      ? `Music is at ${state.volume}%. End speaking to restore ${state.original}%.`
      : 'Adjust the sample levels, then begin to see the change.';
  }

  elements.volume.addEventListener('input', () => {
    state = stateApi.setVolume(state, Number(elements.volume.value));
    render();
  });
  elements.target.addEventListener('input', () => {
    state = stateApi.setTarget(state, Number(elements.target.value));
    render();
  });
  elements.begin.addEventListener('click', () => {
    state = stateApi.beginDucking(state);
    render();
  });
  elements.end.addEventListener('click', () => {
    state = stateApi.endDucking(state);
    render();
  });
  elements.reset.addEventListener('click', () => {
    state = stateApi.resetDemo(state);
    render();
  });
  render();
})();
