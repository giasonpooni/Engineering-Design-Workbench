"""Actual OS pipes and child cleanup; no claim of scientific native execution."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

from ciw.persistent_native import FramedProcess
from ciw.adapters.protocol import AdapterRefusal

ECHO = r'''
import sys, struct
while True:
    h=sys.stdin.buffer.read(4)
    if not h: break
    n=struct.unpack('>I',h)[0]
    raw=sys.stdin.buffer.read(n)
    sys.stdout.buffer.write(h+raw);sys.stdout.buffer.flush()
'''

class PipeTests(unittest.TestCase):
    def process(self, code, timeout=2):
        return FramedProcess([sys.executable, "-u", "-c", code], cwd=os.getcwd(), env=os.environ.copy(), timeout=timeout)

    def test_multiple_requests_one_process(self):
        p = self.process(ECHO)
        try:
            pid = p.process.pid
            for value in (b'A', b'B', b'A'):
                self.assertEqual(p.exchange(value), value)
                self.assertEqual(p.process.pid, pid)
        finally: p.close()
        self.assertIsNotNone(p.process.poll())

    def test_timeout_and_blocked_write_terminate_child(self):
        p = self.process("import time; time.sleep(30)", timeout=.15)
        with self.assertRaises(AdapterRefusal): p.exchange(b'x'*500000)
        self.assertTrue(p.closed)
        self.assertIsNotNone(p.process.poll())

    def test_truncated_frame_refused(self):
        p = self.process("import sys;sys.stdin.buffer.read(4);sys.stdout.buffer.write(b'\\0\\0\\0\\x09x');sys.stdout.buffer.flush()")
        with self.assertRaises(AdapterRefusal): p.exchange(b'{}')
        self.assertTrue(p.closed)

    def test_oversized_output_refused(self):
        p = self.process("import sys,struct;sys.stdin.buffer.read(4);sys.stdout.buffer.write(struct.pack('>I',5000000));sys.stdout.buffer.flush()")
        with self.assertRaises(AdapterRefusal): p.exchange(b'{}')

    def test_diagnostics_bound_is_not_unbounded_memory(self):
        p = self.process("import sys,time;sys.stdin.buffer.read(4);sys.stderr.buffer.write(b'x'*100000);sys.stderr.buffer.flush();time.sleep(30)")
        with self.assertRaises(AdapterRefusal): p.exchange(b'{}')
        self.assertLessEqual(len(p.stderr), 65536)

    def test_closed_channel_cannot_restart_silently(self):
        p = self.process(ECHO); p.close()
        with self.assertRaises(AdapterRefusal): p.exchange(b'{}')

if __name__ == '__main__': unittest.main()
