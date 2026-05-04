# Assembly Instructions — Drone Rocket Mk II

**Version**: 2026-05-03-1
**Estimated time**: 8–12 hours (skilled operator, single technician)
**Cross-reference**: All [BOM] callouts reference [BOM.md](BOM.md) line numbers; [DRG] callouts reference [drawings/](drawings/).

---

## Tools & consumables required

Have these to hand before starting:

- Soldering iron, 50 W, fine + flat tips, 220–280 °C adjustable
- Hex / Allen keys, 1.5 / 2 / 2.5 / 3 mm (ball-end set)
- Phillips screwdriver, PH00 + PH0
- Torque driver 0.1–1 N·m (e.g. Wera 7440)
- Digital calipers, 150 mm
- Multimeter
- Helping-hands stand with magnifier
- Loctite 243 medium-strength threadlocker
- Silicone grease (small tube)
- Heat gun
- Soft brush + isopropyl alcohol (for print prep)

---

## Stage 1 — Print prep (≈30 min)

1. Inspect every printed part for layer separation, warping, or stringing → reject and re-print if found.
2. Light deburr with hobby knife at all edges and bayonet pin slots. Don't oversize.
3. Clean all parts with IPA brush. Allow to dry.
4. Confirm dimensions on the four section interface rings using calipers — bayonet slots should be **3.05 (+0.05/-0.00) mm**. Reject parts outside tolerance.
5. **For all PA-CF parts**: confirm they have been annealed (4 h @ 90 °C). Tap test — should sound crisp, not damp.

---

## Stage 2 — Heat-set inserts (≈45 min)

