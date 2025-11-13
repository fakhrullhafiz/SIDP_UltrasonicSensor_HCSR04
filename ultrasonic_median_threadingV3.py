import RPi.GPIO as GPIO
import time
import statistics
import threading
import os

# --- GPIO SETUP ---
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

# --- Function: Measure Distance with Timeout and Median Filter ---
def measure_distance(trig, echo, samples=5):
    readings = []
    for _ in range(samples):
        # Send 10us pulse
        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)

        # Wait for echo start with timeout
        timeout_start = time.time()
        while GPIO.input(echo) == 0:
            if time.time() - timeout_start > 0.02:  # 20 ms timeout
                return None
        pulse_start = time.time()

        # Wait for echo end with timeout
        timeout_start = time.time()
        while GPIO.input(echo) == 1:
            if time.time() - timeout_start > 0.02:
                return None
        pulse_end = time.time()

        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # convert to cm
        readings.append(distance)
        time.sleep(0.05)  # small delay between samples

    # Median filtering
    if readings:
        median_distance = round(statistics.median(readings), 2)
        return median_distance
    else:
        return None

# --- Threaded Measurement Function ---
def sensor_thread(name, trig, echo, result_dict, key):
    distance = measure_distance(trig, echo)
    result_dict[key] = distance

# --- Main Loop ---
try:
    while True:
        result = {}

        # Start threads for both sensors
        t1 = threading.Thread(target=sensor_thread, args=("Sensor 1", TRIG1, ECHO1, result, "sensor1"))
        t2 = threading.Thread(target=sensor_thread, args=("Sensor 2", TRIG2, ECHO2, result, "sensor2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Clear terminal (this part added)
        os.system('clear')  # Use 'cls' if you're on Windows

        # Display readings
        dist1 = result.get("sensor1", None)
        dist2 = result.get("sensor2", None)

        if dist1 is not None:
            print(f"Sensor 1 Distance: {dist1} cm")
        else:
            print("Sensor 1: No reading (timeout)")

        if dist2 is not None:
            print(f"Sensor 2 Distance: {dist2} cm")
        else:
            print("Sensor 2: No reading (timeout)")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    GPIO.cleanup()
