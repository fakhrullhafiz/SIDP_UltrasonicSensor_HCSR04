import RPi.GPIO as GPIO
import time
import datetime
from zoneinfo import ZoneInfo
import cv2
from ultralytics import YOLO
from picamera2 import Picamera2
import numpy as np
import queue
import threading
import subprocess
import firebase_admin
from firebase_admin import credentials, db

# ========================================
# FIREBASE SETUP
# ========================================
cred = credentials.Certificate("/home/coe/firebase/firebase-key.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://sidp-5fcae-default-rtdb.asia-southeast1.firebasedatabase.app/"
})
ultrasonic_db = db.reference("ultrasonicDB")
object_db = db.reference("objectDetectionDB")
print("Firebase initialized successfully!")

malaysia_tz = ZoneInfo("Asia/Kuala_Lumpur")

# ========================================
# UNIFIED TTS SYSTEM (Threaded, Non-blocking)
# ========================================
tts_queue = queue.PriorityQueue()
use_pyttsx3 = False
engine = None

try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)
    engine.setProperty("volume", 1.0)
    use_pyttsx3 = True
    print("Using pyttsx3 for TTS")
except Exception:
    use_pyttsx3 = False
    print("Using espeak for TTS")

def tts_worker():
    """Background thread that handles all TTS announcements"""
    while True:
        try:
            priority, text = tts_queue.get(timeout=1)
            if text is None:
                tts_queue.task_done()
                break
            
            # Speak the text
            if use_pyttsx3 and engine is not None:
                engine.say(text)
                engine.runAndWait()
            else:
                subprocess.run(["espeak", text], check=False)
            
            tts_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"TTS error: {e}")
            try:
                tts_queue.task_done()
            except:
                pass

tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def speak(text, priority=5):
    """
    Add text to TTS queue
    priority: 1=critical (Stop), 3=warning, 5=normal (object detection)
    """
    tts_queue.put((priority, text))

# ========================================
# ULTRASONIC SENSOR SETUP
# ========================================
GPIO.setmode(GPIO.BOARD)
TRIG = 11
ECHO = 12

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.output(TRIG, False)
time.sleep(0.1)

# Shared ultrasonic data
ultrasonic_data = {
    "distance": 0,
    "message": "Initializing...",
    "color": (255, 255, 255),
    "last_update": time.time()
}
ultrasonic_lock = threading.Lock()

def measure_distance():
    """Measure distance from HC-SR04 sensor with timeout protection"""
    try:
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        pulse_start = time.time()
        pulse_end = time.time()
        timeout = time.time() + 0.1

        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()
            if pulse_start > timeout:
                return None

        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()
            if pulse_end > timeout:
                return None

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        return round(distance, 2)
    except Exception as e:
        print(f"Ultrasonic error: {e}")
        return None

def ultrasonic_worker():
    """Background thread for continuous ultrasonic monitoring"""
    last_message = None
    last_announce_time = 0
    announce_interval = 2.0
    
    while True:
        distance = measure_distance()
        current_time = time.time()
        
        if distance is None:
            with ultrasonic_lock:
                ultrasonic_data["distance"] = 0
                ultrasonic_data["message"] = "Sensor Error"
                ultrasonic_data["color"] = (0, 0, 255)
            time.sleep(0.2)
            continue
        
        # Determine warning level and color
        if distance < 25:
            message = "Stop"
            color = (0, 0, 255)
            priority = 1
        elif distance < 50:
            message = "Warning"
            color = (0, 165, 255)
            priority = 2
        elif distance < 75:
            message = "Caution"
            color = (0, 255, 255)
            priority = 3
        else:
            message = "Clear"
            color = (0, 255, 0)
            priority = 5
        
        # Update shared data
        with ultrasonic_lock:
            ultrasonic_data["distance"] = distance
            ultrasonic_data["message"] = message
            ultrasonic_data["color"] = color
            ultrasonic_data["last_update"] = current_time
        
        # TTS announcement logic
        if message != "Clear":
            if message != last_message or (current_time - last_announce_time) > announce_interval:
                speak(message, priority=priority)
                last_message = message
                last_announce_time = current_time
        else:
            last_message = None
        
        # Upload to Firebase
        try:
            now = datetime.datetime.now(malaysia_tz)
            timestamp = now.strftime("%Y/%m/%d %H:%M:%S")
            firebase_data = {
                "timestamp": timestamp,
                "distance_cm": distance,
                "message": message
            }
            ultrasonic_db.push(firebase_data)
        except Exception as e:
            print(f"Firebase ultrasonic upload error: {e}")
        
        time.sleep(0.2)

# Start ultrasonic monitoring thread
ultrasonic_thread = threading.Thread(target=ultrasonic_worker, daemon=True)
ultrasonic_thread.start()

