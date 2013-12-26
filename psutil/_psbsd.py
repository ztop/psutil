#!/usr/bin/env python

# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""FreeBSD platform implementation."""

import errno
import os
import sys

from psutil import _common
from psutil import _psposix
from psutil._common import (conn_tmap, usage_percent)
from psutil._common import (nt_proc_conn, nt_proc_cpu, nt_proc_ctxsw,
                            nt_proc_file, nt_proc_gids, nt_proc_mem,
                            nt_proc_io, nt_proc_thread, nt_proc_uids,
                            nt_sys_diskpart, nt_sys_swap, nt_sys_user,
                            nt_sys_vmem)
from psutil._compat import namedtuple, wraps
from psutil._error import AccessDenied, NoSuchProcess, TimeoutExpired
import _psutil_bsd as cext
import _psutil_posix


__extra__all__ = []

# --- constants

PROC_STATUSES = {
    cext.SSTOP: _common.STATUS_STOPPED,
    cext.SSLEEP: _common.STATUS_SLEEPING,
    cext.SRUN: _common.STATUS_RUNNING,
    cext.SIDL: _common.STATUS_IDLE,
    cext.SWAIT: _common.STATUS_WAITING,
    cext.SLOCK: _common.STATUS_LOCKED,
    cext.SZOMB: _common.STATUS_ZOMBIE,
}

TCP_STATUSES = {
    cext.TCPS_ESTABLISHED: _common.CONN_ESTABLISHED,
    cext.TCPS_SYN_SENT: _common.CONN_SYN_SENT,
    cext.TCPS_SYN_RECEIVED: _common.CONN_SYN_RECV,
    cext.TCPS_FIN_WAIT_1: _common.CONN_FIN_WAIT1,
    cext.TCPS_FIN_WAIT_2: _common.CONN_FIN_WAIT2,
    cext.TCPS_TIME_WAIT: _common.CONN_TIME_WAIT,
    cext.TCPS_CLOSED: _common.CONN_CLOSE,
    cext.TCPS_CLOSE_WAIT: _common.CONN_CLOSE_WAIT,
    cext.TCPS_LAST_ACK: _common.CONN_LAST_ACK,
    cext.TCPS_LISTEN: _common.CONN_LISTEN,
    cext.TCPS_CLOSING: _common.CONN_CLOSING,
    cext.PSUTIL_CONN_NONE: _common.CONN_NONE,
}

PAGESIZE = os.sysconf("SC_PAGE_SIZE")

# extend base mem ntuple with BSD-specific memory metrics
nt_sys_vmem = namedtuple(
    nt_sys_vmem.__name__,
    list(nt_sys_vmem._fields) + ['active', 'inactive', 'buffers', 'cached'
                                 'shared', 'wired'])

nt_sys_cputimes = namedtuple(
    'cputimes', ['user', 'nice', 'system', 'idle', 'irq'])

nt_proc_extmem = namedtuple('meminfo', ['rss', 'vms', 'text', 'data', 'stack'])


def virtual_memory():
    """System virtual memory as a namedutple."""
    mem = cext.get_virtual_mem()
    total, free, active, inactive, wired, cached, buffers, shared = mem
    avail = inactive + cached + free
    used = active + wired + cached
    percent = usage_percent((total - avail), total, _round=1)
    return nt_sys_vmem(total, avail, percent, used, free,
                       active, inactive, buffers, cached, shared, wired)


def swap_memory():
    """System swap memory as (total, used, free, sin, sout) namedtuple."""
    total, used, free, sin, sout = [x * PAGESIZE for x in cext.get_swap_mem()]
    percent = usage_percent(used, total, _round=1)
    return nt_sys_swap(total, used, free, percent, sin, sout)


def get_sys_cpu_times():
    """Return system per-CPU times as a named tuple"""
    user, nice, system, idle, irq = cext.get_sys_cpu_times()
    return nt_sys_cputimes(user, nice, system, idle, irq)


if hasattr(cext, "get_sys_per_cpu_times"):
    def get_sys_per_cpu_times():
        """Return system CPU times as a named tuple"""
        ret = []
        for cpu_t in cext.get_sys_per_cpu_times():
            user, nice, system, idle, irq = cpu_t
            item = nt_sys_cputimes(user, nice, system, idle, irq)
            ret.append(item)
        return ret
