#!/usr/bin/env python
#
# $Id$
#

import unittest
import os
import sys
import subprocess
import time
import signal
import socket
import types
from test import test_support

import psutil


PYTHON = os.path.realpath(sys.executable)
DEVNULL = open(os.devnull, 'r+')


def wait_for_pid(pid, timeout=1):
    """Wait for pid to show up in the process list then return.
    Used in the test suite to give time the sub process to initialize.
    """
    raise_at = time.time() + timeout
    while 1:
        if pid in psutil.get_pid_list():
		    # give it one more iteration to allow full initialization
            time.sleep(0.0001)
            return
        time.sleep(0.0001)
        if time.time() >= raise_at:
            raise RuntimeError("Timed out")


class TestCase(unittest.TestCase):

    def setUp(self):
        self.proc = None

    def tearDown(self):
        if self.proc is not None:
            try:
                if hasattr(os, 'kill'):
                    os.kill(self.proc.pid, signal.SIGKILL)
                else:
                    psutil.Process(self.proc.pid).kill()
            finally:
                self.proc = None

    def test_get_process_list(self):
        pids = [x.pid for x in psutil.get_process_list()]
        if hasattr(os, 'getpid'):
            self.assertTrue(os.getpid() in pids)

    def test_process_iter(self):
        pids = [x.pid for x in psutil.process_iter()]
        if hasattr(os, 'getpid'):
            self.assertTrue(os.getpid() in pids)

    def test_kill(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        test_pid = self.proc.pid
        wait_for_pid(test_pid)
        p = psutil.Process(test_pid)
        name = p.name
        p.kill()
        self.proc.wait()
        self.proc = None
        self.assertFalse(psutil.pid_exists(test_pid) and name == PYTHON)

    def test_pid(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        self.assertEqual(psutil.Process(self.proc.pid).pid, self.proc.pid)

    def test_eq(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        self.assertTrue(psutil.Process(self.proc.pid) == psutil.Process(self.proc.pid))

    def test_is_running(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        p = psutil.Process(self.proc.pid)
        self.assertTrue(p.is_running())
        psutil.Process(self.proc.pid).kill()
        self.proc.wait()
        self.proc = None
##        wait_for_pid(self.proc.pid) # FIXME: why is this needed?
        self.assertFalse(p.is_running())

    def test_pid_exists(self):
        if hasattr(os, 'getpid'):
            self.assertTrue(psutil.pid_exists(os.getpid()))
        self.assertFalse(psutil.pid_exists(-1))

    def test_path(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        self.assertEqual(psutil.Process(self.proc.pid).path, os.path.dirname(PYTHON))

    def test_cmdline(self):
        self.proc = subprocess.Popen([PYTHON, "-E"], stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        self.assertEqual(psutil.Process(self.proc.pid).cmdline, [PYTHON, "-E"])

    def test_name(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL,  stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        self.assertEqual(psutil.Process(self.proc.pid).name, os.path.basename(PYTHON))

    def test_uid(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        uid = psutil.Process(self.proc.pid).uid
        if hasattr(os, 'getuid'):
            self.assertEqual(uid, os.getuid())
        else:
            # On those platforms where UID doesn't make sense (Windows)
            # we expect it to be -1
            self.assertEqual(uid, -1)

    def test_gid(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        wait_for_pid(self.proc.pid)
        gid = psutil.Process(self.proc.pid).gid
        if hasattr(os, 'getgid'):
            self.assertEqual(gid, os.getgid())
        else:
            # On those platforms where GID doesn't make sense (Windows)
            # we expect it to be -1
            self.assertEqual(gid, -1)

    def test_parent_ppid(self):
        this_parent = os.getpid()
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        p = psutil.Process(self.proc.pid)
        self.assertEqual(p.ppid, this_parent)
        self.assertEqual(p.parent.pid, this_parent)

    def test_get_pid_list(self):
        plist = [x.pid for x in psutil.get_process_list()]
        pidlist = psutil.get_pid_list()
        self.assertEqual(plist.sort(), pidlist.sort())
        # make sure every pid is unique
        self.assertEqual(len(pidlist), len(set(pidlist)))

    def test_types(self):
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        p = psutil.Process(self.proc.pid)
        self.assert_(isinstance(p.pid, int))
        self.assert_(isinstance(p.ppid, int))
        self.assert_(isinstance(p.parent, psutil.Process))
        self.assert_(isinstance(p.name, str))
        self.assert_(isinstance(p.path, str))
        self.assert_(isinstance(p.cmdline, list))
        self.assert_(isinstance(p.uid, int))
        self.assert_(isinstance(p.gid, int))
        self.assert_(isinstance(p.is_running(), bool))
        self.assert_(isinstance(psutil.get_process_list(), list))
        self.assert_(isinstance(psutil.get_process_list()[0], psutil.Process))
        self.assert_(isinstance(psutil.process_iter(), types.GeneratorType))
        self.assert_(isinstance(psutil.process_iter().next(), psutil.Process))
        self.assert_(isinstance(psutil.get_pid_list(), list))
        self.assert_(isinstance(psutil.get_pid_list()[0], int))
        self.assert_(isinstance(psutil.pid_exists(1), bool))

    def test_no_such_process(self):
        # Refers to Issue #12
        self.assertRaises(psutil.NoSuchProcess, psutil.Process, -1)

    def test_invalid_pid(self):
        self.assertRaises(ValueError, psutil.Process, "1")

    def test_zombie_process(self):
        # Test that NoSuchProcess exception gets raised in the event the
        # process dies after we create the Process object.
        # Example:
        #  >>> proc = Process(1234)
        #  >>> time.sleep(5)  # time-consuming task, process dies in meantime
        #  >>> proc.name
        # Refers to Issue #15
        self.proc = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL)
        p = psutil.Process(self.proc.pid)
        p.kill()
        self.proc.wait()
        self.proc = None
##        wait_for_pid(self.proc.pid)  # XXX - maybe not necessary; verify

        self.assertRaises(psutil.NoSuchProcess, getattr, p, "ppid")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "parent")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "name")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "path")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "cmdline")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "uid")
        self.assertRaises(psutil.NoSuchProcess, getattr, p, "gid")
        self.assertRaises(psutil.NoSuchProcess, p.kill)

    # XXX - provisional
    def test_fetch_all(self):
        valid_procs = 0
        for p in psutil.process_iter():
            try:
                str(p)
                valid_procs += 1
            except psutil.NoSuchProcess, psutil.AccessDenied:
                continue
        
        # we should always have a non-empty list, not including PID 0 etc. 
        # special cases.
        self.assertTrue(valid_procs > 2)

    def test_pid_0(self):
        # Process(0) is supposed to work on all platforms even if with
        # some differences
        p = psutil.Process(0)
        if sys.platform.lower().startswith("win32"):
            self.assertEqual(p.name, 'System Idle Process')
        elif sys.platform.lower().startswith("linux"):
            self.assertEqual(p.name, 'sched')
        elif sys.platform.lower().startswith("freebsd"):
            self.assertEqual(p.name, 'swapper')
        elif sys.platform.lower().startswith("darwin"):
            self.assertEqual(p.name, 'kernel_task')

        # use __str__ to access all common Process properties to check
        # that nothing strange happens
        str(p)

        # PID 0 is supposed to be available on all platforms
        self.assertTrue(0 in psutil.get_pid_list())
        self.assertTrue(psutil.pid_exists(0))


    # --- OS specific tests

    # UNIX specific tests

    if not sys.platform.lower().startswith("win32"):

        if hasattr(os, 'getuid') and os.getuid() > 0:
            def test_unix_access_denied(self):
                p = psutil.Process(1)
                self.assertRaises(psutil.AccessDenied, p.kill)

    # Windows specific tests

    if sys.platform.lower().startswith("win32"):

        def test_windows_issue_24(self):
            p = psutil.Process(0)
            self.assertRaises(psutil.AccessDenied, p.kill)


def test_main():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TestCase))
    unittest.TextTestRunner(verbosity=2).run(test_suite)
    if hasattr(test_support, "reap_children"):  # python 2.5 and >
        test_support.reap_children()
    DEVNULL.close()

if __name__ == '__main__':
    test_main()

