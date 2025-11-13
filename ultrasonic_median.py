import RPi.GPIO as GPIO
import time
import statistics   # 🟢 NEW: used for median filtering

# ==============================
# GPIO Setup
# ==============================
GPIO.setmode(GPIO.BOARD)

# Pins for sensor 1
TRIG1 = 11  # GPIO 17
ECHO1 = 12  # GPIO 18

# Pins for sensor 2
TRIG2 = 13  # GPIO 27
ECHO2 = 15  # GPIO 22

GPIO.setup(TRIG1, GPIO.OUT)
GPIO.setup(ECHO1, GPIO.IN)
GPIO.setup(TRIG2, GPIO.OUT)
GPIO.setup(ECHO2, GPIO.IN)

GPIO.output(TRIG1, False)
GPIO.output(TRIG2, False)
print("Wait for sensors to settle...")
time.sleep(2)

# ==============================
# Function to measure distance with median filtering
# ==============================
def measure_distance(trig, echo, samples=9):  # 🟢 MODIFIED: added 'samples' parameter
    readings = []  # 🟢 NEW: to collect multiple samples

    for _ in range(samples):
        # Send 10us pulse
        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)
        
        # Measure echo timing
        pulse_start = time.time()
        pulse_end = time.time()
        
        while GPIO.input(echo) == 0:
            pulse_start = time.time()
        while GPIO.input(echo) == 1:
            pulse_end = time.time()
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # cm
        readings.append(round(distance, 2))  # 🟢 NEW: store each reading

        time.sleep(0.02)  # 🟢 NEW: small gap between samples to stabilize signal

    # 🟢 NEW: compute and return median value
    median_distance = statistics.median(readings)
    return median_distance

# ==============================
# Main Loop
# ==============================
try:
    while True:
        # Measure sensor 1
        dist1 = measure_distance(TRIG1, ECHO1)
        print("Sensor 1 Distance:", dist1, "cm")
        
        time.sleep(0.1)  # Prevent crosstalk

        # Measure sensor 2
        dist2 = measure_distance(TRIG2, ECHO2)
        print("Sensor 2 Distance:", dist2, "cm")
        
        print("-" * 40)
        time.sleep(1)

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    GPIO.cleanup()