else:
    # XXX
    # Ok, this is very dirty.
    # On FreeBSD < 8 we cannot gather per-cpu information, see:
    # http://code.google.com/p/psutil/issues/detail?id=226
    # If num cpus > 1, on first call we return single cpu times to avoid a
    # crash at psutil import time.
    # Next calls will fail with NotImplementedError
    def get_sys_per_cpu_times():
        if get_num_cpus() == 1:
            return [get_sys_cpu_times]
        if get_sys_per_cpu_times.__called__:
            raise NotImplementedError("supported only starting from FreeBSD 8")
        get_sys_per_cpu_times.__called__ = True
        return [get_sys_cpu_times]

    get_sys_per_cpu_times.__called__ = False


def get_num_cpus():
    """Return the number of logical CPUs in the system."""
    return cext.get_num_cpus()


def get_num_phys_cpus():
    """Return the number of physical CPUs in the system."""
    # From the C module we'll get an XML string similar to this:
    # http://manpages.ubuntu.com/manpages/precise/man4/smp.4freebsd.html
    # We may get None in case "sysctl kern.sched.topology_spec"
    # is not supported on this BSD version, in which case we'll mimic
    # os.cpu_count() and return None.
    s = cext.get_num_phys_cpus()
    if s is not None:
        # get rid of padding chars appended at the end of the string
        index = s.rfind("</groups>")
        if index != -1:
            s = s[:index + 9]
            if sys.version_info >= (2, 5):
                import xml.etree.ElementTree as ET
                root = ET.fromstring(s)
                return len(root.findall('group/children/group/cpu')) or None
            else:
                s = s[s.find('<children>'):]
                return s.count("<cpu") or None


def get_boot_time():
    """The system boot time expressed in seconds since the epoch."""
    return cext.get_boot_time()


def disk_partitions(all=False):
    retlist = []
    partitions = cext.get_disk_partitions()
    for partition in partitions:
        device, mountpoint, fstype, opts = partition
        if device == 'none':
            device = ''
        if not all:
            if not os.path.isabs(device) or not os.path.exists(device):
                continue
        ntuple = nt_sys_diskpart(device, mountpoint, fstype, opts)
        retlist.append(ntuple)
    return retlist


def get_users():
    retlist = []
    rawlist = cext.get_users()
    for item in rawlist:
        user, tty, hostname, tstamp = item
        if tty == '~':
            continue  # reboot or shutdown
        nt = nt_sys_user(user, tty or None, hostname, tstamp)
        retlist.append(nt)
    return retlist


get_pids = cext.get_pids
pid_exists = _psposix.pid_exists
get_disk_usage = _psposix.get_disk_usage
net_io_counters = cext.get_net_io_counters
disk_io_counters = cext.get_disk_io_counters


def wrap_exceptions(fun):
    """Decorator which translates bare OSError exceptions into
    NoSuchProcess and AccessDenied.
    """
    @wraps(fun)
    def wrapper(self, *args, **kwargs):
        try:
            return fun(self, *args, **kwargs)
        except OSError:
            err = sys.exc_info()[1]
            if err.errno == errno.ESRCH:
                raise NoSuchProcess(self.pid, self._process_name)
            if err.errno in (errno.EPERM, errno.EACCES):
                raise AccessDenied(self.pid, self._process_name)
            raise
    return wrapper


