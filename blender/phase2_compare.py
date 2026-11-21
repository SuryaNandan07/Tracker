"""Reopen the new file and compare evaluated wrist trajectories against its preserved Action."""
import argparse
import sys
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(); parser.add_argument('--preset',required=True); args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
p=ROOT/'blender'/f'phase2_{args.preset}_validation.json'; report=json.loads(p.read_text())
assert hashlib.sha256((ROOT/'Humanoid_Mocap_Smoothed.blend').read_bytes()).hexdigest()==report['source_hash']
target=bpy.data.objects['Character_MOCAP_TEST']; ref=bpy.data.objects['Character_REFERENCE']
assert target.data!=ref.data
assert target.animation_data.action.name==report['new_action']
scene=bpy.context.scene
data=json.loads((ROOT/'exports'/'phase2'/f'{args.preset}.json').read_text())
frames=data['frames']; times=[t/1000 for t in data['timestamps_ms']]
sys.path.insert(0,str(ROOT/'blender'))
from retarget_mixamo import evaluated_mesh,action_snapshot,digest
refmesh=bpy.data.objects['Ch44']; mesh=bpy.data.objects['Ch44.001']
scene.frame_set(1); ref_geometry=evaluated_mesh(refmesh)
all_actions_before={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
mesh_samples=[]
positions={}
for label,name in [('before',report['original_action']),('after',report['new_action'])]:
    action=bpy.data.actions[name]
    target.animation_data.action=action; target.animation_data.action_slot=action.slots[0]
    tracks=[[],[]]
    for index,frame in enumerate(frames):
        scene.frame_set(math.floor(frame),subframe=frame%1)
        if label=='after' and index in (0,100,200,300,400,571):
            assert evaluated_mesh(refmesh)==ref_geometry
            mesh_samples.append(evaluated_mesh(mesh))
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
assert all(digest(action_snapshot(bpy.data.actions[n]))==h for n,h in all_actions_before.items())
movement=max((Vector(a)-Vector(b)).length for row in mesh_samples[1:] for a,b in zip(row,mesh_samples[0]))
assert movement>.05
report['target_mesh_max_displacement_m']=movement
report['reference_mesh_unchanged_at_six_checks']=True
report['all_existing_action_keyframes_preserved']=True
report['saved_file_reopened']=True
report['evaluated_wrist_motion']=metrics
destination=ROOT/'blender'/f'phase2_{args.preset}_checked.json'
with destination.open('x') as f: json.dump(report,f,indent=2)
print(args.preset,json.dumps(metrics))
print('Reopened successfully; original/new Actions present and source file unchanged.')
