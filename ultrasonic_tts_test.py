import RPi.GPIO as GPIO
import time
import os
import datetime
from zoneinfo import ZoneInfo

# === Firebase Setup ===
import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("/home/coe/firebase/firebase-key.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://sidp-5fcae-default-rtdb.asia-southeast1.firebasedatabase.app/"
})
root = db.reference("ultrasonicDB")
print("Firebase initialized successfully (Ultrasonic)!")

malaysia_tz = ZoneInfo("Asia/Kuala_Lumpur")

# === GPIO SETUP ===
GPIO.setmode(GPIO.BOARD)

TRIG = 11
ECHO = 12

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

GPIO.output(TRIG, False)
print("Waiting for sensor to settle...")
time.sleep(2)

# === FUNCTION TO MEASURE DISTANCE ===
def measure_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    pulse_start = time.time()
    pulse_end = time.time()

    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()

    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

# === MAIN LOOP ===
try:
    last_message = None
    last_announce_time = 0
    announce_interval = 2  # seconds

    while True:
        distance = measure_distance()
        print(f"Distance: {distance} cm")  # <-- timestamp NOT printed

        current_time = time.time()

        # Malaysia timestamp for Firebase only
        now = datetime.datetime.now(malaysia_tz)
        timestamp = now.strftime("%Y/%m/%d %H:%M:%S")

        # === Threshold logic ===
        if distance < 50:
            message = "Stop"
        elif distance < 100:
            message = "Warning, object ahead"
        elif distance < 200:
            message = "Caution"
        else:
            message = None

        # === TTS logic ===
        if message and (message != last_message or current_time - last_announce_time > announce_interval):
            os.system(f"espeak '{message}'")
            last_message = message
            last_announce_time = current_time

        # === Firebase upload WITH timestamp (NOT printed) ===
        firebase_data = {
            "timestamp": timestamp,
            "distance_cm": distance,
            "message": message if message else "None"
        }

        root.push(firebase_data)
        print("Uploaded to Firebase")  # <-- timestamp not shown

        time.sleep(1)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    GPIO.cleanup()
