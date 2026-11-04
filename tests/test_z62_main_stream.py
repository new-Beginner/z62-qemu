"""Cadence and actual MAIN ABI checks; no simulated completion or camera IO."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from z62_main_stream import FrameCadence,MainTemplate,AuditedMailbox,reconstruct
from z62_main_frame import parse_packet


class MainStreamTests(unittest.TestCase):
    def test_actual_time_determines_frame_without_initial_credit(self):
        cadence=FrameCadence();proposal=cadence.suggest(1_500_000_000)
        self.assertEqual(proposal,{'publication':1,'frame':45,'time_ns':1_500_000_000})
        self.assertEqual(cadence.publication,0);cadence.accept(proposal)
        self.assertIsNone(cadence.suggest(1_500_000_001))

    def test_backpressure_and_pause_never_queue_a_burst(self):
        cadence=FrameCadence();cadence.accept(cadence.suggest(0))
        self.assertIsNone(cadence.suggest(1_000_000_000,False))
        proposal=cadence.suggest(2_000_000_000);cadence.accept(proposal)
        self.assertEqual((cadence.publication,cadence.skipped),(2,59))
        self.assertIsNone(cadence.suggest(2_000_000_000))

    def test_backward_clock_or_stale_proposal_rejected(self):
        cadence=FrameCadence();proposal=cadence.suggest(1_000_000_000);cadence.accept(proposal)
        with self.assertRaises(ValueError):cadence.suggest(999_999_999)
        with self.assertRaises(ValueError):cadence.accept(proposal)

    def test_cached_payload_generates_valid_independent_headers(self):
        template=MainTemplate(14,10,(40,80,160))
        a=template.packet(0x97,1,1_000_000_000);b=template.packet(0x97,2,1_033_333_334)
        self.assertEqual(a[96:],b[96:]);self.assertNotEqual(a[:96],b[:96])
        meta,_=parse_packet(b);self.assertEqual((meta.epoch,meta.publish_id,meta.frame_id),(0x97,2,31))

    def test_two_mailboxes_retain_every_packet_in_the_audit(self):
        root=Path('Q:/.runtime/tmp');self.assertTrue(root.is_dir())
        with tempfile.TemporaryDirectory(prefix='main-stream-',dir=root) as temporary:
            directory=Path(temporary)/'stream';source=AuditedMailbox(directory);cadence=FrameCadence();rows=[]
            for now in (0,33_333_334,66_666_667,100_000_000):
                proposal=cadence.suggest(now);path,row=source.prepare(proposal,14,10,proposal['publication']%2)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['packet_sha256'])
                rows.append(row);cadence.accept(proposal)
            self.assertEqual(len(list(directory.glob('mailbox-*.z62m'))),2)
            for row in rows:self.assertEqual(parse_packet(reconstruct(directory,row))[0].publish_id,row['publication'])


if __name__=='__main__':unittest.main()
