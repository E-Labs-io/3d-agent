# Manufacturing Plan — Drone Rocket Mk II

**Version**: 2026-05-03-1
**Build volume assumed**: 300 × 300 × 300 mm (e.g. Bambu X1C, Prusa MK4 with Z-extender, Voron 2.4 350)
**Total print time**: ~84 h   |   **Total assembly time**: 8–12 h

---

## 1. Print sections — overview

The body is split into **five 200 mm sections** plus the nose, all print-volume-friendly:

| # | Section | Y-range (mm) | Print orientation | Material | Walls | Infill | Estimated time |
|--:|---------|--------------|-------------------|----------|------:|-------:|---------------:|
| 1 | Nose & Intake | 800 – 1000 | Tip-up, no supports below 870 | PETG translucent | 5 | 15 % gyroid | 9 h |
| 2 | Avionics | 600 – 800 | Vertical, hollow shell | PETG translucent | 4 | 20 % gyroid | 11 h |
| 3 | Battery + Canards | 400 – 600 | Vertical | PETG translucent | 4 | 20 % gyroid | 12 h |
| 4 | EDF Duct | 200 – 400 | **Inverted** (dome-up) for clean ID | ASA | 6 | 30 % cubic | 14 h |
| 5 | Tail | 0 – 200 | Vertical, base down | PETG | 4 | 25 % gyroid | 10 h |

The remaining ~28 h is parts: motor pods, fan blades, stators, servo mount rings, canards, fins, gimbal rings, intake struts, nozzle bell.

### Why split here?

- 200 mm matches a 300 mm bed comfortably (Z headroom for nozzle, brim, supports)
- Each split lands at a non-load-bearing location — between subsystems
- Visible joint band (red accent ring) doubles as a service marker
- Internal components fit through the largest opening (Ø140 mm ID)

---

## 2. Print settings per material

### PETG (general body, fins, brackets)

| Setting | Value |
|---------|-------|
| Nozzle | 0.4 mm |
| Layer height | 0.2 mm |
| Walls / perimeters | 4 |
| Top / bottom layers | 5 / 4 |
| Infill | 20 % gyroid |
| Print temperature | 240 °C |
| Bed temperature | 80 °C |
| Speed | 60 mm/s outer, 90 mm/s inner |
| Cooling | 50 % from layer 3 |
| Retraction | 4 mm @ 40 mm/s |

### ASA (EDF duct, nozzle bell — heat-tolerant)

| Setting | Value |
|---------|-------|
| Nozzle | 0.4 mm |
| Layer height | 0.2 mm |
| Walls | 6 |
| Infill | 30 % cubic |
| Print temperature | 250 °C |
| Bed temperature | 100 °C |
| Chamber temperature | 50 °C minimum (enclosed printer required) |
| Speed | 50 mm/s |
| Cooling | 0–10 % (avoid warping) |

### PA-CF (load-bearing: motor struts, fan blades, gimbal rings, fin mounts)

| Setting | Value |
|---------|-------|
| Nozzle | 0.4 mm hardened steel **(carbon abrasive)** |
| Layer height | 0.15 mm |
| Walls | 6 |
| Infill | 40 % cubic |
| Print temperature | 290 °C |
| Bed temperature | 100 °C |
| Drying | **Required** — 8 h at 80 °C before printing |
| Annealing | 4 h at 90 °C post-print for full strength |
| Speed | 30 mm/s |

---

## 3. Print sequence (recommended order)

1. **Nose section** (1 print, 9 h) — print first to validate fit + finish quality
2. **Body sections 2 / 3 / 5** (parallel batch on 3 printers, or 33 h sequential)
3. **EDF duct (Section 4)** — needs ASA + enclosed printer; print while bodies print elsewhere
4. **Mechanical sub-assemblies** (small parts, 8 h batched):
   - Both motor pods + struts (PA-CF, 1 batch)
   - Both rotor sets (PA-CF, 1 batch — balance critical, see §5)
   - Both stator sets (PETG, 1 batch)
   - 4 canards + 4 tail fins (PA-CF, 1 batch)
   - All servo mount rings (PA-CF, 1 batch)
   - Gimbal rings + nozzle bell (mixed, 1 batch)
   - All accent rings + collars (PETG accent red, 1 batch)
