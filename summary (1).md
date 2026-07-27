# Handoff summary — Sumobot firmware session

Session date: 27 July 2026. Written for another agent picking this up cold.

---

## 1. Context

Sai is a UNSW student competing in **UNSW Sumobots 2026, Opens stream**. Organiser and budget assessor is **Aneesa**.

**Qualifiers: Mon 27 and Tue 28 July 2026, 5:30–8:30 pm, Ainsworth 101/201.** Ticketed separately per night — it was never established which night Sai is entered for, so the deadline may be the evening of this session or the next. All streams must qualify to enter knockouts; results affect seeding.

**Critical status: the robot is still being built.** As of this session: encoders not wired, nothing tested on hardware, no confirmed access to a practice ring, shell and baseplate at an external printer. Assume nothing has been validated unless Sai says so.

### Robot

UFO-shaped differential-drive wedge bot. Exponential-ramp shell acts as a near-zero-clearance wedge to slide under opponents and lift their wheels. Low-friction skid hull; drive wheels carry most of the weight.

- **MCU:** Raspberry Pi Pico 2 (RP2350), MicroPython
- **Motors:** 2× DFRobot FIT0186 (12 V, encoders built in, on the motor shaft ahead of the gearbox)
- **Driver:** DFRobot DRI0041 (2×7 A)
- **Battery:** 3S 11.1 V 1300 mAh LiPo, XT60
- **Sensors for qualifiers:** 2× RCWL-1601 ultrasonic, front and rear. **No IR line sensors** (time constraint; mounting features printed for later)
- **Fuse:** 7.5 A blade, inline
- **Wheels:** 65 mm, ~63.5 mm loaded
- **Mass:** ~1250 g worst case, cap is 1500 g
- **Budget:** ~$199.31 of $200 inc-GST — roughly 69 cents of headroom

### Rulebook facts that drive design

- **3.4** — 100 cm clearance mandated around the ring. This is load-bearing: it means nothing but the opponent can echo inside 1 m, which is what makes ultrasonic-only viable.
- **1.5.1(c)** — 5 s without movement loses the round.
- **1.4.3 / 1.6.2c** — must wait 5 s after the start call; early movement is a minor violation, two of which gift a round.
- **5.2 / 1.8.2** — a triggered fuse is an "accident", and the causing team loses **the match**, not the round. This is why soft-start and duty caps are non-negotiable.
- **1.5.4(c)** — if both bots fall off and the order is unclear, the round is rematched.
- **1.5.3(a)** — technical merit in movement and operation is the first judging criterion. A bot that moves and searches scores; a stationary one does not.
- **2.6** — free 3D printing in PLA or PETG only.
- Ring: 1150 mm black playing surface, 25 mm white border, 1200 mm outer.

---

## 2. Files produced this session

All are drafts. **None has been run on hardware.**

| File | Purpose | Status |
|---|---|---|
| `plan.md` | Strategy, match procedure, rules mapping, tuning constants | Complete |
| `main.py` | Full firmware — state machine, drive layer, sonar layer | Written, untested, **has known defects, see §4** |
| `README.md` | Setup, flashing, calibration, start/stop procedure | Complete |
| `bringup.py` | 12-stage hardware verification script, menu-driven | Written, untested |
| `motortest.py` | Sai's own motor test, cleaned and patched | Verified ASCII-clean, untested |

---

## 3. THE BLOCKING ISSUE — motor driver interface mismatch

**This must be resolved before anything else. It is unresolved as of session end.**

`main.py` and `bringup.py` assume a **two-pin-per-motor** interface:

```
GP16 left PWM, GP17 left DIR, GP18 right PWM, GP19 right DIR
```

Sai's own `motortest.py` uses a **three-pin-per-motor** interface:

```
ENA=21, IN1=20, IN2=19   (motor 1)
ENB=18, IN3=17, IN4=16   (motor 2)
```

Both the interface style and the pin numbers conflict. GP19 is a direction pin in one and IN2 in the other; GP18 is a PWM in one and ENB in the other.

Sai wrote the three-pin version referencing the DRI0041's P1 header, which suggests **the three-pin version is correct and `main.py` is wrong**. If so:

- `Drive._apply()` in `main.py` §4 needs rewriting to drive three pins per channel
- The pin map in `main.py` §1 and `bringup.py` CONFIG both need updating
- `bringup.py` T7 (driver signal test) needs its prompts updated

Confirm against the actual DRI0041 wiring before changing anything. This is the difference between a working bot and one that does nothing.

---

## 4. Known defects in `main.py`

Identified late in the session, **not yet applied to the file**:

