from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / 'recordings'
DATABASE = ROOT / 'mocap.db'
MODEL = Path(__file__).resolve().parent / 'models' / 'pose_landmarker_full.task'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
LANDMARK_NAMES = (
    'nose left_eye_inner left_eye left_eye_outer right_eye_inner right_eye '
    'right_eye_outer left_ear right_ear mouth_left mouth_right left_shoulder '
    'right_shoulder left_elbow right_elbow left_wrist right_wrist left_pinky '
    'right_pinky left_index right_index left_thumb right_thumb left_hip right_hip '
    'left_knee right_knee left_ankle right_ankle left_heel right_heel '
    'left_foot_index right_foot_index'
).split()
CONNECTIONS = [(0,1),(1,2),(2,3),(3,7),(0,4),(4,5),(5,6),(6,8),(9,10),
               (11,12),(11,13),(13,15),(15,17),(15,19),(15,21),(17,19),
               (12,14),(14,16),(16,18),(16,20),(16,22),(18,20),
               (11,23),(12,24),(23,24),(23,25),(24,26),(25,27),(26,28),
               (27,29),(28,30),(29,31),(30,32),(27,31),(28,32)]
COORDINATES = {
    'image': 'Unmirrored input. x right / image width, y down / image height; '
             'values may leave [0,1]. z relative to hip midpoint, smaller nearer camera, '
             'roughly same scale as x; NOT metric depth.',
    'world': 'MediaPipe estimated meters, origin hip midpoint. Raw model axes preserved; '
             'not calibrated camera/world motion and not a Unity or Blender transform.',
    'time': 'timestamps_ms: float64 elapsed monotonic time since first recorded frame; '
            'sampled immediately after camera read, before inference. Not hardware exposure time.',
    'missing': 'No complete 33-point image/world result: valid_mask=False and all values NaN. '
               'Unavailable scores/joints are NaN. Low-confidence estimates retained raw.',
}
