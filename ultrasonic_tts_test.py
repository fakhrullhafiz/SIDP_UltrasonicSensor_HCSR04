# ultrasonic_sensor.py
import time
import RPi.GPIO as GPIO

class UltrasonicSensor:
    def __init__(self, trig_pin, echo_pin):
        self.trig = trig_pin
        self.echo = echo_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trig, GPIO.OUT)
        GPIO.setup(self.echo, GPIO.IN)

    def get_distance(self):
        # Send trigger pulse
        GPIO.output(self.trig, True)
        time.sleep(0.00001)
        GPIO.output(self.trig, False)

        start_time = time.time()
        stop_time = time.time()

        # Save start time
        while GPIO.input(self.echo) == 0:
            start_time = time.time()

        # Save arrival time
        while GPIO.input(self.echo) == 1:
            stop_time = time.time()

        # Calculate distance
        time_elapsed = stop_time - start_time
        distance = (time_elapsed * 34300) / 2
        return round(distance, 2)

    def cleanup(self):
        GPIO.cleanup()
