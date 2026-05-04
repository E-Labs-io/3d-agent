# Drone Rocket Mk II — Deliverables Package

**Version**: 2026-05-03-1
**Status**: Concept / Development build pack

This package contains everything you need to take the Drone Rocket Mk II from CAD to a finished, flight-ready vehicle.

---

## Contents

| File | What it covers | Size |
|------|----------------|-----:|
| [`design-document.md`](design-document.md) | **Engineering design rationale.** Functional requirements, architecture, material selection, mechanical & electrical design, aerodynamics, thermal, risk register, open questions. | ~14 KB |
| [`BOM.md`](BOM.md) | **Bill of Materials.** 84 line items across 9 subsystems, with materials, vendor part numbers, costs, lead times, and grand total. | ~12 KB |
| [`manufacturing-plan.md`](manufacturing-plan.md) | **Manufacturing & print plan.** Print sections, settings per material, sequence, quality control, tooling list, risk register. | ~10 KB |
| [`assembly-instructions.md`](assembly-instructions.md) | **Step-by-step build manual.** 11 stages, ~9 hours hands-on work, with pre-flight + maintenance schedule. | ~12 KB |
| [`drawings/01-front-elevation.svg`](drawings/01-front-elevation.svg) | Front orthographic view at 1:5 scale, all key dimensions | |
| [`drawings/02-section-view.svg`](drawings/02-section-view.svg) | Cutaway section through Y axis showing internal layout | |
| [`drawings/03-plan-view.svg`](drawings/03-plan-view.svg) | Top-down view through annular intake, struts and column visible | |
| [`drawings/04-bottom-view.svg`](drawings/04-bottom-view.svg) | View from below showing tail fins, gimbal, nozzle | |
| [`drawings/05-exploded-isometric.svg`](drawings/05-exploded-isometric.svg) | Exploded view of all 5 sections + sub-assemblies, with build-order callouts | |
| [`drawings/06-edf-detail.svg`](drawings/06-edf-detail.svg) | Detailed view of contra-rotating EDF stage (cross-section + part details) | |

---

## Stakeholder summary

A **1 m tall, 150 mm diameter, 2.4 kg electric drone rocket** with two stacked counter-rotating EDFs, full thrust vectoring, and 8 control surfaces.

| Headline spec | Value |
|---------------|-------|
| Total height | 1000 mm |
| Body diameter | 150 mm |
| All-up weight | 2.40 kg target |
| Combined thrust | 4.6 kg-f (T:W = 1.92) |
| Endurance | ~4 min @ 50 % hover throttle |
| Battery | 22.2 V 5000 mAh (110 Wh) |
| Build cost | £1,124 |
| Print volume needed | 300 × 300 × 300 mm |
| Total print time | ~84 h |
| Total assembly time | 8–12 h |
| Lead-time gating part | T-Motor MN3110 BLDCs (3 weeks) |

The vehicle is intended as a **research platform** for compact contra-rotating EDF propulsion in tail-sitter VTOL configuration. Live-CAD work is captured in [`scene/current.json`](../../scene/current.json) and the project's CAD viewer at [`http://localhost:3030`](http://localhost:3030) (start with `npm start`).

---

## How to read this package

### If you're a builder…

1. Skim [`design-document.md`](design-document.md) for context (10 min)
2. Read [`BOM.md`](BOM.md) and place orders. Lead-time gate is the BLDC motors — order early.
3. Print parts per [`manufacturing-plan.md`](manufacturing-plan.md). Total ~84 h on a single printer; split across multiple to compress.
4. Build per [`assembly-instructions.md`](assembly-instructions.md), referring to [`drawings/`](drawings/) as needed.

### If you're a stakeholder…

Skim the headline specs above + Section 1 of [`design-document.md`](design-document.md) (Executive Summary). For risks and open questions, see Section 11 of the design document.

### If you're an engineer reviewing…

[`design-document.md`](design-document.md) is the technical heart. Key sections:
- §3 Architecture — block-level decomposition
- §5 Mechanical design — load paths, joints, CG calc
- §6 Electrical — power budget, signal flow
- §7 Aerodynamic design — flight regimes, transition handling
- §11 Open questions — what we don't know yet

[`drawings/06-edf-detail.svg`](drawings/06-edf-detail.svg) is the most informationally dense single drawing — it covers the propulsion system end-to-end.

---

## Design philosophy

This is a **DfM-first** design. Every part is sized and oriented to print on a 300 mm³ hobby-grade printer in a single piece, and every joint is engineered to be assembled and disassembled by hand without specialised tooling.

The five-section split is deliberate — not the minimum number of parts, but the optimal compromise between:

- **Print volume**: each section ≤ 200 mm tall (well within bed limits)
- **Maintenance**: failures are likely subsystem-local; sections come apart for repair
- **Strength**: section interfaces are at non-load-bearing transitions
- **Visual coherence**: red accent rings double as service markers and as a styling cue

Material choice follows the principle of *use the cheapest material that meets the load + thermal duty cycle*:
- PETG for cosmetic and mild-structural parts (most of the body)
- ASA for heat-tolerant zones (EDF duct, nozzle bell)
- PA-CF for fatigue-loaded parts (motor struts, fan blades, gimbal, fin mounts)

---

## Versioning & change log

| Version | Date | Notes |
|---------|------|-------|
| 2026-05-03-1 | 2026-05-03 | Initial release of full deliverables pack |

When the live CAD scene changes, regenerate the affected deliverables:
- Geometry change → re-run BOM cross-check, regenerate affected drawings
- Material change → update §4 of design doc, BOM material column, manufacturing plan §2
- Subsystem add/remove → all four documents
- Kept under version control; semantic version bump in this README

---

## Open questions (status snapshot)

These need resolution before flight. See [`design-document.md`](design-document.md) §11 for full context.

| ID | Issue | Status | Owner |
|---|-------|--------|-------|
| OQ-1 | Final ESC firmware tuning | Pending bench test | Power lead |
| OQ-2 | Validate 1 km telemetry range | Field test required | Avionics |
| OQ-3 | Static thrust test vs target | Bench test required | Propulsion |
| OQ-4 | Resonance check of intake struts | FEA / shake test | Structure |
| OQ-5 | Battery pack final dimensions | Awaiting vendor | Power |
| OQ-6 | Fin flutter speeds | CFD / wind tunnel | Aero |

---

## Contact / handoff

This pack is generated by the **3D Agent Manager**, drawing on briefs from the **Engineer / Designer** and the live CAD model maintained by the **3D Specialist**. To request changes:

| Type of change | Talk to |
|----------------|---------|
| Re-engineer (new requirement, material, mechanism) | Engineer / Designer |
| Re-model in 3D / iterate / adjust dimensions | 3D Specialist |
| Update BOM, drawings, instructions, summaries | Manager (this pack) |

Live CAD: `scene/current.json` → viewer at `http://localhost:3030`.
