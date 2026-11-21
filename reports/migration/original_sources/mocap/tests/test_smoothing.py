import unittest
import numpy as np
from mocap.smooth_motion import filter_tracks


class SmoothingTests(unittest.TestCase):
    def test_quadratic_motion_is_preserved(self):
        times=np.arange(61)/60
        points=np.stack([times,times**2,2+times],axis=1)[:,None,:]
        result,_=filter_tracks(points,times)
        np.testing.assert_allclose(result,points,atol=1e-10)

    def test_noise_reduced_without_mutating_input(self):
        times=np.arange(121)/60
        points=np.zeros((121,1,3)); points[:,0,0]=.01*(-1.)**np.arange(121)
        original=points.copy()
        result,_=filter_tracks(points,times)
        self.assertLess(np.std(result[10:-10]),np.std(points[10:-10])*.5)
        np.testing.assert_array_equal(points,original)

    def test_reject_even_window(self):
        with self.assertRaises(ValueError): filter_tracks(np.zeros((20,1,3)),np.arange(20)/60,8)
