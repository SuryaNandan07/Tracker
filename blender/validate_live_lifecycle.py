"""Additional live safety checks; never saves or modifies a project on disk."""
import json
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
import live_receiver as live
from retarget_mixamo import digest, action_snapshot

before={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
target=bpy.data.objects['Character_MOCAP_TEST']; action=target.animation_data.action
r=live.start(port=0)
assert bpy.app.timers.is_registered(r.callback)
assert target.animation_data.action is None
# Exercise the exact handler called before Save or opening another project.
live.cleanup_before_file_change(None)
assert not r.active and not bpy.app.timers.is_registered(r.callback)
assert target.animation_data.action==action
assert live.cleanup_before_file_change not in bpy.app.handlers.save_pre
assert live.cleanup_before_file_change not in bpy.app.handlers.load_pre
r=live.start(port=0)
# Simulate a fatal socket failure. The timer must restore the Action and unregister.
r.socket.close(); assert r.tick() is None
assert not r.active and target.animation_data.action==action
assert not bpy.app.timers.is_registered(r.callback)
assert before=={a.name:digest(action_snapshot(a)) for a in bpy.data.actions}
with (ROOT/'reports/live_lifecycle_test.json').open('x') as f:
    json.dump(dict(save_load_cleanup=True,error_cleanup=True,actions_unchanged=True,
                   registered_timer_cleanup=True,blender=bpy.app.version_string),f,indent=2)
print('PASS lifecycle: file-change cleanup, exception cleanup, timers, original Actions')
