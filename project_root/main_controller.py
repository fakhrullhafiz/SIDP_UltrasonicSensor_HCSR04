import threading
import time

# Import your subsystem functions
from object_detection import run_object_detection
#from ultrasonic_sensor import run_ultrasonic


def main():
    """
    Main controller for Smart Assistance Device.
    This script coordinates the object detection (camera)
    and ultrasonic distance warning systems to run together.
    """

    print("Initializing Smart Assistance Device...")
    time.sleep(1)
    print("Starting subsystems...\n")

    # --- Create threads for both subsystems ---
    # Thread 1: Object detection (camera + YOLO)
    object_thread1 = threading.Thread(target=run_object_detection, name="ObjectDetectionThread")

    # Thread 2: Ultrasonic distance monitoring
    #ultrasonic_thread = threading.Thread(target=run_ultrasonic, name="UltrasonicThread")

    # --- Start both threads ---
    object_thread1.start()
    #ultrasonic_thread.start()

    print("✅ Both subsystems are now running concurrently.")
    print("Press Ctrl+C to safely stop the program.\n")

    # --- Keep main thread alive ---
    try:
        while True:
            time.sleep(1)  # Keep main thread alive while others run
    except KeyboardInterrupt:
        print("\n🛑 Stopping all subsystems...")
        # In more advanced integration, you’d add stop signals here
        object_thread.join(timeout=2)
        ultrasonic_thread.join(timeout=2)
        print("✅ All systems stopped cleanly.")


if __name__ == "__main__":
    print("[Main] Starting Object Detection Thread...")
    object_thread1.start()
    print("[Main] Starting Ultrasonic Thread...")
    #ultrasonic_thread.start()
    print("[Main] All threads started. Monitoring...")

