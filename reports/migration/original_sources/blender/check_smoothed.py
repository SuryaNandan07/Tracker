"""Reopen the new file and compare evaluated wrist trajectories against its preserved Action."""
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'blender'/'smoothing_validation.json'; report=json.loads(p.read_text())
assert hashlib.sha256((ROOT/'Humanoid_Mocap_Result.blend').read_bytes()).hexdigest()==report['source_hash']
target=bpy.data.objects['Character_MOCAP_TEST']; ref=bpy.data.objects['Character_REFERENCE']
assert target.data!=ref.data
assert target.animation_data.action.name==report['new_action']
scene=bpy.context.scene
data=json.loads((ROOT/'exports'/'sword_combo_smoothed.json').read_text())
frames=data['frames']; times=[t/1000 for t in data['timestamps_ms']]
positions={}
for label,name in [('before',report['original_action']),('after',report['new_action'])]:
    action=bpy.data.actions[name]
    target.animation_data.action=action; target.animation_data.action_slot=action.slots[0]
    tracks=[[],[]]
    for frame in frames:
        scene.frame_set(math.floor(frame),subframe=frame%1)
        for j,bone in enumerate(('mixamorig:LeftHand','mixamorig:RightHand')):
            tracks[j].append(target.matrix_world @ target.pose.bones[bone].head)
    positions[label]=tracks
speed={label:[[((track[i+1]-track[i-1])/(times[i+1]-times[i-1])).length
                for i in range(1,len(times)-1)] for track in tracks] for label,tracks in positions.items()}
metrics={}
for j,side in enumerate(('left','right')):
    a,b=speed['before'][j],speed['after'][j]
    peaks=[]
    for i in sorted(range(len(a)),key=lambda k:a[k],reverse=True):
        if all(abs(i-k)>20 for k in peaks): peaks.append(i)
        if len(peaks)==5: break
    events=[]
    for i in sorted(peaks):
        k=max(range(max(0,i-3),min(len(b),i+4)),key=lambda k:b[k])
        events.append({'source_time_s':times[i+1],'before_m_s':a[i],'after_m_s':b[k],
                       'peak_shift_ms':1000*(times[k+1]-times[i+1]),'speed_ratio':b[k]/a[i]})
    errors={lag:sum((a[i]-b[i+lag])**2 for i in range(4,len(a)-4)) for lag in range(-3,4)}
    metrics[side]={'events':events,'best_speed_alignment_lag_samples':min(errors,key=errors.get)}
report['saved_file_reopened']=True
report['evaluated_wrist_motion']=metrics
p.write_text(json.dumps(report,indent=2))
print(json.dumps(metrics,indent=2))
print('Reopened successfully; original/new Actions present and source file unchanged.')
