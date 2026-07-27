# UNSW-Sumobot-2026, ADAM SMASHERS!!!

A wedge shaped sumo robot built for the UNSW Sumobots 2026 Opens stream. It runs fully autonomously on a Raspberry Pi Pico 2 with two ultrasonic sensors, one facing forward and one facing back. Without line sensors there is no direct way to detect the edge of the ring, so the firmware keeps itself safe by only ever driving toward a confirmed target and searching by rotating on the spot.

## Hardware

| Part | Detail |
|---|---|
| MCU | Raspberry Pi Pico 2 (RP2350), MicroPython |
| Motors | 2x DFRobot FIT0186, 12 V, encoders built in |
| Driver | DFRobot DRI0041, dual 7 A |
| Battery | 3S 11.1 V 1300 mAh LiPo, XT60, 7.5 A inline fuse |
| Sensors | 2x RCWL-1601 ultrasonic, front and rear |
| Wheels | 65 mm, about 63.5 mm loaded |
| Mass | about 1250 g, cap is 1500 g |

The RCWL-1601 runs at 3.3 V logic, so its Echo line connects straight to a Pico GPIO with no level shifter.

## Current progress

The robot is still being built and nothing here has been validated on hardware yet. Development is happening one subsystem at a time. Each subsystem gets a small standalone test script that runs on the bench with the Pico tethered to a laptop over USB, so behaviour can be watched live in the Thonny shell before any of it is combined into the full firmware.

| File | What it is | Status |
|---|---|---|
| `main.py` | Drivetrain test. Drives each motor forward and reverse, then both together, with the wheels off the ground. | Written, not yet run on hardware |
| `ultrasonictest.py` | Ultrasonic bench test. Reads both sensors and prints live distance and raw pulse timing to the shell. | Written, not yet run on hardware |

The next step after both of these check out is to merge the drive layer and the sonar layer into a single `main.py` state machine that searches by rotating, drives only toward a confirmed echo, and stays inside the ring.

## How the ultrasonic test works

`ultrasonictest.py` is the Stage 0 sensor check. It answers one question: do both RCWL-1601 sensors return sane distances before we trust them in the real firmware.

Wiring:

```
Front   Vcc -> 3V3   Trig -> GP14   Echo -> GP15   GND -> GND
Rear    Vcc -> 3V3   Trig -> GP12   Echo -> GP13   GND -> GND
```

How a single reading is taken:

1. Hold Trig low briefly, then pulse it high for 10 microseconds. That tells the sensor to send out an ultrasonic burst.
2. The sensor raises its Echo line and holds it high for exactly as long as the sound takes to travel out and bounce back. `time_pulse_us` measures that high time in microseconds.
3. Distance comes from the speed of sound. Sound travels about 0.343 mm per microsecond, and the pulse covers the round trip, so distance in mm is the pulse width times 0.343 divided by 2.

The timeout is deliberate. If nothing bounces back within the echo window, `time_pulse_us` returns a negative value and the script prints `no echo (out of range)` instead of a distance. Past roughly 1 m there is nothing to bounce off, so no echo is the correct and expected result, not a fault. This is the same idea the real firmware leans on: an echo means a target is in front of us, and no echo means there is nothing to drive toward.

Two details keep the readings honest:

- A 60 ms gap sits between firing the front sensor and firing the rear one, so one sensor does not hear the other sensor's ping. That kind of crosstalk would otherwise show up as a false close reading.
- Anything closer than about 2 cm sits in the sensor's blind zone and will not read correctly. That is a property of the sensor, not a bug.

Each cycle the script prints, for both sensors, the raw echo pulse width in microseconds alongside the distance in cm and mm, so both the timing and the converted value are visible at once. The onboard LED blinks once per cycle as a heartbeat.

## How the motor test works

`main.py` is the drivetrain check. With the wheels off the ground it blinks a 3 second warning, then drives motor 1 forward and reverse, motor 2 forward and reverse, and finally both forward together, printing each step. The point is to confirm the wiring and to note which way each wheel actually spins on the forward passes, so the firmware can be told which motors to invert. Any error stops both motors immediately, and the motors are always stopped on exit.

## Running a test in Thonny

1. Connect the Pico to the laptop with a micro-USB data cable. A charge-only cable is a common cause of an apparently dead board.
2. Open the test file in Thonny and set the interpreter to MicroPython (Raspberry Pi Pico).
3. Press Run. Output streams to the shell. Stop with the red Stop button.

Run the motor test with the wheels off the ground, and on battery rather than USB once you move past the bench, since behaviour at a full 11.8 V is not the same as at a sagging 10.9 V.