class Process(object):
    """Wrapper class around underlying C implementation."""

    __slots__ = ["pid", "_process_name"]

    def __init__(self, pid):
        self.pid = pid
        self._process_name = None

    @wrap_exceptions
    def get_name(self):
        """Return process name as a string of limited len (15)."""
        return cext.get_proc_name(self.pid)

    @wrap_exceptions
    def get_exe(self):
        """Return process executable pathname."""
        return cext.get_proc_exe(self.pid)

    @wrap_exceptions
    def get_cmdline(self):
        """Return process cmdline as a list of arguments."""
        return cext.get_proc_cmdline(self.pid)

    @wrap_exceptions
    def get_terminal(self):
        tty_nr = cext.get_proc_tty_nr(self.pid)
        tmap = _psposix._get_terminal_map()
        try:
            return tmap[tty_nr]
        except KeyError:
            return None

    @wrap_exceptions
    def get_ppid(self):
        """Return process parent pid."""
        return cext.get_proc_ppid(self.pid)

    @wrap_exceptions
    def get_uids(self):
        """Return real, effective and saved user ids."""
        real, effective, saved = cext.get_proc_uids(self.pid)
        return nt_proc_uids(real, effective, saved)

    @wrap_exceptions
    def get_gids(self):
        """Return real, effective and saved group ids."""
        real, effective, saved = cext.get_proc_gids(self.pid)
        return nt_proc_gids(real, effective, saved)

    @wrap_exceptions
    def get_cpu_times(self):
        """return a tuple containing process user/kernel time."""
        user, system = cext.get_proc_cpu_times(self.pid)
        return nt_proc_cpu(user, system)

    @wrap_exceptions
    def get_memory_info(self):
        """Return a tuple with the process' RSS and VMS size."""
        rss, vms = cext.get_proc_memory_info(self.pid)[:2]
        return nt_proc_mem(rss, vms)

    @wrap_exceptions
    def get_ext_memory_info(self):
        return nt_proc_extmem(*cext.get_proc_memory_info(self.pid))

    @wrap_exceptions
    def get_create_time(self):
        """Return the start time of the process as a number of seconds since
        the epoch."""
        return cext.get_proc_create_time(self.pid)

    @wrap_exceptions
    def get_num_threads(self):
        """Return the number of threads belonging to the process."""
        return cext.get_proc_num_threads(self.pid)

    @wrap_exceptions
    def get_num_ctx_switches(self):
        return nt_proc_ctxsw(*cext.get_proc_num_ctx_switches(self.pid))

    @wrap_exceptions
    def get_threads(self):
        """Return the number of threads belonging to the process."""
        rawlist = cext.get_proc_threads(self.pid)
        retlist = []
        for thread_id, utime, stime in rawlist:
            ntuple = nt_proc_thread(thread_id, utime, stime)
            retlist.append(ntuple)
        return retlist

    @wrap_exceptions
    def get_connections(self, kind='inet'):
        """Return etwork connections opened by a process as a list of
        namedtuples.
        """
        if kind not in conn_tmap:
            raise ValueError("invalid %r kind argument; choose between %s"
                             % (kind, ', '.join([repr(x) for x in conn_tmap])))
        families, types = conn_tmap[kind]
        rawlist = cext.get_proc_connections(self.pid, families, types)
        ret = []
        for item in rawlist:
            fd, fam, type, laddr, raddr, status = item
            status = TCP_STATUSES[status]
            nt = nt_proc_conn(fd, fam, type, laddr, raddr, status)
            ret.append(nt)
        return ret

    @wrap_exceptions
    def process_wait(self, timeout=None):
        try:
            return _psposix.wait_pid(self.pid, timeout)
        except TimeoutExpired:
            raise TimeoutExpired(timeout, self.pid, self._process_name)

    @wrap_exceptions
    def get_nice(self):
        return _psutil_posix.getpriority(self.pid)

    @wrap_exceptions
    def set_proc_nice(self, value):
        return _psutil_posix.setpriority(self.pid, value)

    @wrap_exceptions
    def get_status(self):
        code = cext.get_proc_status(self.pid)
        if code in PROC_STATUSES:
            return PROC_STATUSES[code]
        # XXX is this legit? will we even ever get here?
        return "?"

    @wrap_exceptions
    def get_io_counters(self):
        rc, wc, rb, wb = cext.get_proc_io_counters(self.pid)
        return nt_proc_io(rc, wc, rb, wb)

    nt_mmap_grouped = namedtuple(
        'mmap', 'path rss, private, ref_count, shadow_count')
    nt_mmap_ext = namedtuple(
        'mmap', 'addr, perms path rss, private, ref_count, shadow_count')

    # FreeBSD < 8 does not support functions based on kinfo_getfile()
    # and kinfo_getvmmap()
    if hasattr(cext, 'get_proc_open_files'):

        @wrap_exceptions
        def get_open_files(self):
            """Return files opened by process as a list of namedtuples."""
            # XXX - C implementation available on FreeBSD >= 8 only
            # else fallback on lsof parser
            if hasattr(cext, "get_proc_open_files"):
                rawlist = cext.get_proc_open_files(self.pid)
                return [nt_proc_file(path, fd) for path, fd in rawlist]
            else:
                lsof = _psposix.LsofParser(self.pid, self._process_name)
                return lsof.get_proc_open_files()

        @wrap_exceptions
        def get_cwd(self):
            """Return process current working directory."""
            # sometimes we get an empty string, in which case we turn
            # it into None
            return cext.get_proc_cwd(self.pid) or None

        @wrap_exceptions
        def get_memory_maps(self):
            return cext.get_proc_memory_maps(self.pid)

        @wrap_exceptions
        def get_num_fds(self):
            """Return the number of file descriptors opened by this process."""
            return cext.get_proc_num_fds(self.pid)

    else:
        def _not_implemented(self):
            raise NotImplementedError("supported only starting from FreeBSD 8")

        get_open_files = _not_implemented
        get_proc_cwd = _not_implemented
        get_memory_maps = _not_implemented
        get_num_fds = _not_implemented
