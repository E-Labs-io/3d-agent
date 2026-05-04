# Bill of Materials — Drone Rocket Mk II

**Version**: 2026-05-03-1
**Project**: Drone Rocket Mk II — Contra-Rotating EDF
**Total height**: 1000 mm   |   **OD**: 150 mm   |   **Target dry mass**: 1.85 kg   |   **Target AUW**: 2.40 kg

All printed parts are assumed PETG unless noted; substitute PLA for cosmetic shells, ASA for the EDF duct (heat tolerance), and PA-CF (carbon-filled nylon) for any structural part marked "(load-bearing)".

---

## Subsystem totals

| Subsystem | Parts | Subtotal (£) |
|-----------|------:|-------------:|
| 1. Nose & Intake | 8 | 32.50 |
| 2. Structure & Body | 14 | 56.00 |
| 3. Avionics | 7 | 232.00 |
| 4. Power | 6 | 198.00 |
| 5. Propulsion — Upper EDF (CW) | 6 | 142.50 |
| 6. Propulsion — Lower EDF (CCW) | 6 | 142.50 |
| 7. Aero — Canards (×4) | 13 | 96.00 |
| 8. Aero — Tail Fins (×4) | 13 | 84.00 |
| 9. Thrust Vectoring | 11 | 78.00 |
| **Hardware / Consumables** | — | 62.00 |
| **GRAND TOTAL** | **84 line items** | **£1,123.50** |

Lead-time gating part: telemetry radio (5 weeks if Mouser-stocked; 1 week if RS Components has stock).

---

## 1. Nose & Intake

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 1 | `nose_cone` | Ogive Nose Cone | 1 | PETG (translucent white) | Print | 4.50 | print | 120 mm tall, ogive ρ=520 mm |
| 2 | `nose_collar` | Nose Base Collar | 1 | PETG (dark grey) | Print | 1.50 | print | Joint to body section 2 |
| 3 | `pitot_tube` | Pitot Tube | 1 | Matek ASPD-7002 | RS / Mouser | 24.00 | 1 wk | 6 mm OD aluminium, MS4525DO sensor |
| 4 | `intake_struts` | Annular Intake Struts (6× radial) | 1 | PETG (dark grey) | Print | 1.20 | print | Single printed unit, M3 inserts at root |
| 5 | `intake_inner_lip` | Intake Diffuser Lip | 1 | PETG matte black | Print | 0.80 | print | NACA bellmouth profile |
| 6 | `intake_collar_lower` | Intake Lower Collar | 1 | PETG (dark grey) | Print | 0.50 | print | Mates section 1 ↔ section 2 |

**Sub-total: £32.50**

---

## 2. Structure & Body

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 7 | `body_section_2` | Section 2 Shell — Avionics | 1 | PETG translucent (5% tint) | Print | 6.00 | print | 200 mm × Ø150, 3.2 mm wall |
| 8 | `body_section_3` | Section 3 Shell — Battery + Canards | 1 | PETG translucent | Print | 6.00 | print | 4× canard pivot reliefs |
| 9 | `body_section_4` | Section 4 Shell — EDF Duct | 1 | ASA (heat-tolerant) | Print | 9.00 | print | Heat margin from motors; 4 mm wall |
| 10 | `body_section_5` | Section 5 Shell — Tail | 1 | PETG | Print | 5.00 | print | Tapered: 150 ↔ 140 mm OD |
| 11 | `tail_taper` | Tail Convergent Section | 1 | PETG | Print | 3.50 | print | 150 → 80 mm taper |
| 12 | `edf_duct_inner` | EDF Duct Inner Liner | 1 | ASA matte black | Print | 7.50 | print | Smooth ID, anti-noise |
| 13 | `section_ring_800` | Section Joint Ring @ y=800 | 1 | PETG accent red | Print | 1.00 | print | Visible joint band |
| 14 | `section_ring_600` | Section Joint Ring @ y=600 | 1 | PETG accent red | Print | 1.00 | print | |
| 15 | `section_ring_400` | Section Joint Ring @ y=400 | 1 | PETG accent red | Print | 1.00 | print | |
| 16 | `section_ring_200` | Section Joint Ring @ y=200 | 1 | PETG accent red | Print | 1.00 | print | |
| 17 | — | Section bayonet pin | 24 | M3×16 dowel pin, hardened | RS Components | 0.40 | stock | 6 per joint × 4 joints |
| 18 | — | M3 heat-set insert | 24 | Brass M3, OD 4.2 / L 5 mm | AliExpress | 0.10 | stock | 6 per joint × 4 joints |
| 19 | — | O-ring NBR 140 mm ID × 2 mm | 4 | Nitrile O-ring | RS | 1.00 | stock | One per section joint, sealing |
| 20 | — | Section retaining cap-head | 24 | M3×8, A2 stainless | RS | 0.05 | stock | Through-bolts per joint |

