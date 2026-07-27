# Sumobot firmware - ADAM SMASHERS
# UNSW Sumobots 2026, Opens stream. Raspberry Pi Pico 2 (RP2350), MicroPython.
#
# ============================================================================
# WHAT THIS IS
# ============================================================================
# Full autonomous firmware: search by rotating, drive only toward a confirmed
# ultrasonic echo, push, and always retreat after losing contact so we never
# stop sitting on the ring edge. There are no line sensors, so the opponent is
# our only reference for "where the ring is": they are demonstrably on the
# table, so driving toward them and stopping short is the safe move.
#
# ============================================================================
# CURRENT HARDWARE STATE (read before running)
# ============================================================================
#   - Encoders are NOT wired. Odometry is estimated from the sonar range
#     change (against a stationary target this equals our own displacement),
#     with a duty/time fallback while the echo is lost. It is an estimate.
#   - There is NO start button. The match auto-starts on Run after a 5 second
#     countdown (satisfies rule 1.4.3), and auto-stops after RUNTIME_CAP_MS.
#   - There is NO watchdog. That is deliberate: with no button there is no safe
#     way to break a watchdog boot loop. See the marked spot below to add it
#     once a button exists. In Thonny, the red Stop button (Ctrl-C) always
#     stops the bot.
#
# ============================================================================
# WIRING
# ============================================================================
#   Motor driver DRI0041 (P1 header, 3 pins per motor):
#     Motor 1  ENA=GP21  IN1=GP20  IN2=GP19
#     Motor 2  ENB=GP18  IN3=GP17  IN4=GP16
#   Ultrasonic RCWL-1601 (3.3 V logic, no level shifter):
#     Front  Trig=GP14  Echo=GP15   Rear  Trig=GP12  Echo=GP13
#
# ============================================================================
# HOW TO TEST  (do these in order, do not skip ahead)
# ============================================================================
# Keep DEBUG = True for all bench testing so you can watch the state machine.
#
#   TEST 0  Sonar sanity (already covered by ultrasonictest.py). Confirm both
#           sensors read sensible mm and go "no echo" past ~1 m.
#
#   TEST 1  WHEELS OFF THE GROUND, USB tethered, motors powered.
#           Press Run. Watch the shell.
#           - Confirm the 5 s countdown, LED blinking.
#           - It should enter SEARCH and both wheels should spin so the bot
#             would rotate in place (one wheel forward, one back).
#           - Put a hand ~30-50 cm in front of the FRONT sensor. State should
#             switch to APPROACH and both wheels should spin forward.
#           - Move the hand in to ~8-10 cm. State should reach ENGAGE.
#           - Take the hand away quickly. It should RETREAT (wheels reverse
#             briefly) then go back to SEARCH.
#           - Present a target only to the REAR sensor while the front is
#             empty. It should REACQUIRE (keep rotating to bring it round).
#           - Confirm it stops itself at 30 s (DONE, LED solid).
#
#   TEST 2  Fix direction. On the "forward" push note which way each wheel
#           actually turns. If a wheel spins backward, flip its INVERT flag
#           below. If the bot would rotate the wrong way in SEARCH, swap which
#           motor is LEFT vs RIGHT (or flip both inverts).
#
#   TEST 3  Only once TEST 1 and 2 pass: wheels on the ground, on battery,
#           against a weighted box. Then tape a 1150 mm circle and run full
#           rounds. Never test edge behaviour near a real drop until the taped
#           circle looks safe.
#
# WHAT TO LOOK OUT FOR
#   - If a wheel does not move at all, DEADBAND_DUTY may be too low.
#   - If the bot creeps during the 5 s countdown, a motor is not being held
#     stopped: check wiring, do not run on the ground.
#   - Jerky or buzzing start: RAMP_MS too short (soft-start protects the fuse).
#   - Never leave DEBUG = True for a real match: with no USB host attached the
#     print buffer fills and blocks the loop. Set DEBUG = False before a match.
# ============================================================================

from machine import Pin, PWM, time_pulse_us
import time

# ---------------------------------------------------------------------------
# DEBUG: True while tethered on the bench. MUST be False for a real match.
# ---------------------------------------------------------------------------
DEBUG = True

# ===========================================================================
# CONFIG - pins
# ===========================================================================
# Motor 1
ENA, IN1, IN2 = 21, 20, 19
# Motor 2
ENB, IN3, IN4 = 18, 17, 16

