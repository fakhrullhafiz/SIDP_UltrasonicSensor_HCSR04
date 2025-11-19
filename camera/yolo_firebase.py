import firebase_admin
from firebase_admin import credentials, db
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

# --------- Firebase setup ----------
cred = credentials.Certificate("/home/coe/firebase/firebase-key.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://sidp-5fcae-default-rtdb.asia-southeast1.firebasedatabase.app/"
})
root = db.reference("objectDetectionDB")  # Root node
print("Firebase initialized successfully!")

malaysia_tz = ZoneInfo("Asia/Kuala_Lumpur")

# --------- TTS setup ----------
tts_queue = queue.Queue()
use_pyttsx3 = False
engine = None

try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)
    engine.setProperty("volume", 1.0)
    use_pyttsx3 = True
except Exception:
    use_pyttsx3 = False

def tts_worker():
    while True:
        text = tts_queue.get()
        if text is None:
            break
        try:
            if use_pyttsx3 and engine is not None:
                engine.say(text)
                engine.runAndWait()
            else:
                subprocess.run(["espeak", text], check=False)
        except Exception as e:
            print("TTS error:", e)
        tts_queue.task_done()

tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def speak(text):
    tts_queue.put(text)

# --------- YOLO + PiCamera2 ----------
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
print("Camera running... Press 'q' to quit")

# FPS setup
start_time = time.time()
frame_count = 0

try:
    while True:
        now = datetime.datetime.now(malaysia_tz)
        timestamp = now.strftime("%Y/%m/%d %H:%M:%S")

        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

        results = model.predict(frame, imgsz=320, conf=0.35, verbose=False)
        r = results[0]

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
        if n == 0:
            cv2.imshow("YOLOv8", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        boxes = boxes[:n]
        cls_array = cls_array[:n]
        confs = confs[:n]

        # Get class names
        detected_names = []
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
            if name in announced_this_frame:
                continue
            last_time = last_announced.get(name, 0)
            if (datetime.datetime.now().timestamp() - last_time) >= ANNOUNCE_COOLDOWN:
                announced_this_frame.add(name)
                last_announced[name] = datetime.datetime.now().timestamp()
            if announced_this_frame:
                speak(", ".join(announced_this_frame) + " detected")

        # Draw boxes and build Firebase data
        firebase_objects = []
        for i in keep_idx:
            x1, y1, x2, y2 = boxes[i].astype(int)
            conf = float(confs[i])
            name = detected_names[i]
            label = f"{name} {conf:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, max(y1 - 8, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            # Prepare data for Firebase
            firebase_objects.append({
                "name": name,
                "confidence": round(conf, 2),
                "bbox": [int(x1), int(y1), int(x2), int(y2)]
            })

        # Prepare Firebase record
        data = {
            "timestamp": timestamp,
            "objects_detected": firebase_objects
        }

        # Upload to Firebase
        if firebase_objects:  # Only push if there are detections
            root.push(data)
            print(f"[{timestamp}] Data uploaded successfully!")
            time.sleep(1)

        # Display FPS
        frame_count += 1
        if frame_count % 30 == 0:
            fps = frame_count / (time.time() - start_time)
            cv2.putText(frame, f"FPS: {fps:.2f}", (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

        cv2.imshow("YOLOv8", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    tts_queue.put(None)
    tts_thread.join(timeout=1)
    print("Exited cleanly.")
