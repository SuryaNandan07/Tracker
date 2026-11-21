import unittest
import numpy as np
from mocap.phase2_motion import smooth


class Phase2Tests(unittest.TestCase):
    def test_constant_and_input_unchanged(self):
        points=np.ones((25,33,3)); times=np.arange(25)/60; original=points.copy()
        out=smooth(points,times,np.ones((25,33)),np.zeros((25,33)),{'window':11,'quiet':.97,'fast':.1})
        np.testing.assert_allclose(out,points,atol=1e-12)
        np.testing.assert_array_equal(original,points)

    def test_fast_motion_receives_less_correction(self):
        rng=np.random.default_rng(3); points=rng.normal(size=(25,33,3))*.01
        cfg={'window':11,'quiet':.97,'fast':.1}; times=np.arange(25)/60; confidence=np.ones((25,33))
        quiet=smooth(points,times,confidence,np.zeros((25,33)),cfg)
        fast=smooth(points,times,confidence,np.ones((25,33)),cfg)
        self.assertLess(np.linalg.norm(fast-points),np.linalg.norm(quiet-points)*.2)

    def test_low_confidence_outlier_has_less_influence(self):
        points=np.zeros((25,33,3)); points[12]=1; t=np.arange(25)/60
        cfg={'window':11,'quiet':1.,'fast':0.}; conf=np.ones((25,33)); activity=np.zeros((25,33))
        high=smooth(points,t,conf,activity,cfg)
        conf[12]=.05
        low=smooth(points,t,conf,activity,cfg)
        self.assertLess(low[12,0,0],high[12,0,0])