# Which physical side each motor is. Swap these two lines if SEARCH rotates
# the wrong way (TEST 2).
LEFT_MOTOR  = "M1"
RIGHT_MOTOR = "M2"

# Flip a flag if that wheel spins backward on the "forward" push (TEST 2).
INVERT_LEFT  = False
INVERT_RIGHT = False

# Sonar
FRONT_TRIG, FRONT_ECHO = 14, 15
REAR_TRIG,  REAR_ECHO  = 12, 13

# ===========================================================================
# CONFIG - drive tuning   (values marked TUNE need measuring on hardware)
# ===========================================================================
PWM_FREQ      = 1000
MAX_DUTY      = 48000    # hard ceiling of 65535 for fuse safety. Do not raise
                         # without checking current draw.
DRIVE_DUTY    = 40000    # forward/reverse push duty
ROT_DUTY      = 30000    # rotation duty for search (lower = more controlled)
DEADBAND_DUTY = 12000    # TUNE: lowest duty that actually starts the wheels
RAMP_MS       = 250      # soft-start: time to ramp 0 -> full. Protects the
                         # fuse (rule 5.2). Do not set to 0.
BRAKE_MS      = 150      # driver needs >= 100 ms settled before reversing

# Rotation calibration. TUNE: time 10 full spins on the floor, ms / 3600.
ROT_MS_PER_DEG = 8

# Forward speed estimate, mm/s. Only a seed - it self-calibrates live from the
# sonar during the first approach against a stationary target.
SPEED_MM_S = 300

# ===========================================================================
# CONFIG - sonar tuning
# ===========================================================================
# Echo timeout. Round trip for 1 m is ~5830 us. Rule 3.4 mandates 1 m of
# clearance around the ring, so anything past ~1 m is not a target. Keeping
# this near 1 m is the core of the edge-safety doctrine - do not raise it.
ECHO_TIMEOUT_US = 6000               # ~1.0 m
MM_PER_US       = 0.343 / 2.0        # speed of sound, halved for round trip
TRIG_US         = 10
REAR_EVERY      = 3                  # ping rear once every N loops (front is
                                     # pinged every loop for fast control)

# ===========================================================================
# CONFIG - strategy tuning
# ===========================================================================
STANDOFF_MM      = 60     # stop this far short of a bare echo
CONTACT_MM       = 100    # TUNE: range at which the wedge tip reaches them.
                          # The sensor sits partway up the ramp, so verify.
DROPOUT_DELTA_MM = 250    # a range jump bigger than this = target lost, not a
                          # real new target (ring is only 1150 mm across)

APPROACH_BUDGET_MM = 500  # max forward travel in one approach before giving up
ROUND_BUDGET_MM    = 700  # max NET forward travel per round (edge safety)

STALL_EPS_MM    = 25      # range change smaller than this = "not closing"
STALL_WINDOW_MS = 2000    # constant range this long at contact = stalled
ENGAGE_MAX_MS   = 2500    # hard cap on a single engage before backing off
COMMIT_MS       = 1500    # blind push duration when target is in the dead zone
RETREAT_MS      = 450     # how long to reverse after a dropout resolves
REACQUIRE_DEG   = 180     # rotation to bring a rear target to the front

# ===========================================================================
# CONFIG - match timing
# ===========================================================================
T_START_DELAY_MS = 5000   # rule 1.4.3: wait 5 s after the start call
RUNTIME_CAP_MS   = 30000  # bench safety: stop the bot after this. Tunable.
LOOP_MIN_MS      = 5       # floor on loop period

# ===========================================================================
# Hardware objects
# ===========================================================================
led = Pin("LED", Pin.OUT)

_ena = PWM(Pin(ENA)); _ena.freq(PWM_FREQ)
_enb = PWM(Pin(ENB)); _enb.freq(PWM_FREQ)
_in1 = Pin(IN1, Pin.OUT); _in2 = Pin(IN2, Pin.OUT)
_in3 = Pin(IN3, Pin.OUT); _in4 = Pin(IN4, Pin.OUT)

