# Design Document — Drone Rocket Mk II

**Project**: Drone Rocket Mk II — Contra-Rotating EDF Propulsion
**Document version**: 2026-05-03-1
**Status**: Concept / Development

---

## 1. Executive summary

A 1 m tall, 150 mm diameter electric ducted-fan (EDF) drone rocket with full thrust vectoring and aerodynamic control surfaces. Designed for short-duration vertical flight (~3–5 min), tail-sitting takeoff/landing, and as a research platform for compact contra-rotating EDF propulsion.

| Headline spec | Value |
|---------------|-------|
| Height | 1000 mm |
| Body OD | 150 mm |
| AUW (target) | 2.40 kg |
| Thrust (peak, both EDFs) | 4.6 kg-f (1.92 T:W) |
| Endurance @ 50 % throttle hover | ~4 min |
| Battery | 6S 5000 mAh Li-ion (22.2 V, 110 Wh) |
| Build cost | ~£1,124 |

---

## 2. Functional requirements

| ID | Requirement | Target | Verify by |
|----|-------------|--------|-----------|
| F-1 | Vertical takeoff and hover | 30 sec stable hover at 1.5 m | Tethered hover test |
| F-2 | Thrust-to-weight margin | ≥ 1.6 at full charge | Static thrust test |
| F-3 | Thrust vectoring authority | ±15° pitch and yaw | Bench gimbal sweep |
| F-4 | Aerodynamic control authority in forward flight | ±20° canard, ±25° tail fin | Wind-tunnel or CFD validation |
| F-5 | Flight endurance | ≥ 3 min at 50 % throttle | Battery telemetry log |
| F-6 | Telemetry range | ≥ 1 km LoS | Field RSSI test |
| F-7 | All-up weight | ≤ 2.5 kg (regulatory) | Scale |
| F-8 | Manufacturable on 300 mm³ printer | All parts fit | CAD inspection |
| F-9 | Field-serviceable battery | Battery accessible without disassembling propulsion | Service drill |

---

## 3. Architecture overview

The vehicle is a dual-counter-rotating EDF tail-sitter with the avionics/payload arranged in a coaxial central column, leaving an annular duct for unobstructed airflow. Five printable sections stack along Y and join at engineered interfaces.

```
   ┌─────────────────────┐  y=1000  Pitot tube
   │      NOSE CONE       │
   │                      │  y=890
   │  ─── Annular intake ─│  y=820–860 (40 mm gap, 6 struts)
   │                      │
   ├═══════════════════════┤  y=800   Section joint
   │                      │
   │   AVIONICS (FC, GPS,  │
   │   radio, antenna)     │  y=700
   │                      │
   ├═══════════════════════┤  y=600   Section joint
   │                      │
   │   BATTERY +          │  y=500
   │   CANARDS (×4 mid)   │
   │                      │
   ├═══════════════════════┤  y=400   Section joint
   │                      │
   │   UPPER EDF (CW)      │  y=350
   │   Spinner / blades    │
   │   Stators            │  y=395
   │                      │
   │   LOWER EDF (CCW)     │  y=265
   │                      │
   ├═══════════════════════┤  y=200   Section joint
   │                      │
   │   TAIL FINS (×4)      │  y=140
   │                      │
   │   GIMBAL & NOZZLE     │  y=60
   │                      │
   └ ▼ ▼ ▼ exhaust ▼ ▼ ▼ ┘  y=0
```

### Subsystem responsibilities

| Subsystem | Function |
|-----------|----------|
| **Nose & Intake** | Aerodynamic forebody; pitot for airspeed; annular ram/static air ingestion |
| **Structure & Body** | Five-section primary load path; section joints carry bending loads in flight |
| **Avionics** | Flight control, sensing, navigation, telemetry — sealed in central column |
| **Power** | Energy storage in central column; ESC + BEC mounted peripherally for cooling |
| **Propulsion (×2)** | Counter-rotating EDFs cancel torque; centred on body axis |
| **Aero — Canards** | Pitch / yaw authority in forward flight; pre-stall control |
| **Aero — Tail fins** | Roll / pitch / yaw authority near vertical attitude; stabilising surfaces |
| **Thrust vectoring** | ±15° gimballed nozzle for low-airspeed control where aero surfaces are ineffective |

### Why contra-rotating?