**Sub-total: £56.00** (includes hardware listed in this subsystem)

---

## 3. Avionics

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 21 | `avionics_column` | Central Avionics Column | 1 | PETG matte grey | Print | 5.00 | print | 50 mm OD, 3 mm wall, vertical print |
| 22 | `avionics_window` | Inspection Window | 1 | PMMA / acrylic 2 mm, smoke tint | Local plastic | 3.00 | stock | Cut to 50×30 mm |
| 23 | `flight_computer` | Holybro Pixhawk 6C Mini | 1 | FC + IMU + barometer | Holybro | 145.00 | 2 wk | Includes ICM-42688-P, BMM150, MS5611 |
| 24 | `flight_computer_chip` | (FC processor — visible CAD only) | — | — | — | — | — | Represented in CAD; included in #23 |
| 25 | `gps_module` | Holybro M9N GPS + Compass | 1 | u-blox M9N | Holybro | 32.00 | 2 wk | Helical antenna |
| 26 | `radio_module` | ELRS 868/915 MHz Tx/Rx | 1 | Happymodel ES915TX/RX | RDQ | 28.00 | 1 wk | Long-range telemetry |
| 27 | `radio_antenna` | T-antenna 868 MHz | 1 | 3 dBi external whip | RDQ | 8.00 | 1 wk | SMA mount through body |
| 28 | — | Vibration-damping foam pad | 1 | 3 mm sticky-back foam | RS | 4.00 | stock | Under FC for IMU isolation |
| 29 | — | Internal harness wire 24 AWG | 5 m | Silicone-jacketed multicolor | RS | 7.00 | stock | FC ↔ peripherals |

**Sub-total: £232.00**

---

## 4. Power

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 30 | `battery_column` | Battery Column Liner | 1 | PETG | Print | 4.00 | print | Slides into Section 3 column slot |
| 31 | `battery_pack` | Li-ion 6S2P 22.2 V 5000 mAh | 1 | Sony VTC6 cells, custom pack | Vruzend / NKON | 95.00 | 2 wk | 18650 ×12, with BMS |
| 32 | `battery_label` | Pack label / serial | 1 | Custom label | — | 0.50 | stock | Cosmetic/cosmetic in CAD only |
| 33 | `esc_pods` | ESC Pods (×2 housings) | 1 | PETG black | Print | 2.50 | print | One print, two pods printed at once |
| 34 | `esc_heatsinks` | ESC Heatsink Fins (×12) | 2 | 6061-T6 aluminium, anodised | McMaster / RS | 12.00 | 1 wk | One fin block per ESC |
| 35 | — | T-Motor F45A 6S BL-Heli32 ESC | 2 | 45 A continuous, 60 A burst | RDQ | 38.00 | 1 wk | One per EDF |
| 36 | — | XT90 power lead w/ anti-spark | 1 | XT90 + 10 AWG silicone, 200 mm | RDQ | 6.50 | stock | Battery → distribution |
| 37 | — | Power distribution board | 1 | Matek FCHUB-6S | RDQ | 16.00 | 1 wk | 10 V / 5 V BECs onboard |

**Sub-total: £198.00**

---

