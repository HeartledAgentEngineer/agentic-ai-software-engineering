# Squirrel game

A small HTML5 canvas game with a reversed idea: you don't collect nuts, you steal them from a squirrel or shake
the branch until it falls. Built spontaneously for a party and sent to the guests' phones as a single file.

**Stack:** HTML5 Canvas · vanilla JavaScript (ES5) · no build, no assets

## How it works

Everything lives in one `index.html` (about 560 lines of JavaScript):

- **Game loop** with `requestAnimationFrame` → `update()` + `draw()`.
- **State machine** instead of scattered flags: `climb → crown → fall → dead → climb`.
- **Levels as data:** an array maps nut thresholds to skins (normal, cool, Frodo, Shrek). One game logic carries
  all four worlds.
- **Procedural graphics:** tree, sky, characters and particles are drawn at runtime. There is no image file.
- **Fixed logical resolution** (480×640), scaled by CSS; touch coordinates are mapped back, so hit tests don't
  depend on the device.

## Decisions

- **One file, zero dependencies.** On a party you don't control the devices; a single HTML file opens anywhere.
- **Own Bézier ovals instead of `ctx.ellipse`**, because older mobile WebViews didn't support it reliably.
- **ES5 syntax** for old Android browsers.

## Run it

Open `index.html` in any browser, desktop or phone. Tap the nut to steal it, tap a branch to shake it.

← [Back to overview](../../README.md)