Two equal-and-opposite EDFs on the same axis cancel reaction torque — without them, a single EDF would induce a ~12 N·m roll moment that the small fin authority couldn't counter at low airspeed. CRDF arrangement also gives:

- Higher static thrust per swept area (recoverable swirl)
- Reduced exhaust swirl → cleaner signature, less yaw at exit
- Redundancy: degraded but flyable on one EDF in failure mode (with active stabilisation)

---

## 4. Material selection

Material choices are driven by the load and thermal profile of each part:

| Part class | Material | Why |
|------------|----------|-----|
| Body shells (cosmetic, mild structural) | PETG | Tough, easy to print, transparent option for cutaway demo |
| EDF duct | ASA | Heat tolerance to 90 °C continuous (motor heat soak) |
| Nozzle bell, throat | ASA / aluminium insert | Exhaust gas heating — though below combustion, EDF exhaust can hit 65 °C |
| Motor mount struts | PA-CF | Carries full thrust load (~25 N each strut peak); PETG would creep |
| Fan blades | PA-CF (annealed) | Centrifugal stress at root + fatigue cycling |
| Gimbal rings | PA-CF | Bending + torsion under thrust vectoring |
| Canards & tail fins | PA-CF | Aerodynamic load + control linkage moment |
| Servo mount rings | PA-CF | Concentrated load points at servo screws |
| Accent rings, collars | PETG accent red | Cosmetic, no significant load |
| Section joints (bayonet pins) | Hardened steel | Wear surface — printed pins would wallow over re-assembly cycles |

PA-CF is annealed post-print to bring crystallinity to 30 %+ (vs. ~10 % as-printed) — doubles fatigue life.

---

## 5. Mechanical design

### Load paths

In hover (4.6 kg-f thrust opposing 2.4 kg weight):

```
Hub spinner (6 N axial)
   ↓
Motor shaft → motor body (24 N axial + 0.9 N·m torque)
   ↓
Motor pod (24 N axial via four mounting holes)
   ↓
4× Mount struts (6 N each, axial compression)
   ↓
Inner duct ring (24 N distributed around 360°)
   ↓
Body shell (24 N tension/compression along length)
   ↓
Section joints (24 N transferred via 6 bolts each, 4 N per bolt — well within M3 capacity)
   ↓
Tail section / nozzle (reaction)
```

Peak loading occurs during gust response or aggressive thrust vectoring — 1.5× hover thrust assumed. PA-CF strut FoS at 1.5× nominal: 8.

### Joints

| Joint | Type | Capacity |
|-------|------|----------|
| Section interfaces (×4) | Bayonet + 6× M3 bolt + O-ring seal | 850 N axial, 12 N·m bending |
| Motor mount | 4× M3 cap-head into PA-CF strut ends | 360 N pull, well above peak |
| Fin pivot | 5 mm shaft in MR105ZZ flanged bearings | 25 N radial each side |
| Canard pivot | 4 mm shaft in MR104ZZ flanged | 18 N radial each side |
| Gimbal pivot | M2 dowel in MR62ZZ flanged | 8 N radial each side |
| Battery retention | Friction fit + retention clip | Acceleration tolerant to 8 g axial |

### Centre of gravity

Designed CG: y = 480 mm (49 mm aft of geometric centre)

This is intentionally aft of the geometric centre to give natural pitch authority via the canards in forward flight, while remaining within the static-margin envelope for tail-sitter operation. Component placement supports this:

- Battery (1.05 kg) at y = 470 → contributes 49 % of mass weighted at 470
- Both motors (480 g combined) at y = 245 / 380 → contributes 20 % weighted at 313
- Avionics (180 g) at y = 730 → contributes 7 % weighted at 730
- Structure (590 g) distributed along full length → contributes 24 % weighted at ~500

Computed CG: 481 mm — within target.

---

## 6. Electrical design

### Power budget (peak hover)

| Load | Current @ 22.2 V | Power |
|------|----------:|-----:|
| Upper EDF (full throttle) | 32 A | 710 W |
| Lower EDF (full throttle) | 32 A | 710 W |
| FC + GPS + radio (10 V BEC) | 1.0 A @ 10 V | 10 W |
| 8× fin servos (5 V, peak simultaneous) | 8 A @ 5 V | 40 W |
| 2× gimbal actuators (5 V, transient) | 4 A @ 5 V | 20 W |
| **Total** (worst-case simultaneous) | — | 1,490 W |