**a. `COMMIT_MS = 400` is far too short.** At contact the opponent is inside the sonar's ~20 mm blind zone, so a sustained push routes through the COMMIT state — which then abandons after 400 ms. Against a heavy stationary bot that is nowhere near enough. Change to `1500`. The budget calculation already inside `st_commit()` then becomes the binding constraint, which is correct.

**b. `ROUND_BUDGET_MM` never actually bites.** `reset_travel()` is called on entry to APPROACH, so `drive.travel_mm` resets and the round-level budget is never reached. Fix: add `self.total_mm = 0` to `Drive.__init__`, accumulate it alongside `travel_mm` in `_integrate()`, clear it only in `st_armed()`, and test against `total_mm` for all round-budget checks.

**c. Stall detection cannot distinguish success from failure.** A constant range at contact means either "pushing them successfully, both moving" or "pushing and going nowhere." Without encoders these are genuinely indistinguishable — this is the one place their absence costs something real. Mitigation: raise `STALL_WINDOW_MS` to `2000` and let `ENGAGE_MAX_MS` (2500 ms) do the work. Wasting 2.5 s on a true stall is cheap; breaking off a winning push is not.

**d. Boot escape not yet added.** `main.py` starts a watchdog and never returns. Once saved as `main.py` on the board, Ctrl-C stops the loop, nothing feeds the WDT, and the board resets into `main.py` again — an unrecoverable loop requiring `flash_nuke.uf2`. Add before the `WDT()` line in `Bot.run()`:

```python
if _button.value() == 0:
    _led.value(1)
    raise SystemExit("safe boot")
```

**This should be added before `main.py` ever goes on the board.**

---

## 5. Strategy — the reasoning, condensed

### The core doctrine

**The bot never translates forward unless it has a confirmed echo in front of it, and forward travel is bounded by that echo's range.** Searching is pure rotation, which cannot move the CG off the ring. The opponent becomes the ring model: they are demonstrably on the ring, so travelling toward them and stopping short is safe.

This exists because without IR there is **no absolute edge reference**. Rule 3.4's mandated clearance means the front sonar returns no echo whenever nothing is in front — including when pointed off the table — so ultrasonic cannot localise the bot.

### Four-layer edge safety

1. Search is rotation only (does most of the work)
2. Forward allowance = last echo − 60 mm standoff; no echo → no translation
3. Independent distance budget: 500 mm per approach, 700 mm net per round
4. Always retreat after a dropout resolves — never stop where the edge is

### The dropout ambiguity

Echo loss at contact does **not** mean the opponent is gone. The RCWL-1601 returns nothing below ~20 mm, so a timeout may mean "pressed against the ramp" or "riding up the wedge." Disambiguated by range trend:

- Falling then timeout at short range → they are on the ramp → **COMMIT** (keep pushing)
- Rising then timeout → they separated → over the line → **RETREAT**

Dropout is tested as a *delta* (>250 mm jump), not a threshold, because the ring is 1150 mm across and an absolute threshold would fire on a legitimate long-range target.

### In-match speed calibration

Against a **stationary** opponent, change in measured range equals our own displacement. `st_approach()` uses this to calibrate `SPEED_MM_S` live during the first approach of every round. This removes the dependency on pre-event ring time. **It stops working against a moving opponent**, so it is a qualifier-only technique.

### Leaving the ring after a win

Nothing in the rules requires staying on. But stop anyway: 1.5.4(c) turns a clean win into a rematch if the fall order is unclear, and 5.2/1.8.2 make going off the table an accident that loses the whole match. Asymmetry favours stopping.

### Mass

The Opens cap is 1.5 kg for everyone, so the worst case gap is 1.2:1, not 2:1. A metal opponent is compact and low (harder); a wood one is bulky with a high CG (easier). The wedge is the counter — once under them their weight transfers to our drive wheels, so their traction goes to zero and ours rises.

**Open action:** check FIT0186 stall torque against ~1.6 kg·cm per wheel at 32.5 mm radius. If traction-limited, ballast over the axle to ~1450 g is worth ~20% more thrust. If torque-limited, ballast does nothing. Ballast must be added to the parts list for Aneesa.

---

## 6. Encoders — correction made mid-session

Sai pointed out, correctly, that the **FIT0186 has encoders built in**. Earlier statements that "encoders are not wired" meant the four signal lines to the Pico do not exist yet, not that hardware was missing. The CE07510 level shifter is in the BOM precisely because the encoder outputs are 5 V and Pico GPIO is 3.3 V.

**Concern before wiring them: MicroPython interrupt rate.** The encoder sits on the motor shaft ahead of the gearbox, so tick rate is multiplied by the gear ratio. MicroPython pin IRQ handlers cost tens of microseconds; past a few kHz the main loop starves and the watchdog resets mid-round. `bringup.py` T11 measures this — under 2500 Hz is fine, over 6000 Hz needs PIO or omission.

