# Sumobot ultrasonic bench test  (Stage 0)
#
# Pico 2 tethered to the laptop over USB. Run this from Thonny and watch
# the REPL. It reads both RCWL-1601 sensors and prints, once per cycle,
# the raw echo pulse width in microseconds and the distance in cm and mm.
#
# Wiring (RCWL-1601 runs at 3.3 V, so no level shifter on Echo):
#   Front   Vcc -> 3V3   Trig -> GP14   Echo -> GP15   GND -> GND
#   Rear    Vcc -> 3V3   Trig -> GP12   Echo -> GP13   GND -> GND
#
# What to look for (Stage 0 pass criteria):
#   - Sensible mm at close range (hand held ~10-80 cm in front of a sensor).
#   - Reading grows/shrinks smoothly as you move the target.
#   - "no echo" past roughly 1 m  <- the timeout is a FEATURE, not a fault.
#   - Nothing under ~2 cm reads correctly; that is the sensor blind zone.
#
# Stop it any time with the red Stop button in Thonny (Ctrl-C).

from machine import Pin, time_pulse_us
import time

# --- pin map ---
FRONT_TRIG, FRONT_ECHO = 14, 15
REAR_TRIG,  REAR_ECHO  = 12, 13

# --- timing / physics ---
TRIG_US        = 10        # 10 us trigger pulse, per the HC-SR04/RCWL spec
ECHO_TIMEOUT_US = 25000    # give up waiting for the echo after this long.
                           # ~25 ms covers about 4 m round trip, generous for
                           # the bench. The real firmware clamps this near 1 m
                           # (rule 3.4). time_pulse_us returns <0 on timeout.
SETTLE_MS      = 60        # gap between pings so one sensor's echo does not
                           # get heard by the other (sonar crosstalk)
LOOP_MS        = 200       # roughly 5 readings/second, easy to read live

# Speed of sound ~343 m/s at 20 C = 0.343 mm/us. Halve it for the round trip.
MM_PER_US = 0.343 / 2.0

led = Pin("LED", Pin.OUT)

front_trig = Pin(FRONT_TRIG, Pin.OUT)
front_echo = Pin(FRONT_ECHO, Pin.IN)
rear_trig  = Pin(REAR_TRIG, Pin.OUT)
rear_echo  = Pin(REAR_ECHO, Pin.IN)

front_trig.value(0)
rear_trig.value(0)


def read_pulse_us(trig, echo):
    """Fire one ping and return the echo high-time in us, or -1 on timeout."""
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(TRIG_US)
    trig.value(0)

    # Measures how long echo stays high. Returns -1 (no start) or -2
    # (no finish) on timeout; treat any negative value as "no echo".
    us = time_pulse_us(echo, 1, ECHO_TIMEOUT_US)
    return us if us > 0 else -1


def fmt(name, us):
    """Build one readable line for a sensor."""
    if us < 0:
        return "{:>5}: pulse=  ----us   dist=  no echo (out of range)".format(name)
    mm = us * MM_PER_US
    cm = mm / 10.0
    return "{:>5}: pulse={:6d}us   dist={:6.1f} cm  ({:6.0f} mm)".format(
        name, us, cm, mm)


print("Ultrasonic bench test - front GP14/GP15, rear GP12/GP13")
print("Move a hand or box in front of each sensor. Ctrl-C to stop.")
print("-" * 60)

try:
    while True:
        led.on()

        f_us = read_pulse_us(front_trig, front_echo)
        time.sleep_ms(SETTLE_MS)
        r_us = read_pulse_us(rear_trig, rear_echo)

        print(fmt("FRONT", f_us))
        print(fmt("REAR",  r_us))
        print("-" * 60)

        led.off()
        time.sleep_ms(LOOP_MS)

except KeyboardInterrupt:
    print("stopped")

finally:
    front_trig.value(0)
    rear_trig.value(0)
    led.off()
