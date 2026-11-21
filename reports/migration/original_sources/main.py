#
#
# import cv2
# import numpy as np
# import time
# import mediapipe as mp
# #drawing utils
# from mediapipe.tasks.python.vision import PoseLandmarker
#
# mp_drawing = mp.solutions.drawing_utils
# mp_pose=mp.solutions.pose
#
#
# cap=cv2.VideoCapture(0)#video feed
# with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
#     while cap.isOpened():
#         ret, frame=cap.read()
#         # detect stuff and render
#         #recolor image to RGB
#         image=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#         image.flags.writeable = False
#
#         #Make decisions
#         results=pose.process(image)
#
#         #recolor image to BGR
#         image.flags.writeable = True
#         image=cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
#
#
#         cv2.imshow('Mediapipe feed', frame)
#
#         if cv2.waitKey(10)& 0xFF==ord('q'): #trying to close screen?
#             break
#
#
# cap.release()
# cv2.destroyAllWindows()