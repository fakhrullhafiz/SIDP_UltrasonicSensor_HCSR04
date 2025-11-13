import RPi.GPIO as GPIO
import time
import statistics
import threading  # 🟢 NEW: to enable parallel measurement

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
# Distance measurement with median filter
# ==============================
def measure_distance(trig, echo, samples=5):
    readings = []

    for _ in range(samples):
        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)
        
        pulse_start = time.time()
        pulse_end = time.time()
        
        while GPIO.input(echo) == 0:
            pulse_start = time.time()
        while GPIO.input(echo) == 1:
            pulse_end = time.time()
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        readings.append(round(distance, 2))
        time.sleep(0.02)

    return statistics.median(readings)

# ==============================
# Thread function wrapper
# ==============================
def threaded_measure(name, trig, echo, results):  # 🟢 NEW
    """Thread target to measure and store result."""
    distance = measure_distance(trig, echo)
    results[name] = distance

# ==============================
# Main Loop with Parallel Measurement
# ==============================
try:
    while True:
        results = {}  # 🟢 NEW: shared dictionary for results

        # 🟢 Create threads for both sensors
        t1 = threading.Thread(target=threaded_measure, args=('Sensor1', TRIG1, ECHO1, results))
        t2 = threading.Thread(target=threaded_measure, args=('Sensor2', TRIG2, ECHO2, results))
        
        # 🟢 Start threads
        t1.start()
        t2.start()
        
        # 🟢 Wait for both to complete
        t1.join()
        t2.join()

        # 🟢 Print results once both threads have finished
        print(f"Sensor 1 Distance: {results['Sensor1']} cm")
        print(f"Sensor 2 Distance: {results['Sensor2']} cm")
        print("-" * 40)

        time.sleep(0.5)  # Small delay before next cycle

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    GPIO.cleanup()
