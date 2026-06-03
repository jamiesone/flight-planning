# Airspace Types in Switzerland 

**Sources:** Swiss AIP ENR 2.1, ENR 5.1, ENR 5.2, BAZL PRD-Richtlinie LR I-004 D, SHV/FSVL Airspace documentation  

---

## Overview

Airspace types describe the **purpose and geometry** of a defined volume of airspace, independently of its class. A CTR (Control Zone) is always Class D in Switzerland, but a Restricted Area (LS-R) can overlay any class. Understanding types tells you *why* an airspace exists and what rules govern entry — class tells you *how* to communicate and separate.

For balloon pilots, the most operationally significant types are: **CTR, RMZ, TMZ, LS-R, LS-D, and LS-P**.

---

## CTR — Control Zone

**Class in Switzerland:** D  
**Geometry:** Polygon from surface (SFC) to a defined upper limit  
**Purpose:** Protects the immediate vicinity of an aerodrome and its arriving/departing traffic  
**Activation:** Permanent (during aerodrome operating hours); check AIP for hours outside which CTR may be inactive (Class G applies)

**Examples in Switzerland:**  
- LSZB CTR (Bern-Belp): SFC – 1,500m AMSL  
- LSZA CTR (Lugano): SFC – 1,220m AMSL  
- LSGS CTR (Sion): SFC – 1,830m AMSL  
- LSZR CTR (St. Gallen-Altenrhein): SFC – 915m AMSL

**Rules for balloons:** ATC clearance required before entry (Class D). Contact the aerodrome's approach/tower frequency. If the CTR is inactive (outside hours), it reverts to Class G — no clearance required, but check DABS for any NOTAM.

**Practical note:** Balloon launch sites in valley floors near airports are frequently inside or adjacent to CTRs. The Rhône valley (Sion CTR), the Bern plateau (Bern-Belp CTR), and the Rhine valley (Altenrhein CTR) are typical examples where a balloon pilot must confirm clearance before launch.

---

## TMA — Terminal Maneuvering Area

**Class in Switzerland:** C or D depending on sector  
**Geometry:** Polygon with a defined lower limit (not SFC) up to an upper limit  
**Purpose:** Protects the structured arrival and departure routes above a CTR  
**Activation:** Permanent

**Examples:**  
- Zurich TMA (multiple sectors, Class C, lower limits from 1,500ft to FL100)  
- Geneva TMA (Class C, lower limits vary by sector)

**Rules for balloons:** Same as Class C or D as applicable. TMA lower limits are often well above typical balloon cruise altitude, but must be checked for the specific sector over the flight area. A balloon climbing above the TMA base in a Zurich or Geneva sector requires Class C clearance.

---

## RMZ — Radio Mandatory Zone

**Class:** Overlay on any class (usually E or G)  
**Geometry:** Defined polygon and altitude band  
**Purpose:** Ensures radio contact in busy but uncontrolled airspace, particularly around regional aerodromes that do not have a full CTR  
**Activation:** Permanent during published hours

**Examples:**  
- RMZ Bern Information (around Bern area where Class G/E exists)  
- RMZ around several regional aerodromes (Grenchen, Lausanne, Buochs when CTR inactive)

**Rules for balloons:** Two-way radio communication on the published frequency is mandatory before entering and while within the RMZ. The pilot must make a position report. No clearance is required — this is not controlled airspace — but radio contact is legally required.

**Practical note:** Balloons without a radio cannot legally enter an RMZ. This is a common compliance issue for free-flight aircraft. The SHV/FSVL airspace API marks zones with RMZ type — these must be flagged as requiring radio equipment.

---

## TMZ — Transponder Mandatory Zone

**Class:** Overlay on any class (usually E or G)  
**Geometry:** Defined polygon and altitude band  
**Purpose:** Ensures radar visibility of aircraft in airspace with significant IFR/VFR mixing  
**Activation:** Permanent

**Rules for balloons:** A functioning Mode S transponder (with altitude reporting) must be operated when inside a TMZ. Squawk 7000 with altitude mode unless instructed otherwise by ATC.

**Practical note:** Many areas that were previously Class D CTRs have been converted to RMZ/TMZ combinations. Combined RMZ-TMZ zones require both radio and transponder. This is increasingly common in Switzerland as airspace is reorganised. The SHV/FSVL API encodes both RMZ and TMZ flags per zone — check both.

---

## LS-R — Restricted Area

**Geometry:** Polygon with defined lower and upper limits  
**Purpose:** Flight is restricted (not prohibited) for reasons of military activity, sensitive installations, or other operational requirements  
**Activation:** Can be permanent, DABS-activated, or HX (activated at any time without prior notice)

**Examples:**  
- LS-R10 (Sion military area)  
- LS-R25 (Meiringen military area)  
- Various TRA (Temporary Reserved Areas) used for military exercises

**Rules for balloons:** Entry not permitted when active unless specific clearance is obtained from the controlling authority. When the area is inactive, normal Class E or G rules apply.

**Critical flag — HX:** Areas marked HX can be activated at any time without prior notice, including during a flight already in progress. These must be treated as always potentially active. The SHV/FSVL API provides the `HX` boolean flag per zone.

**DABS activation:** Many LS-R areas are activated via the Daily Airspace Bulletin (DABS), published at 16:00 LT for the following day. Always check the DABS before flight. An LS-R zone not listed in the DABS is inactive and may be transited under normal rules.

---

## LS-D — Danger Area

**Geometry:** Polygon with defined lower and upper limits  
**Purpose:** Marks areas where activities dangerous to aircraft may exist (military weapons ranges, firing ranges, parachute drop zones)  
**Activation:** Scheduled or DABS-activated

**Rules for balloons:** Entry is not prohibited but is strongly discouraged when active. A balloon drifting into an active LS-D has no ability to manoeuvre horizontally and should be treated as a no-go zone. Check DABS for activation status.

---

## LS-P — Prohibited Area

**Geometry:** Polygon with defined lower and upper limits  
**Purpose:** Flight is absolutely prohibited (nuclear installations, certain government facilities)  
**Activation:** Permanent

**Rules for balloons:** No entry under any circumstances. These are rare and typically small in Switzerland.

---



## Airspace Type Summary for Balloon Planning

| Type | Entry requirement | Radio | Transponder | Check DABS |
|------|------------------|-------|-------------|------------|
| CTR (Class D) | ATC clearance | Required | Required | For hours |
| TMA (Class C/D) | ATC clearance | Required | Required | No |
| RMZ | Position report only | Required | Not required* | No |
| TMZ | None | Not required* | Required | No |
| RMZ+TMZ | Position report | Required | Required | No |
| LS-R | Not permitted when active | — | — | Yes |
| LS-D | Strongly avoid when active | — | — | Yes |
| LS-P | Prohibited | — | — | Permanent |
| LS-W | Min altitude applies | — | — | Seasonal |

*Unless also overlaid with the other zone type

---