_front_trig = Pin(FRONT_TRIG, Pin.OUT); _front_echo = Pin(FRONT_ECHO, Pin.IN)
_rear_trig  = Pin(REAR_TRIG,  Pin.OUT); _rear_echo  = Pin(REAR_ECHO,  Pin.IN)
_front_trig.value(0); _rear_trig.value(0)


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# ===========================================================================
# Sonar
# ===========================================================================
def _ping(trig, echo):
    """Fire one ping, return range in mm, or -1 for no echo / out of range."""
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(TRIG_US)
    trig.value(0)
    us = time_pulse_us(echo, 1, ECHO_TIMEOUT_US)
    if us <= 0:
        return -1
    return us * MM_PER_US


def read_front():
    return _ping(_front_trig, _front_echo)


def read_rear():
    return _ping(_rear_trig, _rear_echo)


# ===========================================================================
# Drive layer  (three pins per motor, soft-start ramp, duty-integrated odom)
# ===========================================================================
class Drive:
    def __init__(self):
        # signed current/target duty per side (-MAX..MAX; + is forward)
        self.cur_l = 0
        self.cur_r = 0
        self.tgt_l = 0
        self.tgt_r = 0
        self._fwd_dir = 0          # +1 fwd, -1 rev, 0 not translating
        self.speed_mm_s = SPEED_MM_S
        self.travel_mm = 0.0       # forward travel this approach
        self.total_mm = 0.0        # net forward travel this round (signed)
        self._last = time.ticks_ms()

    # -- intent -----------------------------------------------------------
    def forward(self):
        self.tgt_l = DRIVE_DUTY
        self.tgt_r = DRIVE_DUTY
        self._fwd_dir = 1

    def reverse(self):
        self.tgt_l = -DRIVE_DUTY
        self.tgt_r = -DRIVE_DUTY
        self._fwd_dir = -1

    def spin_cw(self):
        # left forward, right back -> clockwise seen from above (verify TEST 2)
        self.tgt_l = ROT_DUTY
        self.tgt_r = -ROT_DUTY
        self._fwd_dir = 0

    def spin_ccw(self):
        self.tgt_l = -ROT_DUTY
        self.tgt_r = ROT_DUTY
        self._fwd_dir = 0

    def stop(self):
        self.tgt_l = 0
        self.tgt_r = 0
        self._fwd_dir = 0

    def reset_travel(self):
        self.travel_mm = 0.0

    def reset_round(self):
        self.travel_mm = 0.0
        self.total_mm = 0.0

    # -- execution --------------------------------------------------------
    def tick(self):
        """Ramp toward target duty, write PWM, integrate odometry. Call every
        loop. Returns dt in ms since the last tick."""
        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last)
        if dt < 0:
            dt = 0
        self._last = now

        step = int(MAX_DUTY * dt / RAMP_MS) + 1   # max duty change this tick
        self.cur_l = self._ramp(self.cur_l, self.tgt_l, step)
        self.cur_r = self._ramp(self.cur_r, self.tgt_r, step)

        self._apply(_ena, _in1, _in2, self.cur_l, INVERT_LEFT)
        self._apply(_enb, _in3, _in4, self.cur_r, INVERT_RIGHT)

        # duty-time odometry fallback (used when no valid echo corrects it)
        if self._fwd_dir != 0:
            d = self._fwd_dir * self.speed_mm_s * dt / 1000.0
            self.travel_mm += d
            self.total_mm += d
        return dt

    @staticmethod
    def _ramp(cur, tgt, step):
        if cur < tgt:
            return min(cur + step, tgt)
        if cur > tgt:
            return max(cur - step, tgt)
        return cur

    @staticmethod
    def _apply(en, in_a, in_b, signed_duty, invert):
        d = -signed_duty if invert else signed_duty
        fwd = d >= 0
        in_a.value(1 if fwd else 0)
        in_b.value(0 if fwd else 1)
        mag = abs(int(d))
        if mag > MAX_DUTY:
            mag = MAX_DUTY
        en.duty_u16(mag)


# ===========================================================================
# State machine
# ===========================================================================
ARMED, SEARCH, REACQUIRE, APPROACH, ENGAGE, COMMIT, RETREAT, DONE = range(8)
_NAMES = ("ARMED", "SEARCH", "REACQUIRE", "APPROACH",
          "ENGAGE", "COMMIT", "RETREAT", "DONE")


