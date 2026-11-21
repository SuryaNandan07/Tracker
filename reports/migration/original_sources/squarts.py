from ultralytics import YOLO
import cv2
import numpy as np

# =========================
# LOAD MODEL
# =========================
model = YOLO("yolov8s-pose.pt")

# =========================
# VIDEO / CAMERA
# =========================
cap = cv2.VideoCapture("How to squat correctly.webm")
#cap = cv2.VideoCapture(0)

# cap.set(cv2.CAP_PROP_FRAME_WIDTH, 70)
# cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 30)

# =========================
# VARIABLES
# =========================
prev_person = None
stage = "up"
counter = 0

UP_ANGLE = 160
DOWN_ANGLE = 120

# =========================
# FULL BODY CONNECTIONS
# =========================
connections = [
    (5, 6),
    (5, 7), (7, 9),
    (6, 8), (8, 10),
    (5, 11), (6, 12),
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16)
]

# =========================
# ANGLE FUNCTION
# =========================
def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)

    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - \
              np.arctan2(a[1]-b[1], a[0]-b[0])

    angle = np.abs(radians * 180 / np.pi)

    if angle > 180:
        angle = 360 - angle

    return angle


# =========================
# TORSO ANGLE
# =========================
def torso_angle(shoulder, hip):
    dx = shoulder[0] - hip[0]
    dy = hip[1] - shoulder[1]

    ang = np.degrees(np.arctan2(abs(dx), abs(dy)))
    return ang


# =========================
# SQUAT FORM ANALYSIS
# ONLY CHECK AT BOTTOM / DOWN
# UP PHASE ALWAYS GREEN
# =========================
def analyze_squat(shoulder, hip, knee, ankle, angle, stage):

    # ---------------------------------
    # UP OR RISING = ALWAYS GREEN
    # ---------------------------------
    if stage == "up":
        return (0,255,0), "Ready"

    if stage == "rising":
        return (0,255,0), "Nice Rep"

    # ---------------------------------
    # ONLY DOWN STAGE CHECKS
    # ---------------------------------
    # Half squat
    if angle > 130:
        return (0,0,255), "Go Lower"

    # Knee too forward
    if knee[0] > ankle[0] + 40:
        return (0,0,255), "Knees Forward"

    # Torso collapse
    torso = torso_angle(shoulder, hip)
    if torso > 50:
        return (0,0,255), "Chest Down"

    # Too deep
    if angle < 55:
        return (0,0,255), "Too Deep"

    return (0,255,0), "Perfect Depth"

# =========================
# WINDOW SIZE
# =========================
cv2.namedWindow("Squat Coach", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Squat Coach", 700, 1200)

# =========================
# MAIN LOOP
# =========================
while True:
    ret, frame = cap.read()

    if not ret:
        break

    annotated = frame.copy()

    results = model(frame, verbose=False)

    if results[0].keypoints is not None:

        pts = results[0].keypoints.xy.cpu().numpy()

        if len(pts) > 0:

            person = pts[0]

            # =========================
            # SMOOTHING
            # =========================
            if prev_person is None:
                prev_person = person.copy()

            alpha = 0.7
            person = alpha * prev_person + (1 - alpha) * person
            prev_person = person.copy()

            try:
                shoulder = person[5]
                hip = person[11]
                knee = person[13]
                ankle = person[15]

                # =========================
                # ANGLE
                # =========================
                angle = calculate_angle(hip, knee, ankle)

                # =========================
                # COUNT LOGIC
                # =========================
                # =========================
                # STAGE LOGIC
                # =========================

                if angle < DOWN_ANGLE:
                    stage = "down"

                elif DOWN_ANGLE <= angle < UP_ANGLE:
                    if stage == "down":
                        stage = "rising"

                elif angle >= UP_ANGLE:
                    if stage == "rising":
                        counter += 1
                    stage = "up"

                # =========================
                # ANALYZE
                # =========================
                skeleton_color, warning = analyze_squat(
                    shoulder, hip, knee, ankle, angle, stage
                )

                # Angle text
                cv2.putText(
                    annotated,
                    str(int(angle)),
                    tuple(np.int32(knee)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (255, 255, 255),
                    2
                )

            except:
                skeleton_color = (0, 255, 0)
                warning = "Tracking..."

            # =========================
            # DRAW BODY
            # =========================
            for pt in person:
                x, y = int(pt[0]), int(pt[1])
                cv2.circle(annotated, (x, y), 6, skeleton_color, -1)

            for a, b in connections:
                x1 = int(person[a][0])
                y1 = int(person[a][1])
                x2 = int(person[b][0])
                y2 = int(person[b][1])

                cv2.line(
                    annotated,
                    (x1, y1),
                    (x2, y2),
                    skeleton_color,
                    4
                )

            # Warning text
            cv2.putText(
                annotated,
                warning,
                (420, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                skeleton_color,
                2
            )

    # =========================
    # UI PANEL
    # =========================
    cv2.rectangle(annotated, (0, 0), (300, 110), (30, 30, 30), -1)

    cv2.putText(
        annotated,
        f"Squats: {counter}",
        (10, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated,
        f"Stage: {stage}",
        (10, 85),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2
    )

    # =========================
    # SHOW
    # =========================
    cv2.imshow("Squat Coach", annotated)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# =========================
# END
# =========================
cap.release()
cv2.destroyAllWindows()