Battery: 22.2 V × 5 Ah = 111 Wh. Average flight load (50 % throttle, 25 % servo duty) ≈ 720 W → endurance 9.2 min on paper, derate to 4 min with 80 % discharge limit and reserve.

### Wiring conventions

- 10 AWG silicone for battery → distribution board (single-conductor pair, twisted)
- 12 AWG silicone for distribution → ESCs (max 60 A peak)
- 22 AWG silicone for FC → ESC signal, FC → servos
- All flexible silicone insulation (rated 200 °C)
- Servo bus: 4 fins per channel-expander (Pololu Maestro or similar) → 1 PWM line out of FC

### Failure modes considered

| Failure | Effect | Recovery |
|---------|--------|----------|
| Single EDF stop | Roll moment > tail authority below ~30 m/s airspeed | FC: forward-flight transition + RTL |
| Battery cell failure | Voltage drop, cutoff at 18.0 V (3.0 V/cell) | FC: descend immediately at half throttle |
| FC reboot in flight | Servos / ESC arming maintained briefly via passthrough; FC re-arms in ~2 s | Limited recovery; design margin assumes survival |
| Telemetry loss | No flight effect; loiter-on-loss timer 10 s, RTL after | Onboard logging continues |
| GPS lock loss | Position hold degrades to attitude hold | Pilot manual control; RTL on link if both lost |

---

## 7. Aerodynamic design

The vehicle has two flight regimes:

### Hover / vertical flight (airspeed < 5 m/s)

- **Roll**: ESC differential between the two EDFs (residual torque after CR cancellation)
- **Pitch / yaw**: Thrust vectoring nozzle (±15° each axis)
- **Aero surfaces**: Ineffective at this speed; held in trim

### Transition / forward flight (airspeed > 10 m/s)

- **Pitch**: Canards + tail fins differential (canards lead, fins trail)
- **Yaw**: Tail fins differential (rudder action)
- **Roll**: Tail fins + canards combined (aileron action via differential left/right pairs)
- **Thrust vectoring**: De-tuned to ±5° to avoid coupling with aero surfaces

### Transition handling

Tail-sitter transition between vertical and horizontal flight is the highest-risk regime — requires careful tuning. Strategy:

1. Begin at hover, climb to 30 m altitude
2. Pitch nose forward at 5°/sec; thrust vector follows
3. At 35° pitch from vertical, the canards begin to develop authority; FC blends control mix
4. By 60° pitch, aero surfaces dominate; thrust vectoring backs off
5. Forward flight at full horizontal: thrust vectored ±5° max for trim only

Reverse transition (forward flight → hover) is trickier; requires altitude allowance and is best initiated via FC's automated tail-sitter profile.

---

## 8. Aerodynamic intake design

The annular intake at y = 820–860 mm is critical to performance:

- **Free area**: 60 mm tall × ~440 mm circumference, gross area 26,400 mm². Subtract 6 struts × 8 mm width × 60 mm = 2,880 mm² obstruction. Net: 23,520 mm².
- **EDF demand at full throttle**: ~14,000 mm² of equivalent through-flow (per swept area calc)
- **Margin**: 1.68× — clean intake, no pre-stall recirculation expected
- **Diffuser lip**: NACA bellmouth profile inside, smooths flow into the duct
- **Strut profile**: Symmetric airfoil (NACA-0010 equivalent) at 0° angle of incidence, minimising pressure drop

Air enters annularly, accelerates through the diffuser, passes through the central column / battery section (annular flow channel), enters the upper EDF, and is exhausted out the gimballed nozzle.

---

## 9. Thermal management

Heat sources:

- 2× motors at 80 % continuous: ~30 W heat each
- 2× ESCs at full load: ~25 W heat each (efficient)

Heat sinks:

- Motors are bathed in the air stream — convective cooling effective, no concern
- ESCs sit in Section 4 peripherally with finned heat sinks; air passes through the duct on either side

Predicted ESC temperature rise above ambient at full load: 18 °C (within 105 °C component rating margin).

Battery generates ~10 W heat at 50 % discharge rate; airflow past the battery column keeps it under 40 °C ambient + 15 °C rise = OK.

---

## 10. Manufacturing & DfM

