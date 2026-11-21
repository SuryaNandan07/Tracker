"""Non-destructive, centered adaptive quadratic smoothing using NumPy only."""
import argparse
import json
import runpy
from pathlib import Path
import numpy as np
from .config import ROOT


def filter_tracks(points, times, window=9, strength=.85, fast_strength=.15):
    if window < 3 or window % 2 == 0:
        raise ValueError('window must be odd and >= 3')
    n=len(times); fitted=np.empty_like(points)
    for i,t in enumerate(times):
        lo=max(0,min(i-window//2,n-window)); hi=min(n,lo+window)
        offsets=(times[lo:hi]-t)
        design=np.column_stack([np.ones(hi-lo),offsets,offsets**2])
        fitted[i]=np.linalg.lstsq(design,points[lo:hi].reshape(hi-lo,-1),rcond=None)[0][0].reshape(points.shape[1:])
    speed=np.linalg.norm(np.gradient(fitted,times,axis=0),axis=2)
    low=np.quantile(speed,.35,axis=0); high=np.maximum(np.quantile(speed,.85,axis=0),low+1e-5)
    activity=np.clip((speed-low)/(high-low),0,1)
    # Broad centered activity envelope preserves the lead-in and recovery of strikes.
    activity=np.maximum.reduce([np.roll(activity,k,axis=0) for k in range(-2,3)])
    blend=strength*(1-activity)+fast_strength*activity
    return points+(fitted-points)*blend[:,:,None], activity


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window',type=int,default=9)
    p.add_argument('--strength',type=float,default=.85)
    p.add_argument('--fast-strength',type=float,default=.15)
    p.add_argument('--output',type=Path,default=ROOT/'exports'/'sword_combo_smoothed.json')
    args=p.parse_args()
    if not 0<=args.fast_strength<=args.strength<=1: p.error('Require 0 <= fast-strength <= strength <= 1')
    helper=runpy.run_path(str(ROOT/'blender'/'import_mocap.py'))
    raw=helper['load_motion'](ROOT/'exports'/'sword_combo_001.json')
    frames,tracks=helper['prepare_tracks'](raw,60)
    points=np.asarray(tracks).transpose(1,0,2); times=np.asarray(raw['timestamps_ms'])/1000
    smoothed,activity=filter_tracks(points,times,args.window,args.strength,args.fast_strength)
    # Stationarity is selected from broad motion, not the jitter being measured.
    stationary=activity[1:-1]<.2
    residual=lambda x:np.linalg.norm(x[1:-1]-(x[:-2]+x[2:])/2,axis=2)
    before=residual(points); after=residual(smoothed)
    speed=lambda x:np.linalg.norm(np.gradient(x,times,axis=0),axis=2)
    a,b=speed(points),speed(smoothed)
    peaks={}
    for j in (15,16):
        # Compare each largest separated raw wrist-speed event in a +/- 3 sample window.
        indices=[]
        for i in np.argsort(a[:,j])[::-1]:
            if all(abs(int(i)-k)>20 for k in indices): indices.append(int(i))
            if len(indices)==5: break
        peaks[str(j)]=[{'time_s':float(times[i]),'raw_speed_m_s':float(a[i,j]),
            'filtered_speed_m_s':float(b[max(0,i-3):i+4,j].max()),
            'peak_shift_ms':float((times[max(0,i-3)+int(b[max(0,i-3):i+4,j].argmax())]-times[i])*1000)} for i in sorted(indices)]
    metrics={'stationary_landmark_residual_rms_mm_before':float(np.sqrt(np.mean(before[stationary]**2))*1000),
        'stationary_landmark_residual_rms_mm_after':float(np.sqrt(np.mean(after[stationary]**2))*1000),
        'stationary_joint_samples':int(stationary.sum()),'wrist_speed_events':peaks}
    result={'timestamps_ms':raw['timestamps_ms'],'frames':frames,'points':smoothed.tolist(),
        'activity':activity.tolist(),'metrics':metrics,'parameters':vars(args)|{'output':str(args.output)},
        'valid_mask':raw['valid_mask'],'source':'sword_combo_001.json; interpolated missing positions only in derived data'}
    with args.output.open('x',encoding='utf-8') as f: json.dump(result,f,allow_nan=False)
    print(json.dumps(metrics,indent=2))


if __name__=='__main__': main()
