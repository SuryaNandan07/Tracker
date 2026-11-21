import numpy as np
from .config import CONNECTIONS


def draw_skeleton(canvas, points, visibility, threshold=0.3):
    import cv2
    h, w = canvas.shape[:2]
    good = np.isfinite(points[:, :2]).all(axis=1)
    good &= np.isnan(visibility) | (visibility >= threshold)
    # Omit off-screen points in the renderer, never clip the saved coordinates.
    good &= (points[:, :2] >= 0).all(axis=1) & (points[:, :2] <= 1).all(axis=1)
    pixels = {i: (int(points[i,0]*(w-1)), int(points[i,1]*(h-1)))
              for i in np.flatnonzero(good)}
    for a, b in CONNECTIONS:
        if a in pixels and b in pixels:
            cv2.line(canvas, pixels[a], pixels[b], (80,210,90), 2)
    for p in pixels.values():
        cv2.circle(canvas, p, 3, (0,190,255), -1)