5. **Final fit-check parts** — 6× intake struts, intake lip, throat insert

---

## 4. Section interface design

### Geometry

Each section joint at y = 200, 400, 600, 800 mm uses:

- **Bayonet pins** (×6 per joint): M3 × 16 hardened dowel pins, pressed into upper section, sliding into mating slots in lower section
- **Through-bolts** (×6 per joint): M3 × 8 cap-heads through dowel-pin lugs into M3 heat-set inserts in the mating section. Quarter-turn engagement.
- **O-ring seal** (140 mm ID NBR): seats in a groove on the mating face for IP54-equivalent sealing
- **Visual band**: contrasting accent ring (red PETG) covers the parting line cosmetically

### Assembly

1. Lower section's interface ring sits face-up on the bench
2. O-ring seated in its groove, lightly greased with silicone grease
3. Upper section's bayonet pins aligned with lower section's slots
4. Lower onto pins; rotate quarter-turn clockwise to seat
5. Insert and tighten 6 × M3 × 8 cap-heads through the through-bolt holes (Loctite 243 medium-strength threadlocker on each)
6. Torque to 0.6 N·m (snug — these are loaded in shear, not tension)

### Tolerances

- Bayonet pin slot width: nominal 3.05 mm (+0.05 / -0.00) — slip fit on 3 mm pin
- Mating face flatness: 0.2 mm over 150 mm — print orientation matters; layer adhesion lines should be parallel to mating face
- O-ring groove: 1.5 mm × 2.0 mm rectangular cross-section

---

## 5. Special manufacturing concerns

### EDF rotor balancing

Both rotor sets must be statically balanced before final assembly:

1. Print rotor with PA-CF (annealed)
2. Mount on a balancing stand or a horizontal precision pin
3. Rotate; identify heavy side (rests at bottom)
4. Sand 0.1–0.2 mm from the lighter blade tip(s) until rotor stays in any rotational position
5. Mark dynamically-balanced face of motor mount with a punch dot for orientation reference

Tolerance: residual imbalance < 0.5 g·mm. Above this, vibration causes audible drone and IMU noise.

### EDF duct surface finish

The inner surface of the duct (inside Section 4) must be smooth. ASA self-smooths reasonably with chamber-controlled printing. If banding is visible:

- Light sand with 400 grit
- Acetone vapour smoothing — 30 seconds at 25 °C in an extraction-vented chamber (ASA only — never PETG or PLA)

### Print orientation gotchas

- **Fan blades**: print **flat on bed** (XY oriented) so layer lines run perpendicular to centrifugal load. Vertical printing fails at the root.
- **Motor struts**: print **horizontal**, with brim, layer lines parallel to long axis.
- **Section 4 (EDF duct)**: print **inverted** (dome side up) so the inner liner surface comes out clean. Use tree supports for the upper rim.
- **Body sections 2, 3, 5**: standard upright.

### Annealing PA-CF parts

Required for parts subjected to fatigue (motor struts, gimbal rings, rotor blades, fin mounts):