# ========================================
# YOLO + CAMERA SETUP
# ========================================
model = YOLO("yolov8n.pt")
allowed_classes = {
    'person', 'car', 'cat', 'dog', 'stop sign',
    'toilet', 'chair', 'bed', 'tv', 'dining table', 'vase'
}
ANNOUNCE_COOLDOWN = 5.0
last_announced = {}

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (320, 240), "format": "XBGR8888"}
)
picam2.configure(config)
picam2.start()
print("Camera started. Press 'q' to quit")

# FPS tracking
start_time = time.time()
frame_count = 0

# ========================================
# MAIN LOOP
# ========================================
try:
    while True:
        # Capture frame
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        
        # Run YOLO inference
        results = model.predict(frame, imgsz=320, conf=0.35, verbose=False)
        r = results[0]
        
        # Process detections
        try:
            cls_array = r.boxes.cls.cpu().numpy()
            boxes = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
        except Exception:
            cls_array = np.array(r.boxes.cls)
            boxes = np.array(r.boxes.xyxy)
            confs = np.array(r.boxes.conf)
        
        cls_array = np.atleast_1d(np.array(cls_array).squeeze())
        confs = np.atleast_1d(np.array(confs).squeeze())
        boxes = np.array(boxes)
        if boxes.ndim == 1 and boxes.size == 4:
            boxes = boxes.reshape(1, 4)
        
        n = min(boxes.shape[0], cls_array.shape[0], confs.shape[0])
        
        # Get detected object names
        detected_names = []
        firebase_objects = []
        
        if n > 0:
            boxes = boxes[:n]
            cls_array = cls_array[:n]
            confs = confs[:n]
            
            for c in cls_array:
                idx = int(c)
                if isinstance(model.names, dict):
                    name = model.names.get(idx, str(idx))
                else:
                    name = model.names[idx]
                detected_names.append(name)
            
            # Filter allowed classes
            keep_idx = [i for i, name in enumerate(detected_names) if name in allowed_classes]
            
            # Announcement logic
            announced_this_frame = set()
            for i in keep_idx:
                name = detected_names[i]
                if name not in announced_this_frame:
                    last_time = last_announced.get(name, 0)
                    if (time.time() - last_time) >= ANNOUNCE_COOLDOWN:
                        announced_this_frame.add(name)
                        last_announced[name] = time.time()
            
            # Announce once per frame
            if announced_this_frame:
                announcement = ", ".join(announced_this_frame) + " detected"
                speak(announcement, priority=5)
            
            # Draw bounding boxes
            for i in keep_idx:
                x1, y1, x2, y2 = boxes[i].astype(int)
                conf = float(confs[i])
                name = detected_names[i]
                label = f"{name} {conf:.2f}"
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, max(y1 - 8, 10)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                
                # Prepare Firebase data
                firebase_objects.append({
                    "name": name,
                    "confidence": round(conf, 2),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                })
        
        # Upload YOLO detections to Firebase
        if firebase_objects:
            try:
                now = datetime.datetime.now(malaysia_tz)
                timestamp = now.strftime("%Y/%m/%d %H:%M:%S")
                data = {
                    "timestamp": timestamp,
                    "objects_detected": firebase_objects
                }
                object_db.push(data)
            except Exception as e:
                print(f"Firebase object upload error: {e}")
        
        # ========================================
        # OVERLAY ULTRASONIC DATA ON FRAME
        # ========================================
        with ultrasonic_lock:
            distance = ultrasonic_data["distance"]
            message = ultrasonic_data["message"]
            color = ultrasonic_data["color"]
        
        # Create semi-transparent overlay box
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (315, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Display ultrasonic info
        cv2.putText(frame, f"Distance: {distance:.1f} cm", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Status: {message}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Add color indicator bar
        cv2.rectangle(frame, (10, 55), (310, 65), color, -1)
        
        # Display FPS
        frame_count += 1
        if frame_count % 30 == 0:
            fps = frame_count / (time.time() - start_time)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        # Show frame
        cv2.imshow("Vision Assistance System", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\nStopped by user")

finally:
    # Clean shutdown
    print("Shutting down...")
    
    # Stop camera
    try:
        picam2.stop()
    except Exception:
        pass
    
    # Close OpenCV windows
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    
    # Cleanup GPIO
    try:
        GPIO.cleanup()
    except Exception:
        pass
    
    # Stop TTS thread
    try:
        tts_queue.put((0, None))
        tts_thread.join(timeout=2)
    except Exception:
        pass
    
    # Clean pyttsx3 engine
    if use_pyttsx3 and engine is not None:
        try:
            engine.stop()
        except Exception:
            pass
    
    print("Exited cleanly")
