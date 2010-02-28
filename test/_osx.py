import unittest
import subprocess
import time
import re
import sys

import psutil

from test_psutil import kill, PYTHON, DEVNULL
#from _posix import ps


def sysctl(cmdline):
    """Expects a sysctl command with an argument and parse the result
    returning only the value of interest.
    """
    p = subprocess.Popen(cmdline, shell=1, stdout=subprocess.PIPE)
    result = p.communicate()[0].strip().split()[1]
    if sys.version_info >= (3,):
        result = str(result, sys.stdout.encoding)
    try:
        return int(result)
    except ValueError:
        return result


class OSXSpecificTestCase(unittest.TestCase):

    def setUp(self):
        self.pid = subprocess.Popen(PYTHON, stdout=DEVNULL, stderr=DEVNULL).pid

    def tearDown(self):
        kill(self.pid)

    def test_TOTAL_PHYMEM(self):
        sysctl_hwphymem = sysctl('sysctl hw.physmem')
        self.assertEqual(sysctl_hwphymem, psutil.TOTAL_PHYMEM)

    def test_process_create_time(self):
        cmdline = "ps -o lstart -p %s" %self.pid
        p = subprocess.Popen(cmdline, shell=1, stdout=subprocess.PIPE)
        output = p.communicate()[0]
        if sys.version_info >= (3,):
            output = str(output, sys.stdout.encoding)
        start_ps = output.replace('STARTED', '').strip()
        start_psutil = psutil.Process(self.pid).create_time
        start_psutil = time.strftime("%a %b %e %H:%M:%S %Y",
                                     time.localtime(start_psutil))
        self.assertEqual(start_ps, start_psutil)


if __name__ == '__main__':
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(OSXSpecificTestCase))
    unittest.TextTestRunner(verbosity=2).run(test_suite)




