import cv2
from ultralytics import YOLO

# Load pose model
model = YOLO("yolov8n-pose.pt")   # first run auto-downloads model
count=0
# Open webcam
cap = cv2.VideoCapture('male-Bodyweight-push-up-side.mp4')
#cap = cv2.VideoCapture(0)
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Run pose detection
    results = model(frame)

    # Draw body keypoints + skeleton
    annotated_frame = results[0].plot()
    cv2.putText(
        annotated_frame,  # image/frame
        "Body Detected",  # text
        (30, 50),  # x,y position
        cv2.FONT_HERSHEY_SIMPLEX,  # font
        1,  # size
        (0, 255, 0),  # color BGR = green
        2  # thickness
    )
    
    # Show output
    cv2.imshow("Body Tracker", annotated_frame)

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

