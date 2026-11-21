"""Confidence-weighted adaptive offline landmarks; fixed evaluation masks for all presets."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import numpy as np
from .config import ROOT
from .smooth_motion import filter_tracks


def smooth(points,times,confidence,activity,config):
    n=len(times); out=np.empty_like(points); radius=config['window']//2
    for i,t in enumerate(times):
        lo=max(0,min(i-radius,n-config['window'])); hi=min(n,lo+config['window'])
        dt=times[lo:hi]-t
        design=np.column_stack((np.ones(len(dt)),dt,dt**2))
        for j in range(33):
            weights=np.sqrt(np.clip(confidence[lo:hi,j],.05,1))
            fit=np.linalg.lstsq(design*weights[:,None],points[lo:hi,j]*weights[:,None],rcond=None)[0][0]
            fit=np.clip(fit,points[lo:hi,j].min(axis=0),points[lo:hi,j].max(axis=0))
            amount=config['quiet']*(1-activity[i,j])+config['fast']*activity[i,j]
            out[i,j]=points[i,j]+amount*(fit-points[i,j])
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--presets',type=Path,default=Path(__file__).with_name('phase2_presets.json'))
    parser.add_argument('--output-dir',type=Path,default=ROOT/'exports'/'phase2')
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    configs=json.loads(args.presets.read_text())
    helper=runpy.run_path(str(ROOT/'blender'/'import_mocap.py'))
    source=ROOT/'exports'/'sword_combo_001.json'; raw=helper['load_motion'](source)
    frames,tracks=helper['prepare_tracks'](raw,60)
    points=np.asarray(tracks).transpose(1,0,2); times=np.asarray(raw['timestamps_ms'])/1000
    _,fixed_activity=filter_tracks(points,times)
    # Freeze the previous pass's activity estimator for identical evaluation segments.
    # Its two-frame envelope protects lead-in/recovery of high-speed direction changes.
    activity=fixed_activity.copy()
    confidence=np.asarray(raw['visibility'],dtype=float)
    confidence=np.nan_to_num(confidence,nan=.05)
    confidence=np.where(np.asarray(raw['valid_mask'])[:,None],confidence,.05)
    mask=fixed_activity[1:-1]<.2
    residual=lambda x:np.linalg.norm(x[1:-1]-(x[:-2]+x[2:])/2,axis=2)
    metric=lambda x:float(np.sqrt(np.mean(residual(x)[mask]**2))*1000)
    baseline=np.asarray(json.loads((ROOT/'exports'/'sword_combo_smoothed.json').read_text())['points'])
    for name,cfg in configs.items():
        if cfg['window']<3 or cfg['window']%2==0: raise ValueError('Odd window >=3 required')
        result=smooth(points,times,confidence,activity,cfg)
        data={'preset':name,'config':cfg,'timestamps_ms':raw['timestamps_ms'],'frames':frames,
              'points':result.tolist(),'valid_mask':raw['valid_mask'],
              'metrics':{'raw_landmark_rms_mm':metric(points),'baseline_landmark_rms_mm':metric(baseline),
                         'landmark_rms_mm':metric(result),'quiet_joint_samples':int(mask.sum())},
              'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        with (args.output_dir/f'{name}.json').open('x') as f: json.dump(data,f,allow_nan=False)
        print(name,data['metrics'])


if __name__=='__main__': main()