class Bot:
    def __init__(self):
        self.drive = Drive()
        self.state = ARMED
        self.t_state = time.ticks_ms()
        self.t_round = time.ticks_ms()

        self.front = -1            # latest front range, -1 = no echo
        self.rear = -1
        self.last_front = -1       # last valid front range
        self.prev_front = -1       # the valid reading before that (for trend)
        self.falling = True        # is the front range decreasing?

        self.spin_ccw = False      # search rotation direction
        self.loop_n = 0

        # per-approach
        self.appr_start_mm = -1
        self.appr_start_t = 0
        # per-engage
        self.stall_ref_mm = -1
        self.t_stall = 0

    # -- helpers ----------------------------------------------------------
    def enter(self, s):
        self.state = s
        self.t_state = time.ticks_ms()

    def in_state_ms(self):
        return time.ticks_diff(time.ticks_ms(), self.t_state)

    def target_ahead(self):
        return self.front > 0

    def note_front(self, r):
        """Record a valid front reading and update the trend."""
        if r > 0:
            if self.last_front > 0:
                self.prev_front = self.last_front
                self.falling = r < self.last_front
            self.last_front = r

    def dropout_kind(self):
        """After losing the front echo, decide what happened.
        Returns 'commit' (they are in our dead zone on the ramp) or
        'retreat' (they separated / went over the line)."""
        if self.last_front > 0 and self.last_front <= (CONTACT_MM + DROPOUT_DELTA_MM) \
                and self.falling:
            return "commit"
        return "retreat"

    # -- states -----------------------------------------------------------
    def st_armed(self):
        # 5 s start delay (rule 1.4.3). Motors held stopped, LED blinks.
        self.drive.stop()
        self.drive.reset_round()
        log("ARMED: 5 s start delay")
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < T_START_DELAY_MS:
            self.drive.tick()
            led.toggle()
            time.sleep_ms(200)
        led.value(1)
        self.t_round = time.ticks_ms()
        self.new_search()

    def new_search(self):
        # alternate rotation direction each time we return to searching so we
        # do not chase our tail in one direction forever
        self.spin_ccw = not self.spin_ccw
        self.enter(SEARCH)

    def st_search(self):
        if self.spin_ccw:
            self.drive.spin_ccw()
        else:
            self.drive.spin_cw()
        if self.target_ahead():
            self.begin_approach()
            return
        # active rear re-acquire: nothing ahead but something behind -> turn
        if self.rear > 0:
            self.enter(REACQUIRE)

    def st_reacquire(self):
        # keep rotating (same direction) to bring the rear target to the front
        if self.spin_ccw:
            self.drive.spin_ccw()
        else:
            self.drive.spin_cw()
        if self.target_ahead():
            self.begin_approach()
            return
        if self.in_state_ms() > ROT_MS_PER_DEG * REACQUIRE_DEG:
            self.enter(SEARCH)     # swept round, resume normal search

    def begin_approach(self):
        self.drive.reset_travel()
        self.appr_start_mm = self.front
        self.appr_start_t = time.ticks_ms()
        self.enter(APPROACH)

    def st_approach(self):
        self.drive.forward()

        if self.front < 0:
            # lost the echo mid-approach
            self.resolve_dropout()
            return

        # live speed calibration + range-based odometry (stationary target:
        # range drop == our forward displacement)
        if self.appr_start_mm > 0:
            moved = self.appr_start_mm - self.front
            if moved > 0:
                self.drive.travel_mm = moved
                dt_s = time.ticks_diff(time.ticks_ms(), self.appr_start_t) / 1000.0
                if moved > 30 and dt_s > 0.15:
                    self.drive.speed_mm_s = clamp(moved / dt_s, 100, 1000)

        if self.front <= CONTACT_MM:
            self.begin_engage()
            return

        # edge-safety budgets
        if self.drive.travel_mm >= APPROACH_BUDGET_MM or \
                self.drive.total_mm >= ROUND_BUDGET_MM:
            log("APPROACH: budget reached, backing off")
            self.enter(RETREAT)

    def begin_engage(self):
        self.stall_ref_mm = self.front
        self.t_stall = time.ticks_ms()
        self.enter(ENGAGE)

    def st_engage(self):
        self.drive.forward()

        if self.front < 0:
            self.resolve_dropout()
            return

        if self.front > CONTACT_MM:
            # they slipped away but are still visible -> chase again
            self.begin_approach()
            return

        # at contact. Are we closing or stalled?
        if self.stall_ref_mm - self.front > STALL_EPS_MM:
            self.stall_ref_mm = self.front       # still closing, reset stall
            self.t_stall = time.ticks_ms()

        if self.drive.total_mm >= ROUND_BUDGET_MM:
            log("ENGAGE: round budget reached, backing off")
            self.enter(RETREAT)
            return

        # Without encoders a constant range means either winning push or dead
        # stall - indistinguishable. Cap the effort and back off; wasting 2.5 s
        # is cheap, breaking a winning push is not.
        if time.ticks_diff(time.ticks_ms(), self.t_stall) > STALL_WINDOW_MS or \
                self.in_state_ms() > ENGAGE_MAX_MS:
            log("ENGAGE: stalled/timed out, backing off")
            self.enter(RETREAT)

    def resolve_dropout(self):
        kind = self.dropout_kind()
        if kind == "commit":
            log("DROPOUT: falling at short range -> COMMIT (blind push)")
            self.enter(COMMIT)
        else:
            log("DROPOUT: rising/far -> RETREAT")
            self.enter(RETREAT)

    def st_commit(self):
        # blind push while the target sits in the sonar dead zone on our ramp.
        # The round budget is the binding safety constraint here.
        self.drive.forward()

        if self.drive.total_mm >= ROUND_BUDGET_MM:
            log("COMMIT: round budget reached, backing off")
            self.enter(RETREAT)
            return

        if self.front > 0:
            # target reappeared
            if self.front > CONTACT_MM and not self.falling:
                log("COMMIT: target separated -> RETREAT")
                self.enter(RETREAT)
            else:
                self.begin_engage()
            return

        if self.in_state_ms() > COMMIT_MS:
            log("COMMIT: push done, backing off")
            self.enter(RETREAT)

    def st_retreat(self):
        # always back off after a dropout resolves - never stop where the edge
        # might be. Reversing reduces net travel (total_mm).
        self.drive.reverse()
        if self.in_state_ms() > RETREAT_MS:
            self.last_front = -1
            self.prev_front = -1
            self.new_search()

    def st_done(self):
        self.drive.stop()

    # -- main loop --------------------------------------------------------
    def run(self):
        # ---- add a watchdog HERE once a start/boot-escape button exists ----
        # from machine import WDT
        # if _button.value() == 0: raise SystemExit("safe boot")
        # wdt = WDT(timeout=2000)
        # --------------------------------------------------------------------
        self.st_armed()

        while True:
            self.loop_n += 1

            # sensing: front every loop, rear occasionally
            self.front = read_front()
            self.note_front(self.front)
            if self.loop_n % REAR_EVERY == 0:
                self.rear = read_rear()

            # safety auto-stop
            if self.state != DONE and \
                    time.ticks_diff(time.ticks_ms(), self.t_round) > RUNTIME_CAP_MS:
                log("RUNTIME CAP reached -> DONE")
                self.enter(DONE)

            # dispatch
            s = self.state
            if s == SEARCH:
                self.st_search()
            elif s == REACQUIRE:
                self.st_reacquire()
            elif s == APPROACH:
                self.st_approach()
            elif s == ENGAGE:
                self.st_engage()
            elif s == COMMIT:
                self.st_commit()
            elif s == RETREAT:
                self.st_retreat()
            elif s == DONE:
                self.st_done()
                self.drive.tick()
                led.value(1)
                self.report()
                return

            self.drive.tick()
            self.report()
            time.sleep_ms(LOOP_MIN_MS)

    def report(self):
        if not DEBUG:
            return
        # throttle to ~7 Hz so the shell stays readable
        if self.loop_n % 10 != 0:
            return
        f = "{:4.0f}".format(self.front) if self.front > 0 else " -- "
        r = "{:4.0f}".format(self.rear) if self.rear > 0 else " -- "
        print("[{:>9}] front={}mm rear={}mm  trav={:4.0f} tot={:4.0f} v={:3.0f}".format(
            _NAMES[self.state], f, r,
            self.drive.travel_mm, self.drive.total_mm, self.drive.speed_mm_s))


def log(msg):
    if DEBUG:
        print("*", msg)


# ===========================================================================
# Entry point
# ===========================================================================
def all_stop():
    _ena.duty_u16(0); _enb.duty_u16(0)
    _in1.value(0); _in2.value(0); _in3.value(0); _in4.value(0)


if __name__ == "__main__":
    bot = Bot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("stopped by user")
    except Exception as e:
        print("ERROR:", e)
        raise
    finally:
        # never leave the motors driving
        all_stop()
        led.value(0)
