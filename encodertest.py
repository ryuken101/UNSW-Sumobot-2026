# Sumobot encoder test
# UNSW Sumobots 2026, ADAM SMASHERS. Raspberry Pi Pico 2, MicroPython.
#
# ============================================================================
# WHAT THIS IS
# ============================================================================
# A bench test for the two FIT0186 quadrature encoders. You spin each wheel by
# HAND and watch the decoded count, the raw A/B channel levels, and the pulse
# rate print live in the Thonny shell. It confirms three things before the
# firmware ever trusts the encoders:
#   1. the signal actually reaches the Pico (level shifter + wiring),
#   2. the quadrature decode is correct and stable,
#   3. which physical spin direction counts up vs down.
#
# It does NOT test the interrupt-rate ceiling. That problem (the encoder sits
# ahead of the gearbox, so under motor power the tick rate is multiplied and
# can starve the main loop) only shows up when the motors are driven at speed.
# Re-check that separately under power before trusting encoders in a match.
#
# ============================================================================
# WIRING
# ============================================================================
# Encoders are 5 V, so they go through the CE07510 level shifter. Pico reads
# the LV (3.3 V) side. Confirm HV = 5 V, LV = 3.3 V, grounds common.
#   Left  encoder  A -> GP28 (LV1)   B -> GP27 (LV2)
#   Right encoder  A -> GP26 (LV3)   B -> GP22 (LV4)
#   Switch  GP4 -> switch -> GND   (internal pull-up, reads 0 when pressed)
#
# ============================================================================
# HOW TO TEST  (in order)
# ============================================================================
#   1. Power the level shifter first: HV to 5 V, LV to 3V3, GND common. A dead
#      or unpowered shifter is the most likely reason for no counts or noise.
#   2. USB tether the Pico. Open this file in Thonny, interpreter set to
#      MicroPython (Raspberry Pi Pico). Press Run.
#   3. The LED blinks = waiting. Press the GP4 switch to start.
#   4. Slowly turn the LEFT wheel by hand one way. The LEFT count should move
#      smoothly. Turn it back, it should count back down. The RIGHT count
#      should NOT move (if it does, the two encoders are cross-wired).
#   5. Repeat for the RIGHT wheel.
#   6. To measure counts-per-revolution: press the switch to zero the counters,
#      turn one wheel exactly one full turn, read the count. Put that number in
#      COUNTS_PER_REV below so the odometry can convert counts to distance.
#   7. Ctrl-C (red Stop) to finish.
#
# WHAT TO LOOK OUT FOR
#   - Both A and B levels should toggle as you spin. If one channel is stuck at
#     0 or 1, that channel is dead and you lose direction sensing. Check the
#     shifter and that pin.
#   - A count that drifts or jitters by a few while the wheel is dead still
#     means a floating or noisy line: check the level shifter power, the GND,
#     and the connections. Clean encoders do not move when the wheel is still.
#   - Big jumps or a frozen count while spinning steadily = missed edges or a
#     loose wire.
#   - Note which spin direction gives a POSITIVE count on each wheel. That is
#     what "forward" means for that motor. If forward gives a negative count,
#     swap that encoder's A and B pins (or negate it in the firmware later).
# ============================================================================

from machine import Pin
import time

# --- pin map ---
L_A, L_B = 28, 27      # left encoder channels A, B
R_A, R_B = 26, 22      # right encoder channels A, B
SWITCH   = 4           # start / zero button, to GND, pressed = 0

# --- calibration ---
# Output-shaft counts per full wheel revolution, in 4x quadrature. Leave 0
# until measured (step 6); while 0 the script prints raw counts only.
COUNTS_PER_REV = 0

# 4x quadrature transition table. Index = (previous_state << 2) | new_state,
# where state = (A << 1) | B. Valid Gray-code steps give +1 / -1; an illegal
# jump (a missed edge) gives 0 rather than a wrong count.
_QTAB = (0, -1,  1,  0,
         1,  0,  0, -1,
        -1,  0,  0,  1,
         0,  1, -1,  0)


class Encoder:
    def __init__(self, pin_a, pin_b, name):
        self.name = name
        # No pull: the level shifter output is push-pull.
        self.a = Pin(pin_a, Pin.IN)
        self.b = Pin(pin_b, Pin.IN)
        self.count = 0
        self.state = (self.a.value() << 1) | self.b.value()
        # Interrupt on every edge of both channels = full 4x resolution.
        self.a.irq(self._cb, Pin.IRQ_RISING | Pin.IRQ_FALLING)
        self.b.irq(self._cb, Pin.IRQ_RISING | Pin.IRQ_FALLING)

    def _cb(self, pin):
        s = (self.a.value() << 1) | self.b.value()
        self.count += _QTAB[(self.state << 2) | s]
        self.state = s

    def levels(self):
        return self.a.value(), self.b.value()


led = Pin("LED", Pin.OUT)
sw  = Pin(SWITCH, Pin.IN, Pin.PULL_UP)
left  = Encoder(L_A, L_B, "LEFT")
right = Encoder(R_A, R_B, "RIGHT")


def wait_for_press():
    """Block, blinking, until the switch is pressed and released (debounced)."""
    while sw.value() == 0:          # make sure it starts released
        time.sleep_ms(10)
    while True:
        led.toggle()
        if sw.value() == 0:
            time.sleep_ms(30)
            if sw.value() == 0:
                break
        time.sleep_ms(100)
    led.value(1)
    while sw.value() == 0:          # wait for release so it is not re-read
        time.sleep_ms(10)


def press_edge():
    """Return True once per press, debounced, without blocking on release long."""
    if sw.value() == 0:
        time.sleep_ms(30)
        if sw.value() == 0:
            while sw.value() == 0:
                time.sleep_ms(5)
            return True
    return False


def fmt(enc, rate):
    a, b = enc.levels()
    st = (a << 1) | b
    if rate > 0:
        d = "->"
    elif rate < 0:
        d = "<-"
    else:
        d = "--"
    line = "{:<5} A={} B={} st={}  count={:7d}  rate={:6d}/s  {}".format(
        enc.name, a, b, st, enc.count, rate, d)
    if COUNTS_PER_REV > 0:
        line += "  rev={:7.2f}".format(enc.count / COUNTS_PER_REV)
    return line


print("Encoder test - left GP28/GP27, right GP26/GP22, switch GP4")
print("Spin each wheel by hand. Press the switch to START (and later to ZERO).")
print("-" * 60)
wait_for_press()
print("started - spin a wheel")
print("-" * 60)

l_prev = left.count
r_prev = right.count
t_prev = time.ticks_ms()

try:
    while True:
        if press_edge():
            left.count = 0
            right.count = 0
            l_prev = 0
            r_prev = 0
            print("-- counters zeroed --")

        time.sleep_ms(200)

        now = time.ticks_ms()
        dt = time.ticks_diff(now, t_prev) / 1000.0
        if dt <= 0:
            dt = 0.001
        l_rate = int((left.count - l_prev) / dt)
        r_rate = int((right.count - r_prev) / dt)

        print(fmt(left, l_rate))
        print(fmt(right, r_rate))
        print("-" * 60)

        l_prev = left.count
        r_prev = right.count
        t_prev = now

except KeyboardInterrupt:
    print("stopped")
    print("final counts:  LEFT={}  RIGHT={}".format(left.count, right.count))
