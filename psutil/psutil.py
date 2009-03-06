#!/usr/bin/env python
#
# $Id$
#

"""psutil is a module providing convenience functions for managing
processes in a portable way by using Python.
"""

import sys
import os
try:
    import pwd, grp
except ImportError:
    pwd = grp = None


# this exception get overriden by the platform specific modules if necessary
class NoSuchProcess(Exception):
    """No process was found for the given parameters."""

class AccessDenied(Exception):
    """Exception raised when permission to perform an action is denied."""


# the linux implementation has the majority of it's functionality
# implemented in python via /proc
if sys.platform.lower().startswith("linux"):
    from _pslinux import *

# the windows implementation requires the _psutil_mswindows C module
elif sys.platform.lower().startswith("win32"):
    from _psmswindows import *

# OS X implementation requires _psutil_osx C module
elif sys.platform.lower().startswith("darwin"):
    from _psosx import *

# BSD implementation requires _psutil_bsd C module
elif sys.platform.lower().startswith("freebsd"):
    from _psbsd import *
else:
    raise ImportError('no os specific module found')

_platform_impl = Impl()


class ProcessInfo(object):
    """Class that allows the process information to be passed
    between external code and psutil.  Used directly by the
    Process class.
    """

    def __init__(self, pid, ppid=None, name=None, path=None, cmdline=None,
                       uid=None, gid=None):
        self.pid = pid
        self.ppid = ppid
        self.name = name
        self.path = path
        self.cmdline = cmdline
        # if we have the cmdline but not the path, figure it out from argv[0]
        if cmdline and not path:
            self.path = os.path.dirname(cmdline[0])
        self.uid = uid
        self.gid = gid


class Process(object):
    """Represents an OS process."""

    def __init__(self, pid):
        """Create a new Process object, raises NoSuchProcess if the PID does
        not exist, and ValueError if the parameter is not an integer PID."""
        if not isinstance(pid, int):
            raise ValueError("An integer is required")
        if not pid_exists(pid):
            raise NoSuchProcess("No process found with PID %s" % pid)
        self._procinfo = ProcessInfo(pid)
        self.is_proxy = True

    def __str__(self):
        return "psutil.Process <PID:%s; PPID:%s; NAME:'%s'; PATH:'%s'; " \
               "CMDLINE:%s; UID:%s; GID:%s;>" \
               %(self.pid, self.ppid, self.name, self.path, self.cmdline, \
                 self.uid, self.gid)

    def __eq__(self, other):
        """Test for equality with another Process object based on PID,
        name etc."""
        if self.pid != other.pid:
            return False

        # make sure both objects are initialized
        self.deproxy()
        other.deproxy()
        # check all non-callable and non-private attributes for equality
        # if the attribute is missing from other then return False
        for attr in dir(self):
            attrobj = getattr(self, attr)
            # skip private attributes
            if attr.startswith("_"):
                continue 
            
            # skip methods and Process objects 
            if callable(attrobj) or isinstance(attrobj, Process):
                continue
            
            # attribute doesn't exist or isn't equal, so return False
            if not hasattr(other, attr):
                return False
            if getattr(self, attr) != getattr(other, attr):
                return False
                
        return True

    def deproxy(self):
        """Used internally by Process properties. The first call to deproxy()
        initializes the ProcessInfo object in self._procinfo with process data
        read from platform-specific module's get_process_info() method. 
        
        This method becomes a NO-OP after the first property is accessed. 
        Property data is filled in from the ProcessInfo object created, and
        further calls to deproxy() simply return immediately without calling
        get_process_info()."""
        if self.is_proxy:
            self._procinfo = _platform_impl.get_process_info(self._procinfo.pid)
            self.is_proxy = False

    @property
    def pid(self):
        """The process pid."""
        return self._procinfo.pid

    @property
    def ppid(self):
        """The process parent pid."""
        self.deproxy()
        return self._procinfo.ppid

    @property
    def parent(self):
        """Return the parent process as a Process object. If no ppid is known
        then return None."""
        if self.ppid is not None:
            return Process(self.ppid)
        return None

    @property
    def name(self):
        """The process name."""
        self.deproxy()
        return self._procinfo.name

    @property
    def path(self):
        """The process path."""
        self.deproxy()
        return self._procinfo.path

    @property
    def cmdline(self):
        """The command line process has been called with."""
        self.deproxy()
        return self._procinfo.cmdline

    @property
    def uid(self):
        """The real user id of the current process."""
        self.deproxy()
        return self._procinfo.uid

    @property
    def gid(self):
        """The real group id of the current process."""
        self.deproxy()
        return self._procinfo.gid

    def is_running(self):
        """Return whether the current process is running in the current process
        list."""
        try:
            new_proc = Process(self.pid)
            # calls get_process_info() which may in turn trigger NSP exception
            str(new_proc)
        except NoSuchProcess:
            return False
        return (self == new_proc)

    def kill(self, sig=None):
        """Kill the current process by using signal sig (defaults to SIGKILL).
        """
        _platform_impl.kill_process(self.pid, sig)


def pid_exists(pid):
    """Check whether the given PID exists in the current process list."""
    return _platform_impl.pid_exists(pid)

def get_pid_list():
    """Return a list of current running PIDs."""
    return _platform_impl.get_pid_list()

def process_iter():
    """Return an iterator yielding a Process class instances for all
    running processes on the local machine.
    """
    pids = _platform_impl.get_pid_list();
    # for each PID, create a proxyied Process object
    # it will lazy init it's name and path later if required
    for pid in pids:
        try:
            yield Process(pid)
        except (NoSuchProcess, AccessDenied):
            continue

def get_process_list():
    """Return a list of Process class instances for all running
    processes on the local machine.
    """
    return list(process_iter())


def test():
    processes = get_process_list()
    print "%-5s  %-5s %-15s %-25s %-20s %-5s %-5s %-5s %-5s" \
          %("PID", "PPID", "NAME", "PATH", "COMMAND LINE", "UID", "GID")
    for proc in processes:
        print "%-5s  %-5s %-15s %-25s %-20s %-5s %-5s" \
              %(proc.pid, proc.ppid, proc.name, proc.path or "<unknown>", \
              ' '.join(proc.cmdline) or "<unknown>", proc.uid, proc.gid)

if __name__ == "__main__":
    test()

