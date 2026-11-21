import cv2
from ultralytics import YOLO
import math
# Load pose model
model = YOLO("yolov8n-pose.pt")

# Webcam (change to video path if needed)
#cap = cv2.VideoCapture("male-Bodyweight-push-up-side.mp4")
cap = cv2.VideoCapture(0)

count = 0
stage = "UP"

def angle(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c

    ab = (ax - bx, ay - by)
    cb = (cx - bx, cy - by)

    dot = ab[0]*cb[0] + ab[1]*cb[1]
    mag1 = math.sqrt(ab[0]**2 + ab[1]**2)
    mag2 = math.sqrt(cb[0]**2 + cb[1]**2)

    if mag1 == 0 or mag2 == 0:
        return 0

    cosang = dot / (mag1 * mag2)
    cosang = max(-1, min(1, cosang))

    ang = math.degrees(math.acos(cosang))
    return ang


while True:
    ret, frame = cap.read()

    if not ret:
        break

    # Run pose detection
    results = model(frame, verbose=False)

    # Draw skeleton
    annotated = results[0].plot()

    # Show helper text
    cv2.putText(
        annotated,
        "Stand Sideways for Pushup Test",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    if results[0].keypoints is not None:
        pts = results[0].keypoints.xy.cpu().numpy()

        if len(pts) > 0:
            person = pts[0]

            shoulder = person[6]   # try visible shoulder
            elbow    = person[8]
            wrist    = person[10]

            ang = angle(shoulder, elbow, wrist)

            if ang < 95:
                stage = "DOWN"

            elif ang > 155 and stage == "DOWN":
                count += 1
                stage = "LOCKED"

            elif ang > 140 and stage == "LOCKED":
                stage = "UP"

            cv2.putText(annotated, f"Angle: {int(ang)}",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0,255,0), 2)

    display_count=math.ceil(count /2)
    cv2.putText(annotated, f"Pushups: {display_count}",
                (20, 80), cv2.FONT_HERSHEY_SIMPLEX,
                1, (0,255,0), 2)

    cv2.putText(annotated, f"Stage: {stage}",
                (20, 120), cv2.FONT_HERSHEY_SIMPLEX,
                1, (0,255,0), 2)


    cv2.namedWindow("Pushup Coach", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Pushup Coach", 333, 233)
    cv2.imshow("Pushup Coach", annotated)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()



"""
create table t4(n decimal(5,2))

"""