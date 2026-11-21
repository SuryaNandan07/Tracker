"""Bounded real-inference sender test; saves only a small validation report."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from mocap.live_protocol import HOST, decode, PacketGate

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--camera',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    report=root/'reports'/('live_camera_test.json' if args.camera else 'live_sender_test.json')
    if report.exists(): raise FileExistsError(report)
    packets=[]; valid=0; gate=PacketGate(); process=None
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind((HOST,0)); sock.settimeout(.1)
        cmd=[sys.executable,'-B','-m','mocap.live_sender','--port',str(sock.getsockname()[1]),
             '--max-frames','30','--max-seconds','8']
        if not args.camera: cmd += ['--video',str(root/'Videos/fighting.webm')]
        process=subprocess.Popen(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+35
        try:
            while time.monotonic()<deadline:
                try:
                    p=decode(sock.recv(32768))
                    assert gate.accept(p,time.monotonic_ns())
                    packets.append(p['sequence']); valid+=int(p['detected'])
                except socket.timeout:
                    if process.poll() is not None: break
            stdout,stderr=process.communicate(timeout=3)
        except BaseException:
            process.kill(); process.wait()
            raise
    data=dict(mode='camera' if args.camera else 'video',packets=len(packets),detections=valid,
        exit_code=process.returncode,stdout=stdout,stderr=stderr,
        passed=process.returncode==0 and len(packets)>0,
        note='Independent actual MediaPipe sender and UDP listener; not an interactive Blender test.')
    with report.open('x') as f: json.dump(data,f,indent=2)
    print(json.dumps(data,indent=2))
    if not data['passed']: raise SystemExit(1)

if __name__=='__main__': main()