See [`manufacturing-plan.md`](manufacturing-plan.md) for full detail. Key DfM decisions:

- Five-section split keeps every part within 200 mm Z range — fits any modern hobby printer
- Section interfaces are bayonet + bolt — tool-free disassembly with one Allen key
- All threaded points use M3 brass heat-set inserts — robust, repeatable assembly cycles
- No support material required for any "as printed" part (every overhang is below 45° or is internal to print orientation)
- Custom geometry (fan blades, stators) printed flat — best layer-line orientation for centrifugal load

---

## 11. Open questions & risks

| # | Issue | Status | Owner |
|---|-------|--------|-------|
| OQ-1 | Final ESC firmware tuning for contra-rotating pair | Pending bench test | Power lead |
| OQ-2 | Validate 1 km telemetry range with antenna in this position (close to body) | Field test required | Avionics |
| OQ-3 | Static thrust measurement vs. design target | Bench test required | Propulsion |
| OQ-4 | Resonance check of full assembly — is the 6× strut intake structurally rigid at 100 Hz? | FEA or shake test | Structure |
| OQ-5 | Exact battery pack dimensions (custom 6S2P 18650) — verify 38×38×110 mm fits | Awaiting pack vendor sample | Power |
| OQ-6 | Wing/fin flutter speeds — PA-CF panels at 30 m/s? | CFD or wind-tunnel | Aero |

### Risk register

| Risk | Severity | Mitigation |
|------|---------:|------------|
| Crash during transition flight | High | Tether tests; gradual envelope expansion; FC failsafe behaviours |
| Section joint failure under bending | High | 6-bolt + bayonet redundancy; FoS 4× |
| Rotor blade departure | Critical | PA-CF + annealing; spin-test to 110 % rated; spinner cap thread-locked |
| Battery thermal incident | Critical | Quality cells; BMS; thermal fuse; pack swelling sensor |
| Telemetry loss → fly-away | Medium | Loiter-on-loss + RTL on extended loss; GPS-aware failsafe |

---

## 12. Future iterations

The Mk II is Concept-level. Planned Mk III improvements:

- Larger nose intake area (30 % more) for higher static thrust margin
- Composite lay-up of body shells (vacuum bagged carbon) — 40 % weight saving
- Integrated rocket-style payload bay between avionics and battery
- Switch to 21700 cells for 25 % more capacity in same volume
- Drogue chute deployment for emergency recovery
- Exterior antenna fairing for full GPS / telemetry diversity

---

## Appendix A — Coordinate system

- **Origin (0,0,0)**: Centre of nozzle exit plane (ground when standing)
- **+Y axis**: Up (toward nose)
- **+X axis**: Right (looking from nose to tail along -Y)
- **+Z axis**: Forward (nominal forward-flight direction in transition)
- **All dimensions**: millimetres unless stated
- **All angles**: degrees unless stated, positive = right-hand rule about the relevant axis

## Appendix B — Material data

| Material | Yield | UTS | Modulus | Density | Tg / HDT | Cost (£/kg) |
|----------|-----:|----:|--------:|--------:|---------:|------------:|
| PETG | 50 MPa | 53 MPa | 2.1 GPa | 1.27 g/cc | 80 °C | 22 |
| ASA | 45 MPa | 49 MPa | 2.0 GPa | 1.07 g/cc | 96 °C | 30 |
| PA-CF (annealed) | 90 MPa | 110 MPa | 7.5 GPa | 1.18 g/cc | 180 °C | 65 |
| 6061-T6 Al | 276 MPa | 310 MPa | 69 GPa | 2.70 g/cc | 200 °C | 8 |

## Appendix C — Drawings

See [`drawings/`](drawings/) directory:

- [01-front-elevation.svg](drawings/01-front-elevation.svg) — primary external view, all key dimensions
- [02-section-view.svg](drawings/02-section-view.svg) — cutaway through centre line, internal layout
- [03-plan-view.svg](drawings/03-plan-view.svg) — top-down looking through annular intake
- [04-bottom-view.svg](drawings/04-bottom-view.svg) — view from below, tail fins + nozzle
- [05-exploded-isometric.svg](drawings/05-exploded-isometric.svg) — exploded view showing all printable sections
- [06-edf-detail.svg](drawings/06-edf-detail.svg) — detail of contra-rotating EDF assembly