Install M3 brass heat-set inserts [BOM #74] into all printed mounting points. Required locations:

| Section | Insert count | Position |
|---------|:------------:|----------|
| Section 2 (Avionics) | 8 | 4 servo mount ring + 4 column retention |
| Section 3 (Battery + Canards) | 12 | 4 canard servo screws × 4 servos − 4 = 12; plus 4 ring retention |
| Section 4 (EDF Duct) | 16 | 4 motor pod × 2 stages = 8; 4 ESC mount × 2 = 8 |
| Section 5 (Tail) | 12 | 4 fin servo × 4 servos = 16; 4 gimbal ring; 4 nozzle attach |
| Each section interface | 6 | M3×8 through-bolt locations |

**Procedure:**
1. Solder iron at 220 °C with flat tip
2. Pre-heat tip 30 sec
3. Place insert in pre-printed hole (insert OD 4.2 mm, hole 4.0 mm)
4. Press iron onto insert face, light pressure, 3–5 seconds
5. Release iron when insert is flush with surface
6. Allow 5 min cool before applying any torque

→ See [DRG 02](drawings/02-section-view.svg) for exact insert locations.

---

## Stage 3 — Build the avionics column (Section 2) (≈75 min)

1. Locate BOM #21 Central Avionics Column.
2. Test-fit Pixhawk FC [#23] inside column at y = 720 mm position. It should slide in with 1 mm clearance per side. Apply 3 mm vibration-damping foam pad [#28] to the underside before final mount.
3. Wire harness preparation:
   - Solder XT60 connector to FC power input lead
   - Tin the GPS, radio, and servo bus signal wires
   - All wire-to-wire joints inside heat-shrink, ≥ 6 mm length
4. Mount FC with 4× M3×6 cap-heads through the column wall threaded inserts. Torque 0.3 N·m.
5. Mount GPS module [#25] above FC at y = 740 mm. Use the GPS bracket (printed with Section 2).
6. Mount telemetry radio [#26] at y = 700 mm. The antenna wire [#27] runs through the column wall slot and out through the body shell at the planned exit point.
7. Connect GPS UART to FC TELEM1, radio UART to FC TELEM2.
8. Power-on bench test:
   - 22.2 V from bench supply via XT60
   - FC LED solid green = OK
   - Mission Planner / QGroundControl connect = OK
   - GPS lock within 3 min outdoors = OK
   - Radio bind to ground station = OK
9. Power off, secure all wires with cable ties / clips.

---

## Stage 4 — Build the battery + canards (Section 3) (≈90 min)

1. Slide battery column [BOM #30] into Section 3 from the top.
2. Pre-fit battery pack [#31] (do not connect XT90 yet). Confirm it sits with 1 mm clearance. Add foam pad if loose.
3. Connect XT90 anti-spark connector [#36] to battery pack. Insulate exposed terminals with heat-shrink.
4. **Canards (×4)** — each canard repeats the same steps:

   a. Press a 4 mm bearing [#56] into the inner side of the canard pivot bore.
   b. Insert pivot shaft [#52] (4 mm) through bearing.
   c. Press the second bearing into the outer side. Confirm shaft rotates freely.
   d. Slide canard fin [#53] onto the protruding shaft end. Pin with M3 grub screw + threadlocker.
   e. Mount canard servo [#54] in the servo housing using 2× M2×6 cap-heads. Confirm servo arm clears the column wall.
   f. Connect M3 ball-link rod [#55] between servo arm and fin's control horn. Servo arm at 0° = fin at 0° (centred).
   g. Connect servo signal wire to FC AUX channel (canard 1 = AUX1, canard 2 = AUX2, etc.)
5. **Repeat for all 4 canards** — they are at 45°, 135°, 225°, 315° positions around the body.
6. Bench test all 4 canards: command FC servo travel, verify ±20° travel both directions without binding.

→ See [DRG 03](drawings/03-plan-view.svg) for canard positioning angles.

---

## Stage 5 — Build the contra-rotating EDF assembly (Section 4) (≈3 h)

This is the most critical assembly stage. Take your time.

### 5a. Install the duct liner

1. Slide EDF duct inner liner [#12] into Section 4 from the top.
2. Confirm fit — interference fit should be smooth, fully seated when ASA liner protrudes 0 mm above the section rim.

### 5b. Pre-balance both rotors

This **must** happen before installation. Skipping this causes vibration → crashes.

1. Mount rotor [#40 upper, #46 lower] on a balancing stand or precision pin.
2. Allow rotor to settle. Identify heaviest blade tip (rests at bottom).
3. With 400-grit sandpaper, gently remove material from heaviest blade tip — 0.05 mm per pass.
4. Re-test. Repeat until rotor stays in any rotational position when nudged.
5. Mark balanced face of rotor with a sharpie dot near the hub.
6. Repeat for second rotor.

### 5c. Install lower EDF (CCW) first (it's at the bottom of the duct)

1. Install lower motor pod [#44] into the duct using 4× M3×8 cap-heads through duct wall into pod inserts. Torque 0.6 N·m.
2. Install lower motor mount struts [#45] between pod and duct wall — these are pressed into pre-printed slots. Threadlocker on the screws.
3. Install the BLDC motor [#49] into the pod, secured with 4× M3×6 from below the pod. Use threadlocker. Torque 0.4 N·m.
4. Solder phase wires from motor (3× phase) to ESC2 [#35]. Use 12 AWG silicone, length 200 mm.
5. Slide ESC2 into its peripheral mount in Section 4 (one of the two ESC pod slots [#33]).
6. Mount lower stator vanes [#47] above the motor pod. They press-fit into duct grooves and don't need bolting.
7. Install lower rotor [#46] onto motor shaft. Torque the rotor lock-nut to 1.0 N·m with threadlocker.
8. Cap with lower spinner [#48] — friction-fit, sometimes hot-glue or lock-tite the threads.

### 5d. Install upper EDF (CW)

Identical process at the upper end of Section 4, with these differences:
- Upper motor [#43] wired in REVERSE: swap any two of the three phase wires before connecting to ESC1
- Upper rotor [#40] is the CW-pitched one (visually distinct — note the pitch direction at hub)
- Upper stators mount with vanes orientated **opposite** of the lower stators (their leading edges face downward)

### 5e. Wire ESCs to FC

1. ESC1 (upper / CW) → FC motor channel 1 (DSHOT600)
2. ESC2 (lower / CCW) → FC motor channel 2 (DSHOT600)
3. ESCs share +12 V from distribution board [#37]
4. Verify on bench (rocket clamped down, props clear of obstruction):
   - Throttle to 5 % → smooth spin-up
   - Visual: upper rotor spinning CW (looking down), lower spinning CCW
   - If wrong direction: swap two phase wires on the appropriate motor and re-test
   - Throttle to 50 % for 10 sec → no vibration, no smoke

### 5f. Final balance check after install

If you feel any low-frequency vibration during the 50 % spin-up, the rotors are out of balance in their motor frame. Remove and re-balance per §5b — being on the motor frame can introduce small imbalances vs. balanced on a free pin.

→ See [DRG 06](drawings/06-edf-detail.svg) for exact EDF stage layout and rotation directions.

---

## Stage 6 — Build the tail + gimbal (Section 5) (≈90 min)

### 6a. Tail fins (×4)

Same process as canards (Stage 4), but at cardinal positions (0/90/180/270°) and using:
- 5 mm bearings [#63] (vs. 4 mm canard)
- KST X10 servos [#61] (more torque)
- 5 mm pivot shafts [#60]

→ See [DRG 04](drawings/04-bottom-view.svg).

### 6b. Gimbal frame

1. Press gimbal pivot bearings [#66] into the outer ring [#64] (4× MR62ZZ flanged).
2. Insert M2 dowel pins [#70] through bearings.
3. Mount the inner ring [#65] orthogonally onto the dowels.
4. Verify both axes pivot freely through ±15° each.
5. Attach 2× linear actuators [#67] to the inner ring's drive points (one for pitch, one for yaw).
6. Connect actuator wires to FC AUX9 (pitch) and AUX10 (yaw).

### 6c. Mount nozzle

1. Test-fit nozzle bell [#68] onto the inner gimbal ring's nozzle attachment plate (4× M3×6).
2. Threadlocker on each screw.
3. Slide nozzle throat insert [#69] into the bell from the top — friction-fit.
4. Verify gimbal range with nozzle installed: ±15° pitch, ±15° yaw, no contact with body shell.

---

## Stage 7 — Build the nose (Section 1) (≈30 min)

1. Mount pitot tube [BOM #3] in nose tip — secure with epoxy, sealed for IP.
2. Connect pitot pneumatic tubes (run through the nose interior) and pitot wiring (5 V supply, I²C signal) to the FC's pitot input.
3. Confirm nose collar [#2] and intake collar lower [#6] are seated correctly with intake struts [#4] connecting them.
4. Test-fit lower section before continuing — Section 1 should mate cleanly with Section 2 via bayonet.

---

## Stage 8 — Final stack assembly (≈90 min)

This is best done with the rocket horizontal on a padded bench.

1. Begin from the **tail** end. Place Section 5 (Tail) on the bench, gimbal pointing up.
2. Apply silicone grease to the O-ring [#19] for the y=200 joint.
3. Lower Section 4 (EDF) onto Section 5, aligning bayonet pins. Rotate quarter-turn clockwise to engage.
4. Insert 6× M3×8 cap-heads [#20] through the section ring into Section 5's heat-set inserts. Cross-pattern tighten in stages: snug → 0.3 N·m → 0.6 N·m. Threadlocker on each.
5. **Connect inter-section wiring** at the joint:
   - 12 AWG ESC power leads from Section 4 → battery distribution board (will route up through Section 3)
   - Servo signals from Section 4 ESCs → FC will pass through this joint
   - Threading order matters: route wires before tightening the second section bolt.
6. Repeat for joint y=400: lower Section 3 (Battery+Canards) onto Section 4. Same procedure.
7. Repeat for joint y=600: lower Section 2 (Avionics) onto Section 3.
8. Repeat for joint y=800: place Section 1 (Nose) onto Section 2.
9. After full stack: verify no wires pinched at any joint.
10. Connect battery [#31] to XT90 (anti-spark engagement).
11. Stand the rocket vertical on its tail fins. Verify it stands stably.

→ Final cross-check: refer to [DRG 05](drawings/05-exploded-isometric.svg) for the assembly order at a glance.

---

## Stage 9 — Calibration & tuning (≈60 min)

1. **FC sensor cal** — accelerometer, gyro, compass (in QGroundControl or Mission Planner, follow standard tail-sitter cal flow)
2. **ESC cal** — both ESCs through FC's motor test (DSHOT600 telemetry feedback)
3. **Servo travel limits** — set per-channel min/max for canards (±20°) and tail fins (±25°)
4. **Gimbal travel** — set actuator endpoints for ±15° each axis
5. **Mixer** — VTOL tail-sitter mode in Ardupilot, contra-rotating tail-sitter profile
6. **PIDs** — start from default tail-sitter values; tune in tethered hover

---

## Stage 10 — Pre-flight (≈30 min)

Use this checklist before every flight.

- [ ] Battery cell voltages all within 0.05 V of each other (4.20 V × 6 = 25.20 V at full)
- [ ] Battery secured in pack column; XT90 connected
- [ ] All section bolts present and torqued (visual check)
- [ ] All 4 canards & 4 tail fins move smoothly when commanded
- [ ] Both rotors spin freely by hand, no rub on duct
- [ ] FC arms; pre-arm checks pass
- [ ] GPS lock (3D, ≥ 8 satellites)
- [ ] Telemetry RSSI ≥ -80 dBm
- [ ] Wind ≤ 5 m/s for first flight
- [ ] Tether ≥ 10 m, secured to anchor (first 5 flights only)
- [ ] Spotter present
- [ ] Emergency stop accessible (arming switch on TX)
- [ ] Fire extinguisher within 3 m
- [ ] Take-off area clear, 15 m radius

---

## Stage 11 — Tethered first flight

1. Arm the FC.
2. Slow throttle increase. At ~50 % throttle the rocket should lift off (T:W ≈ 1.0 at 50 %).
3. Hold at 30 cm hover for 10 sec — observe for vibration, drift, control inputs.
4. Increase to 1 m hover, hold 30 sec.
5. Release tether tension; observe 10 more seconds.
6. Land gently — throttle down through 30 % over 5 sec.

If anything misbehaves at any stage: throttle to 0, allow flight controller to land. **Do not attempt forward-flight transition until at least 5 successful tethered hovers.**

---

## Troubleshooting

| Symptom | Cause | Action |
|---------|-------|--------|
| Rocket yaws steadily on takeoff | Imbalanced ESC1/ESC2 trim | Re-cal ESCs, check motor PWM linearity |
| High-frequency vibration | Rotor imbalance | Re-balance rotors per §5b |
| Low-frequency wobble | PID tuning, or CG too far aft | Adjust PIDs, verify CG ≤ 480 mm |
| One side spinner failing on spin-up | Reverse-wired motor not properly configured | Check ESC firmware for "reverse" flag, OR swap two phase wires |
| FC reboot during flight | Brownout from battery sag | Check battery cell health, voltage at FC under load |
| GPS lock loss | Antenna shielded | Verify antenna position, no metal nearby |
| Servo jitter | EMI from ESCs | Ferrite cores on servo signal wires; separate signal/power runs |

---

## Service & maintenance schedule

| Interval | Action |
|----------|--------|
| Pre-flight | Full visual + checklist (above) |
| Every 5 flights | Re-torque section bolts; visual inspection of fins/canards |
| Every 25 flights | Re-balance rotors (after impacts or rough landings) |
| Every 50 flights | Replace bearings (#56, #63, #66) |
| Every 100 flights | Strip and rebuild EDF stages; replace motor wear items |
| As needed | Battery cell rebalance (every 30 cycles); replace if any cell drifts > 0.1 V |

---

End of assembly instructions. **Fly safe. Keep records of every flight in a log.**
