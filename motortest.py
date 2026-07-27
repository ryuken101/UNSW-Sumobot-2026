# Sumobot drivetrain test
# Wheels OFF THE GROUND. Flash over USB with battery unplugged,
# then unplug USB, then connect the battery.
#
# Sequence: 3s blink warning, then
#   M1 fwd, M1 rev, M2 fwd, M2 rev, then both fwd.
# Note which way each wheel actually turns on the "fwd" passes. Use that to
# set INVERT_LEFT / INVERT_RIGHT and the LEFT/RIGHT motor mapping in main.py.

from machine import Pin, PWM
import time

# --- pin map (matches P1 header on the DRI0041) ---
ENA, IN1, IN2 = 21, 20, 19      # motor 1 -> P4 (OUT1/OUT2)
ENB, IN3, IN4 = 18, 17, 16      # motor 2 -> P3 (OUT3/OUT4)

DUTY     = 20000                # ~30% of 65535. Keep low for a first run.
PWM_FREQ = 1000
BRAKE_MS = 150                  # driver needs >= 100 ms before reversing
RUN_MS   = 1000

ena = PWM(Pin(ENA)); ena.freq(PWM_FREQ)
enb = PWM(Pin(ENB)); enb.freq(PWM_FREQ)
in1 = Pin(IN1, Pin.OUT)
in2 = Pin(IN2, Pin.OUT)
in3 = Pin(IN3, Pin.OUT)
in4 = Pin(IN4, Pin.OUT)
led = Pin("LED", Pin.OUT)


def stop():
    """Coast both motors, then hold for the brake interval."""
    ena.duty_u16(0)
    enb.duty_u16(0)
    in1.value(0); in2.value(0)
    in3.value(0); in4.value(0)
    time.sleep_ms(BRAKE_MS)


def m1(fwd, duty=DUTY):
    in1.value(1 if fwd else 0)
    in2.value(0 if fwd else 1)
    ena.duty_u16(duty)


def m2(fwd, duty=DUTY):
    in3.value(1 if fwd else 0)
    in4.value(0 if fwd else 1)
    enb.duty_u16(duty)


def blink(n, ms=250):
    for _ in range(n * 2):
        led.toggle()
        time.sleep_ms(ms)
    led.value(0)


def pulse(fn, fwd, label):
    print(label)
    fn(fwd)
    time.sleep_ms(RUN_MS)
    stop()
    time.sleep_ms(800)


try:
    stop()
    print("starting in 3s - wheels off the ground")
    blink(6)

    pulse(m1, True,  "M1 forward")
    pulse(m1, False, "M1 reverse")
    pulse(m2, True,  "M2 forward")
    pulse(m2, False, "M2 reverse")

    print("both forward")
    m1(True); m2(True)
    time.sleep_ms(RUN_MS)
    stop()

    print("done")
    led.value(1)

except Exception as e:
    # Never leave the motors driving if anything goes wrong.
    stop()
    print("ERROR:", e)
    raise

finally:
    stop()