**Recommended scheme if used:** count channel A only, rising edges only (a quarter of full quadrature rate), and sign the count from the commanded direction.

**Worth testing first:** power the encoder from 3.3 V rather than 5 V. If it still pulses cleanly, the level shifter leaves the circuit entirely.

**What encoders buy:** straight-line tracking (the most underrated — open-loop differential drive veers over a 500 mm approach), real odometry replacing the duty-based estimate, exact rotation angles (deleting `ROT_MS_PER_DEG`), and torque-stall detection. They do **not** detect traction slip and are **not** a substitute for line sensors on edge safety.

**Recommendation given:** leave them out if qualifying tonight. Wire tomorrow morning with a hard noon cutoff if qualifying Tuesday.

---

## 7. Tuning priorities

**Tier 1, must measure:**
- `INVERT_LEFT` / `INVERT_RIGHT` — from `selftest()` on blocks
- `ROT_MS_PER_DEG` — time 10 revolutions ÷ 3600. Currently a guess at 8. Breakoff's re-attack angle depends entirely on it.
- `DEADBAND_DUTY` — step duty up by 5 until wheels start from rest

**Tier 2:** `SPEED_MM_S` (self-calibrates, seed only needs to be close), `STANDOFF_MM` / `CONTACT_MM` (geometry — verify 100 mm corresponds to the wedge tip reaching them, since the sensor sits partway up the ramp)

**Do not touch:** `BRAKE_MS` (driver requirement), `ECHO_TIMEOUT_US` (derived from rule 3.4), `RAMP_MS` (fuse protection), `T_START_DELAY_MS` (rule 1.4.3)

## 8. Test protocol

- **Stage 0** — sonar on breadboard: sensible mm close, `-1` past ~1 m. *The timeout is the feature.*
- **Stage 1** — motors on blocks via `selftest()` or `motortest.py`
- **Stage 2** — rotation on open floor; measure `ROT_MS_PER_DEG` here
- **Stage 3** — weighted cardboard box as a target
- **Stage 4** — **tape a 1150 mm circle on the floor** (string at 575 mm from a centre pin). Full rounds, zero fall risk. Pass: five rounds without crossing the tape. This is the highest-value test available and costs nothing.
- **Stage 5** — real ring if one materialises

Run stage 4 **on battery, not USB** — behaviour at 11.8 V is not behaviour at 10.9 V.

Set `DEBUG = True` while testing, tethered. **`DEBUG = False` before the match** — USB writes block once the buffer fills with no host attached, which hangs the loop and trips the watchdog.

---

## 9. Toolchain state

Sai is on a MacBook. As of session end:

- Homebrew **not installed** (`zsh: command not found: brew`)
- `mpremote` not installed
- Recommended fallback: `python3 -m venv ~/mpy && ~/mpy/bin/pip install mpremote`, or skip the CLI entirely and use **Thonny**, which does everything needed here
- `pip3 install` will not work — macOS ships an externally-managed Python

**Note:** I incorrectly told Sai the Pico 2 has USB-C. It is **micro-USB**. Charge-only micro-USB cables are a common cause of an apparently dead board.

**Error encountered:** `NameError: name '' isn't defined` — an invisible Unicode character (zero-width space or non-breaking space) picked up from copying formatted text out of the chat window. Fixed by delivering the file as a download instead. **Deliver code as files, not chat text, for this user.**

---

## 10. Open actions

1. **Resolve the 2-pin vs 3-pin driver mismatch** (§3) — blocking
2. Apply the four defect fixes in §4, especially the boot escape
3. Run `bringup.py` T1–T6 (no motors needed) and T7 (motors disconnected)
4. Confirm DRI0041 pin 13 sits at 3.3 V — silent failure mode, most common way to lose an evening
5. Measure `ROT_MS_PER_DEG`
6. Check FIT0186 stall torque to decide on ballast
7. Confirm start-position numbering against the physical ring
8. Ask Aneesa: exact moment a win is called under 1.5.1(a); whether ballast needs a parts-list line; inc-GST vs ex-GST budget basis (carried over from before this session)
9. Tape the 1150 mm test circle

---

## 11. Working style

- Prefers direct numerical answers with brief reasoning, not lengthy derivations
- Corrects misreads quickly and concisely; iterates in tight loops, one constraint at a time
- External communications should be concise, warm, casual — no em dashes, no AI-sounding phrasing
- Building a GitHub repo for this; wanted a short description with no em dashes
- **Deliver code as downloadable files, not pasted into chat** (see §9)