## 5. Propulsion — Upper EDF (Clockwise)

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 38 | `edf_motor_pod_upper` | Motor Pod (CW) | 1 | PETG / PA-CF | Print | 4.00 | print | Houses motor, anchors struts |
| 39 | `edf_motor_struts_upper` | Motor Mount Struts (×4) | 1 | PA-CF (load-bearing) | Print | 3.50 | print | 4 mm × 3 mm cross-section |
| 40 | `edf_blades_upper` | Rotor (×7 blades, CW pitch) | 1 | PA-CF or balanced PETG | Print | 6.00 | print | Hub Ø24, tip Ø136, 18 mm chord |
| 41 | `edf_stators_upper` | Stator Vanes (×11) | 1 | PETG / aluminium | Print | 4.00 | print | Anti-swirl, anchored to duct |
| 42 | `edf_spinner_upper` | Hub Spinner Cap | 1 | PETG accent red | Print | 1.00 | print | M3 collet retention |
| 43 | — | T-Motor MN3110-13 700 KV BLDC | 1 | Brushless out-runner | T-Motor | 124.00 | 3 wk | 720 W cont, prop adapter included |

**Sub-total: £142.50**

---

## 6. Propulsion — Lower EDF (Counter-Clockwise)

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 44 | `edf_motor_pod_lower` | Motor Pod (CCW) | 1 | PETG / PA-CF | Print | 4.00 | print | Same geometry as upper |
| 45 | `edf_motor_struts_lower` | Motor Mount Struts (×4) | 1 | PA-CF | Print | 3.50 | print | |
| 46 | `edf_blades_lower` | Rotor (×7 blades, CCW pitch) | 1 | PA-CF / PETG | Print | 6.00 | print | Mirror twist of #40 |
| 47 | `edf_stators_lower` | Stator Vanes (×11) | 1 | PETG / aluminium | Print | 4.00 | print | Mirror angle of #41 |
| 48 | `edf_spinner_lower` | Hub Spinner Cap | 1 | PETG accent red | Print | 1.00 | print | |
| 49 | — | T-Motor MN3110-13 700 KV BLDC | 1 | Brushless, reverse-wired | T-Motor | 124.00 | 3 wk | Reversed via ESC config |

**Sub-total: £142.50**

---

## 7. Aerodynamic Controls — Canards (×4)

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 50 | `canard_servo_ring` | Servo Mount Ring | 1 | PA-CF | Print | 2.00 | print | Slides into avionics column slot |
| 51 | `canard_servos` | Servo housings (×4 — CAD only) | — | — | — | — | — | Servos themselves are #54 |
| 52 | `canard_pivot_shafts` | Pivot Shafts (×4) | 4 | 4 mm hardened steel rod | RS | 1.50 | stock | M3 thread one end |
| 53 | `canards` | Canard fins (×4) | 4 | PA-CF | Print | 2.00 | print | NACA-0008 trapezoidal, 70 mm span |
| 54 | — | KST X06H 10 mm micro servo | 4 | 0.18 sec/60°, 5.5 kg·cm | KST hobby | 18.00 | 1 wk | All-metal gear, programmable |
| 55 | — | M3 ball-link rod end + linkage | 4 | M3 ball-link, 30 mm rod | KST | 1.50 | stock | Servo arm → fin horn |
| 56 | — | Bearing — 4 mm flanged | 8 | MR104ZZ flanged | SimplyBearings | 0.80 | stock | 2 per fin pivot, ID 4 mm |

**Sub-total: £96.00**

---

## 8. Aerodynamic Controls — Tail Fins (×4)

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 57 | `tail_fin_servo_ring` | Servo Mount Ring | 1 | PA-CF | Print | 2.00 | print | |
| 58 | `tail_fins` | Tail Fins (×4) | 4 | PA-CF | Print | 2.50 | print | Trapezoidal, 60 mm span |
| 59 | `tail_fin_servos` | Servo housings (×4 — CAD) | — | — | — | — | — | Servos themselves are #61 |
| 60 | `tail_fin_pivots` | Pivot Shafts (×4) | 4 | 5 mm hardened steel rod | RS | 1.80 | stock | Wider than canard for stronger fin |
| 61 | — | KST X10 12 mm mini servo | 4 | 0.13 sec/60°, 8 kg·cm | KST | 22.00 | 1 wk | Higher torque for tail authority |
| 62 | — | M3 ball-link + linkage | 4 | M3 ball-link, 25 mm rod | KST | 1.50 | stock | |
| 63 | — | Bearing — 5 mm flanged | 8 | MR105ZZ flanged | SimplyBearings | 1.00 | stock | 2 per fin pivot, ID 5 mm |

