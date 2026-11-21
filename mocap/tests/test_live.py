import json
import socket
import time
import unittest
import numpy as np
from mocap.live_protocol import decode, encode, PacketGate, HOST
from mocap.live_sender import CausalFilter


def packet():
    return dict(version=1, session='test', sequence=0, timestamp_ns=time.monotonic_ns(),
                detected=True, world=[[0.,1.,2.]]*33, confidence=[.9]*33)


class LiveTests(unittest.TestCase):
    def test_udp_roundtrip(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as recv, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as send:
            recv.bind((HOST,0)); recv.settimeout(1)
            p=packet(); send.sendto(encode(p),recv.getsockname())
            self.assertEqual(decode(recv.recv(32768)),p)

    def test_invalid_packets(self):
        for change in ({'world':[[float('nan'),0,0]]*33}, {'confidence':[-1]*33},
                       {'sequence':True}, {'timestamp_ns':-1}, {'world':[]}, {'version':9},
                       {'detected':False}, {'world':[[99,0,0]]*33}):
            with self.assertRaises(ValueError):
                decode(json.dumps(packet()|change).encode())
        for payload in (b'no',b'null',b'[]',b'\xff',b' '*32769):
            with self.assertRaises(ValueError): decode(payload)

    def test_gate_reordering_age_restart(self):
        p=packet(); gate=PacketGate(); now=p['timestamp_ns']
        self.assertTrue(gate.accept(p,now))
        self.assertFalse(gate.accept(p,now))
        self.assertFalse(gate.accept(p|{'sequence':1},now+1_000_000_000))
        self.assertTrue(gate.accept(p|{'session':'new','timestamp_ns':now+1},now+1))
        self.assertFalse(gate.accept(p|{'sequence':10,'timestamp_ns':now+2},now+2))

    def test_causal_filter_missing_and_immutability(self):
        f=CausalFilter(beta=0)
        p=np.ones((33,3)); s=dict(world_landmarks=p,visibility=np.ones(33),valid_mask=True)
        first,_=f.update(s,1.)
        self.assertEqual(first,p.tolist())
        s['world_landmarks']=p*2
        second,_=f.update(s,1.03)
        self.assertTrue(1 < second[0][0] < 2)
        np.testing.assert_equal(p,np.ones((33,3)))
        s['valid_mask']=False
        points,scores=f.update(s,1.04)
        self.assertEqual(points,[None]*33)
        decode(encode(packet()|dict(world=points,confidence=scores,detected=False)))
        s['valid_mask']=True
        self.assertEqual(f.update(s,2.)[0],(p*2).tolist())


if __name__=='__main__': unittest.main()