1. Print, remove from bed
2. Place on level glass tray
3. 4 h at 90 °C (regular oven works)
4. Cool slowly in oven to room temp (don't open door)
5. Expect 0.3–0.6 % shrinkage isotropically — design parts 0.5 % oversized

---

## 6. Heat-set insert installation

Required for every threaded mounting point in printed parts:

1. Use a soldering iron at 220 °C with a flat tip
2. Place insert into hole (sized to print 0.2 mm under the insert OD)
3. Press straight down with the iron tip; let the brass melt into the plastic for 3–5 seconds
4. Release before brass cools; wipe iron tip
5. Verify perpendicularity with a square; use a M3 cap-head temporarily as alignment if needed

Allow inserts to cool fully (5 min) before applying torque.

---

## 7. Electrical assembly

### Pre-flight checklist

- [ ] All wiring soldered, heat-shrunk, and strain-relieved
- [ ] XT90 connectors keyed with anti-spark resistor present (battery side)
- [ ] ESC firmware verified (BLHeli-32, latest, motor direction set per CW/CCW pair)
- [ ] FC firmware: Ardupilot Plane 4.5+ in tilt-rotor / VTOL mode, contra-prop tail-sitter profile
- [ ] Telemetry radio bound, RSSI ≥ -90 dBm at 100 m bench test
- [ ] Battery cell voltages within 0.05 V of each other before first flight

### Power flow

```
Battery (22.2 V 5000 mAh)
   │
   ├─ XT90 → distribution board
        ├─ ESC1 → Upper EDF (CW)
        ├─ ESC2 → Lower EDF (CCW)
        ├─ 10 V BEC → FC, GPS, telemetry
        └─ 5 V BEC → 8 servos + 2 actuators (peak draw 12 A)
```

### Signal flow (PWM/DSHOT)

- FC → ESC1 / ESC2: DSHOT600 over short (<200 mm) signal wires
- FC → 8 fin servos: PWM 333 Hz, 4 channels per servo bus expander
- FC → 2 gimbal actuators: PWM 50 Hz
- FC → telemetry: UART, 57600 baud
- FC → GPS: UART, 38400 baud

---

## 8. Quality control checks

### Per-print

- Visual: no layer separation, no warping at base, no stringing in cavities
- Dimensional: random measurement at 5 points, all within ±0.3 mm of CAD
- Wall: no light visible through 4-wall PETG sections (held to bright LED)

### Sub-assembly

- Section joints engage with hand pressure; bayonet engagement audible click
- Each fin pivots through full ±25° travel without binding
- Gimbal pivots ±15° each axis without binding
- Both rotors spin freely on their motor shafts
- Static balance check on rotors (per §5)

### System-level (pre-flight)

- AUW within 5 % of design target (2.40 kg)
- CG within 10 mm of design point (y = 480 mm aft of nose tip)
- All control surfaces respond to FC commands in correct direction
- Both EDFs spool up smoothly to 30 % throttle on the bench (tied down!) without unusual sound

---

## 9. Tooling required

| Tool | Use | Notes |
|------|-----|-------|
| Soldering iron, 50 W min, fine tip | Heat-set inserts, electrical | Adjustable temp essential |
| Hex / Allen keys, M2 / M2.5 / M3 | All fastening | Ball-end set preferred |
| Torque driver, 0.1–1 N·m | Section bolts, motor mount | Wera or similar |
| Digital calipers | Print verification | 150 mm range |
| Multimeter | Continuity, voltage checks | |
| Helping-hands w/ magnifier | Soldering small connectors | |
| Print build plate scraper | Removing prints | |
| Filament drier | PA-CF prep | 80 °C, 8 h capacity |
| Convection oven | PA-CF annealing | 90 °C accurate |
| Balancing stand or precision pin | Rotor balancing | Custom or hobby-grade |
| Heat gun | Heat-shrink, post-print stress relief | |
| Cyanoacrylate + activator | Bonding repairs | If needed |

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Rotor imbalance → vibration → IMU noise → unstable flight | Medium | High | Static balance per §5; flight controller filtering tuned |
| Section bayonet wear → loose joint | Low | Medium | Use M3 dowel pins (hard) not printed pins; 24-bolt secondary retention |
| ASA duct delaminates from print on heat | Low | Medium | Enclosed printer only; chamber 50 °C+; 6-wall print |
| Battery thermal runaway | Low | Critical | Quality cells (Sony VTC6); BMS; thermal fuse on pack; LiPo bag during charging |
| EDF blade departure | Very low | Critical | PA-CF with annealing; spinner cap secured with thread-lock; spin-test to 110 % rated RPM before first flight |
| GPS lock loss → mission failure | Medium | Medium | M9N has good multi-constellation; 2 nd antenna location budget |
| Telemetry drop-out | Medium | Low | ELRS long-range; flight controller has loiter-on-loss behaviour configured |

---

## Appendix A — Filament shopping list

| Filament | Quantity | Use |
|----------|---------:|-----|
| PETG translucent (white tint, 5 %) | 1.0 kg | Body sections, nose, fins (cosmetic) |
| PETG accent red | 0.15 kg | Accent rings, spinners, hub caps |
| PETG dark grey | 0.15 kg | Collars, intake struts |
| ASA matte black | 0.5 kg | EDF duct, nozzle bell, throat |
| PA-CF black | 0.4 kg | Motor struts, blades, gimbal, mount rings |

Total filament: ~2.2 kg (allows 30 % wastage for failed prints / supports / brims).
