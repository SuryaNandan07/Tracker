"""Blender background integration test and exclusive new-file creation."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
import live_receiver as live
from mocap.live_protocol import encode, HOST
from retarget_mixamo import action_snapshot, digest, rig_snapshot, evaluated_mesh, matrix

output=ROOT/'blender_projects/experiments/Humanoid_Live_Mocap.blend'
report_path=ROOT/'reports/live_mocap_validation.json'
if output.exists() or report_path.exists():
    raise FileExistsError('Refusing to overwrite live project/report')
source=Path(bpy.data.filepath)
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
ref,target=live.validate_scene()
refmesh=bpy.data.objects['Ch44']; mesh=bpy.data.objects['Ch44.001']
before_actions={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
before_rigs=[rig_snapshot(ref,refmesh),rig_snapshot(target,mesh)]
before_pose={p.name:(p.rotation_mode,matrix(p.matrix_basis)) for p in target.pose.bones}
before_ref_pose=[matrix(p.matrix) for p in ref.pose.bones]
before_ref_mesh=evaluated_mesh(refmesh)
original_action=target.animation_data.action
original_action_name=original_action.name
original_slot=target.animation_data.action_slot
transform=matrix(target.matrix_world)
source_data=json.loads((ROOT/'exports/sword_combo_001.json').read_text())
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
    probe.bind((HOST,0)); port=probe.getsockname()[1]
movement=0.; max_tick=0.
initial_mesh=evaluated_mesh(mesh)
receiver=live.start(port=port)
try:
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        def send(p):
            sender.sendto(encode(p),(HOST,port))
            start=time.perf_counter(); receiver.tick()
            return time.perf_counter()-start
        sender.sendto(b'{invalid',(HOST,port)); receiver.tick()
        assert receiver.bad==1
        for i in range(0,572,4):
            raw=source_data['world_landmarks'][i]
            points=[p if all(v is not None for v in p) else None for p in raw]
            confidence=[v if v is not None else 0 for v in source_data['visibility'][i]]
            p=dict(version=1,session='integration',sequence=i,timestamp_ns=time.monotonic_ns(),
                detected=source_data['valid_mask'][i],world=points,confidence=confidence)
            max_tick=max(max_tick,send(p))
            bpy.context.view_layer.update()
            assert [matrix(p.matrix) for p in ref.pose.bones]==before_ref_pose
            assert matrix(target.matrix_world)==transform
            if i % 100==0:
                assert evaluated_mesh(refmesh)==before_ref_mesh
                moved=evaluated_mesh(mesh)
                movement=max(movement,max(sum((a-b)**2 for a,b in zip(v,w))**.5 for v,w in zip(initial_mesh,moved)))
        before=[matrix(p.matrix_basis) for p in target.pose.bones]
        missing=p|dict(sequence=600,timestamp_ns=time.monotonic_ns(),detected=False,world=[None]*33,confidence=[0]*33)
        send(missing)
        assert before==[matrix(p.matrix_basis) for p in target.pose.bones]
        bad=receiver.bad
        send(missing)
        send(missing|dict(sequence=601,timestamp_ns=time.monotonic_ns()-2_000_000_000))
        assert receiver.bad==bad+2
        assert receiver.updated > 20 and movement > .01
        live.set_smoothing(.06)
        metrics=live.status()
finally:
    live.stop()
bpy.context.view_layer.update()
assert not bpy.app.timers.is_registered(receiver.callback)
assert target.animation_data.action==original_action and target.animation_data.action_slot==original_slot
assert before_pose=={p.name:(p.rotation_mode,matrix(p.matrix_basis)) for p in target.pose.bones}
for _ in range(3):
    r=live.start(port=port); live.stop(); live.stop()
    assert not bpy.app.timers.is_registered(r.callback)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
    probe.bind((HOST,port))
assert before_actions=={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
assert before_rigs==[rig_snapshot(ref,refmesh),rig_snapshot(target,mesh)]
assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
text=bpy.data.texts.new('LIVE_MOCAP_START.py')
text.write("# Run this text to start. Pause Timeline; do not press Play.\n"
    "import sys\n"
    f"sys.path.insert(0, {str(ROOT/'blender')!r})\n"
    "import live_receiver as live\n"
    "live.start()\n"
    "# Console: import live_receiver as live; live.status()\n"
    "# live.stop() restores the original pose and Action.\n")
output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output))
bpy.ops.wm.open_mainfile(filepath=str(output),load_ui=False,use_scripts=False)
ref,target=live.validate_scene()
assert before_actions=={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
assert before_rigs==[rig_snapshot(ref,bpy.data.objects['Ch44']),rig_snapshot(target,bpy.data.objects['Ch44.001'])]
assert target.animation_data.action.name==original_action_name
report=dict(blender=bpy.app.version_string,source=str(source),output=str(output),source_sha256=source_hash,
    rig_names=[ref.name,target.name],mesh_names=['Ch44','Ch44.001'],mapped_bones=live.MAPPED,
    test_packets=metrics,max_manual_tick_ms=max_tick*1000,target_mesh_displacement=movement,
    actions_unchanged=True,reference_unchanged=True,pose_restored=True,root_transform_unchanged=True,
    repeated_start_stop=3,reopened=True,
    interactive_viewport_tested=False,notes='Background main-thread tick/network tests; no interactive latency measurement.')
report_path.parent.mkdir(parents=True,exist_ok=True)
with report_path.open('x') as f: json.dump(report,f,indent=2)
print('PASS LIVE',json.dumps(report),flush=True)
