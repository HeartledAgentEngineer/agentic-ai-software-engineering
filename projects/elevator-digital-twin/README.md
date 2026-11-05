# Elevator digital twin

A three-floor elevator controlled by real PLC code. The PLC runs in TwinCAT 3 (simulation mode); a small Node.js
bridge simulates the physics and streams the state to a 3D view in the browser. This is where I come from:
automation logic first, then the software around it.

**Stack:** IEC 61131-3 Structured Text (TwinCAT 3) · Node.js (`ads-client`, `ws`) · Three.js

## How it works

```
Browser (elevator_3d_demo.html, Three.js)
   ↕ WebSocket ws://localhost:3000
ads_bridge/server.js   ← physics simulation (car height, door position), 50 ms cycle
   ↕ ADS (port 851)
TwinCAT PLC   MAIN → FB_Elevator, FB_Door
```

- **PLC side** (`Elevator_TC/Elevator/`): a step chain in `FB_Elevator` (`Init → Idle → DoorClosing → DecideDir →
  MovingUp/MovingDown → Braking → DoorOpening → WaitAtFloor`, plus `Emergency`), a separate `FB_Door`, and global
  I/O in `GVL_Elevator`: floor sensors, door end switches, emergency stop (normally closed), light curtain, fire
  alarm, overload and hall calls per direction.
- **Bridge** (`ads_bridge/server.js`): reads and writes the PLC variables over ADS, simulates what the real
  machine would do (car moves, door opens) and feeds the sensors back. It reconnects on its own if the runtime
  is not reachable.
- **3D HMI** (`elevator_3d_demo.html`): one HTML file, the scene is built from primitives; calls are sent back to
  the PLC through the bridge.

## Run it

Requires TwinCAT 3 XAE with the project activated in simulation mode, and Node.js.

```powershell
cd ads_bridge
npm install
npm start          # or start_elevator.bat, which also opens the 3D page
```

Set your own AMS Net ID in `CFG.amsNetId` in `server.js`.

## What I took from it

Safety signals (emergency stop, light curtain, overload) belong in the PLC, not in the visualisation. The bridge
only simulates the plant; it never decides.

← [Back to overview](../../README.md)