**Sub-total: £84.00**

---

## 9. Thrust Vectoring

| # | Part ID | Name | Qty | Material / Part No | Source | Unit £ | Lead | Notes |
|--:|---------|------|---:|-------------------|--------|-------:|-----:|-------|
| 64 | `gimbal_outer_ring` | Outer Pitch Ring | 1 | PA-CF (load-bearing) | Print | 2.50 | print | Ø76 OD, 3 mm tube cross-section |
| 65 | `gimbal_inner_ring` | Inner Yaw Ring | 1 | PA-CF | Print | 2.00 | print | Ø64 OD |
| 66 | `gimbal_pivots` | Pivot Bearings (×4) | 4 | MR62ZZ flanged | SimplyBearings | 1.20 | stock | ID 2, OD 6 mm |
| 67 | `gimbal_actuators` | Linear Actuators (×2) | 2 | KST DS215MG-LA, 25 mm stroke | KST | 32.00 | 2 wk | Pitch + yaw control |
| 68 | `nozzle_bell` | Vectoring Nozzle Bell | 1 | ASA matte (high-temp) | Print | 4.00 | print | de Laval profile, OD 80 → 60 mm |
| 69 | `nozzle_throat` | Nozzle Throat Insert | 1 | Matte black ASA / aluminium | Print or RS | 5.50 | print | Optional aluminium for heat |
| 70 | — | Gimbal pivot pin (M2×8) | 4 | M2 stainless, hardened | RS | 0.30 | stock | One per gimbal pivot |
| 71 | — | Actuator clevis pins | 4 | M2×6, hardened | RS | 0.20 | stock | Both ends of each actuator |
| 72 | — | Wire harness for actuators | 2 | 22 AWG silicone, 200 mm | RDQ | 1.50 | stock | |

**Sub-total: £78.00**

---

## Hardware / Consumables (general)

| # | Description | Qty | Spec | Source | Unit £ | Notes |
|--:|-------------|---:|------|--------|-------:|-------|
| 73 | M3 cap-head, A2 stainless | 50 ea | 6 / 8 / 10 / 12 mm assortment | RS | 0.05 | General fastening |
| 74 | M3 heat-set inserts (brass) | 50 | OD 4.2, L 5 mm | AliExpress | 0.10 | All printed parts threaded points |
| 75 | M3 lock-nuts (nyloc) | 30 | A2 stainless | RS | 0.10 | Vibration-critical joints |
| 76 | M2 cap-head | 20 ea | 4/6/8/10 mm | RS | 0.05 | Servo mounting, gimbal |
| 77 | Threadlocker | 1 | Loctite 243 (medium), 10 mL | RS | 6.50 | All thread joints |
| 78 | Cyanoacrylate adhesive | 1 | Medium viscosity, 50 g | RS | 4.50 | Print bonding (post) |
| 79 | Heat-shrink tubing | 1 | Assortment 1.5–6 mm | RS | 5.00 | Wire terminations |
| 80 | Electrical connectors | 1 | XT60, JST-XH/PH/SH, servo | RDQ | 14.00 | Assorted |
| 81 | Foam tape (vibration) | 1 | 3 mm closed-cell, 10 m roll | RS | 6.50 | Avionics damping |
| 82 | Lock-wire / safety wire | 1 | 0.5 mm stainless, 5 m | RS | 4.00 | Critical fastener safety |
| 83 | Print filament (consumed) | — | PETG/ASA/PA-CF estimated 1.5 kg total | Various | 35.00 | Usage cost across all printed parts |
| 84 | Misc. shrink tubing, cable ties | 1 | Bag | RS | 8.00 | |

**Sub-total: £62.00**

---

## Grand Total

| Item | Cost |
|------|-----:|
| All printed parts (filament cost, included in subsystem totals) | 105.00 |
| All COTS components (motors, servos, electronics, battery) | 855.00 |
| All hardware / fasteners / consumables | 163.50 |
| **Project total** | **£1,123.50** |

**Critical-path lead time**: 3 weeks (T-Motor MN3110 BLDCs).
**Print time estimate**: 84 hours total at 0.2 mm layer / 60 mm/s — split across 5 sections + small parts.
**Assembly time estimate**: 8–12 hours skilled, single technician.
