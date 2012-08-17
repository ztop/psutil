/*
 * $Id$
 *
 * Copyright (c) 2009, Jay Loden, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Functions specific to Sun OS Solaris platforms.
 */

#include <Python.h>

// fix for "Cannot use procfs in the large file compilation environment"
// error, see:
// http://sourceware.org/ml/gdb-patches/2010-11/msg00336.html
#undef _FILE_OFFSET_BITS

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/proc.h>
#include <sys/swap.h>
#include <sys/sysinfo.h>
#include <sys/mntent.h>  // for MNTTAB
#include <sys/mnttab.h>
#include <fcntl.h>
#include <procfs.h>
#include <utmpx.h>
#include <kstat.h>

// #include "_psutil_bsd.h"  TODO fix warnings


#define TV2DOUBLE(t)   (((t).tv_nsec * 0.000000001) + (t).tv_sec)


/*
 * Read a file content and fills a C structure with it.
 */
int
_fill_struct_from_file(char *path, void *fstruct, size_t size)
{
    int fd;
    size_t nbytes;
	fd = open(path, O_RDONLY);
	if (fd == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
	}
	nbytes = read(fd, fstruct, size);
	if (nbytes == 1) {
    	close(fd);
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
	}
	if (nbytes != size) {
    	close(fd);
        PyErr_SetString(PyExc_RuntimeError, "structure size mismatch");
        return NULL;
	}
	close(fd);
    return nbytes;
}


/*
 * Return process ppid, rss, vms, ctime, nice, nthreads, status and tty
 * as a Python tuple.
 */
static PyObject*
get_process_basic_info(PyObject* self, PyObject* args)
{
	int pid;
	char path[100];
	psinfo_t info;

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/psinfo", pid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }
    return Py_BuildValue("ikkdiiik",
                         info.pr_ppid,              // parent pid
                         info.pr_rssize,            // rss
                         info.pr_size,              // vms
                         TV2DOUBLE(info.pr_start),  // create time
                         info.pr_lwp.pr_nice,       // nice
                         info.pr_nlwp,              // no. of threads
                         info.pr_lwp.pr_state,      // status code
                         info.pr_ttydev             // tty nr
                         );
}


/*
 * Return process name and args as a Python tuple.
 */
static PyObject*
get_process_name_and_args(PyObject* self, PyObject* args)
{
	int pid;
	char path[100];
	psinfo_t info;

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/psinfo", pid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }
    return Py_BuildValue("ss", info.pr_fname,
                               info.pr_psargs);
}


/*
 * Return process user and system CPU times as a Python tuple.
 */
static PyObject*
get_process_cpu_times(PyObject* self, PyObject* args)
{
	int pid;
	char path[100];
	pstatus_t info;

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/status", pid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }

    // results are more precise than os.times()
    return Py_BuildValue("dd", TV2DOUBLE(info.pr_utime),
                               TV2DOUBLE(info.pr_stime));
}


/*
 * Return process uids/gids as a Python tuple.
 */
static PyObject*
get_process_cred(PyObject* self, PyObject* args)
{
	int pid;
	char path[100];
	prcred_t info;

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/cred", pid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }

    return Py_BuildValue("iiiiii", info.pr_ruid, info.pr_euid, info.pr_suid,
                                   info.pr_rgid, info.pr_egid, info.pr_sgid);
}


/*
 * Return process uids/gids as a Python tuple.
 */
static PyObject*
get_process_num_ctx_switches(PyObject* self, PyObject* args)
{
    int pid;
    char path[100];
    prusage_t info;

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/usage", pid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }

    return Py_BuildValue("kk", info.pr_vctx, info.pr_ictx);
}

/*
 * Return information about a given process thread.
 */
static PyObject*
query_process_thread(PyObject* self, PyObject* args)
{
	int tid;
	char path[100];
	lwpstatus_t info;

    if (! PyArg_ParseTuple(args, "i", &tid)) {
        return NULL;
    }
    sprintf(path, "/proc/%i/lwp/1/lwpstatus", tid);
    if (! _fill_struct_from_file(path, (void *)&info, sizeof(info))) {
        return NULL;
    }

    return Py_BuildValue("dd", TV2DOUBLE(info.pr_utime),
                               TV2DOUBLE(info.pr_stime));
}


/*
 * Return information about system virtual memory.
 */
static PyObject*
get_swap_mem(PyObject* self, PyObject* args)
{
// XXX (arghhh!)
// total/free swap mem: commented out as for some reason I can't
// manage to get the same results shown by "swap -l", despite the
// code below is exactly the same as:
// http://cvs.opensolaris.org/source/xref/onnv/onnv-gate/usr/src/cmd/swap/swap.c
// We're going to parse "swap -l" output from Python (sigh!)

/*
    struct swaptable 	*st;
    struct swapent	*swapent;
    int	i;
    struct stat64 statbuf;
    char *path;
    char fullpath[MAXPATHLEN+1];
    int	num;

    if ((num = swapctl(SC_GETNSWP, NULL)) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    if (num == 0) {
        PyErr_SetString(PyExc_RuntimeError, "no swap devices configured");
        return NULL;
    }
    if ((st = malloc(num * sizeof(swapent_t) + sizeof (int))) == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "malloc failed");
        return NULL;
    }
    if ((path = malloc(num * MAXPATHLEN)) == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "malloc failed");
        return NULL;
    }
    swapent = st->swt_ent;
    for (i = 0; i < num; i++, swapent++) {
	    swapent->ste_path = path;
	    path += MAXPATHLEN;
    }
    st->swt_n = num;
    if ((num = swapctl(SC_LIST, st)) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    swapent = st->swt_ent;
    long t = 0, f = 0;
    for (i = 0; i < num; i++, swapent++) {
	    int diskblks_per_page =(int)(sysconf(_SC_PAGESIZE) >> DEV_BSHIFT);
        t += (long)swapent->ste_pages;
        f += (long)swapent->ste_free;
    }

    free(st);
    return Py_BuildValue("(kk)", t, f);
*/

    kstat_ctl_t	*kc;
    kstat_t	    *k;
    cpu_stat_t	*cpu;
    int	        cpu_count = 0;
    int         flag = 0;
    uint_t      sin = 0;
    uint_t      sout = 0;

    kc = kstat_open();
    if (kc == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);;
    }

	k = kc->kc_chain;
  	while (k != NULL) {
	    if((strncmp(k->ks_name, "cpu_stat", 8) == 0) && \
	        (kstat_read(kc, k, NULL) != -1) )
	    {
	        flag = 1;
		    cpu = (cpu_stat_t*) k->ks_data;
		    sin += cpu->cpu_vminfo.pgswapin;    // num pages swapped in
		    sout += cpu->cpu_vminfo.pgswapout;  // num pages swapped out
	    }
	    cpu_count += 1;
        k = k->ks_next;
    }
	kstat_close(kc);
	if (!flag) {
    	PyErr_SetString(PyExc_RuntimeError, "no swap device was found");
    	return NULL;
	}
    return Py_BuildValue("(II)", sin, sout);
}


/*
 * Return users currently connected on the system.
 */
static PyObject*
get_system_users(PyObject* self, PyObject* args)
{
    PyObject *ret_list = PyList_New(0);
    PyObject *tuple = NULL;
    PyObject *user_proc = NULL;
    struct utmpx *ut;
    int ret;

    while (NULL != (ut = getutxent())) {
        if (ut->ut_type == USER_PROCESS)
            user_proc = Py_True;
        else
            user_proc = Py_False;
        tuple = Py_BuildValue("(sssfO)",
            ut->ut_user,              // username
            ut->ut_line,              // tty
            ut->ut_host,              // hostname
            (float)ut->ut_tv.tv_sec,  // tstamp
            user_proc                 // (bool) user process
        );
        PyList_Append(ret_list, tuple);
        Py_DECREF(tuple);
    }
    endutent();

    return ret_list;
}


/*
 * Return disk mounted partitions as a list of tuples including device,
 * mount point and filesystem type.
 */
static PyObject*
get_disk_partitions(PyObject* self, PyObject* args)
{
    FILE *file;
    struct mnttab mt;
    PyObject* py_retlist = PyList_New(0);
    PyObject* py_tuple;

    file = fopen(MNTTAB, "rb");
    if (file == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    while (getmntent(file, &mt) == 0) {
        py_tuple = Py_BuildValue("(ssss)", mt.mnt_special,  // device
                                           mt.mnt_mountp,     // mount point
                                           mt.mnt_fstype,    // fs type
                                           mt.mnt_mntopts);   // options
        PyList_Append(py_retlist, py_tuple);
        Py_XDECREF(py_tuple);

    }

    return py_retlist;
}


/*
 * Return system-wide CPU times.
 */
static PyObject*
get_system_per_cpu_times(PyObject* self, PyObject* args)
{
    kstat_ctl_t *kc;
    kstat_t *ksp;
    cpu_stat_t cs;
    int numcpus;
    int i;
    PyObject* py_retlist = PyList_New(0);
    PyObject* py_cputime;

    kc = kstat_open();
    if (kc == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);;
    }

    numcpus = sysconf(_SC_NPROCESSORS_ONLN) - 1;
    for (i=0; i<=numcpus; i++) {
        ksp = kstat_lookup(kc, "cpu_stat", i, NULL);
        if (ksp == NULL) {
            kstat_close(kc);
            return PyErr_SetFromErrno(PyExc_OSError);;
        }
	    if (kstat_read(kc, ksp, &cs) == -1) {
		    kstat_close(kc);
            return PyErr_SetFromErrno(PyExc_OSError);;
	    }
        py_cputime = Py_BuildValue("IIII",
                                   cs.cpu_sysinfo.cpu[CPU_USER],
                                   cs.cpu_sysinfo.cpu[CPU_KERNEL],
                                   cs.cpu_sysinfo.cpu[CPU_IDLE],
                                   cs.cpu_sysinfo.cpu[CPU_WAIT]);
        PyList_Append(py_retlist, py_cputime);
        Py_XDECREF(py_cputime);
    }

    kstat_close(kc);
    return py_retlist;
}


/*
 * Return disk IO statistics.
 */
static PyObject*
get_disk_io_counters(PyObject* self, PyObject* args)
{
    kstat_ctl_t *kc;
    kstat_t *ksp;
    kstat_io_t kio;
    PyObject* py_retdict = PyDict_New();
    PyObject* py_disk_info;

    kc = kstat_open();
    if (kc == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);;
    }
    ksp = kc->kc_chain;
    while (ksp != NULL) {
        if (ksp->ks_type == KSTAT_TYPE_IO) {
            if (strcmp(ksp->ks_class, "disk") == 0) {
                if (kstat_read(kc, ksp, &kio) == -1) {
                    kstat_close(kc);
                    return PyErr_SetFromErrno(PyExc_OSError);;
                }
                py_disk_info = Py_BuildValue("(IIKKLL)",
                                             kio.reads,
                                             kio.writes,
                                             kio.nread,
                                             kio.nwritten,
                                             kio.rtime,  // XXX are these ms?
                                             kio.wtime   // XXX are these ms?
                                             );
                PyDict_SetItemString(py_retdict, ksp->ks_name, py_disk_info);
                Py_XDECREF(py_disk_info);
            }
        }
        ksp = ksp->ks_next;
    }
    kstat_close(kc);

    return py_retdict;
}


/*
 * Return process memory mappings.
 */
static PyObject*
get_process_memory_maps(PyObject* self, PyObject* args)
{
    int pid;
    int fd;
	char path[100];
	char perms[10];
	char *name;
	struct stat st;
	pstatus_t status;

    prxmap_t *xmap = NULL, *p;
    off_t size;
    size_t nread;
    int nmap;
    uintptr_t pr_addr_sz;
    uintptr_t stk_base_sz, brk_base_sz;

    PyObject* pytuple = NULL;
    PyObject* retlist = PyList_New(0);

    if (! PyArg_ParseTuple(args, "i", &pid)) {
        goto error;
    }

    sprintf(path, "/proc/%i/status", pid);
    if (! _fill_struct_from_file(path, (void *)&status, sizeof(status))) {
        goto error;
    }

    sprintf(path, "/proc/%i/xmap", pid);
    if (stat(path, &st) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        goto error;
    }

    size = st.st_size;

	fd = open(path, O_RDONLY);
	if (fd == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        goto error;
	}

	xmap = (prxmap_t *)malloc(size);
	if (xmap == NULL) {
        PyErr_SetString(PyExc_MemoryError, "can't allocate prxmap_t");
        goto error;
	}

    nread = pread(fd, xmap, size, 0);
    nmap = nread / sizeof(prxmap_t);
    p = xmap;

    while (nmap) {
        nmap -= 1;
        if (p == NULL) {
            p += 1;
            continue;
        }

        perms[0] = '\0';
        pr_addr_sz = p->pr_vaddr + p->pr_size;


        // perms
        sprintf(perms, "%c%c%c%c%c%c", p->pr_mflags & MA_READ ? 'r' : '-',
                                       p->pr_mflags & MA_WRITE ? 'w' : '-',
                                       p->pr_mflags & MA_EXEC ? 'x' : '-',
                                       p->pr_mflags & MA_SHARED ? 's' : '-',
                                       p->pr_mflags & MA_NORESERVE ? 'R' : '-',
                                       p->pr_mflags & MA_RESERVED1 ? '*' : ' ');

        // name
        if (strlen(p->pr_mapname) > 0) {
            name = p->pr_mapname;
        }
        else {
            if ((p->pr_mflags & MA_ISM) || (p->pr_mflags & MA_SHM)) {
                name = "[shmid]";
            }
            else {
                stk_base_sz = status.pr_stkbase + status.pr_stksize;
                brk_base_sz = status.pr_brkbase + status.pr_brksize;

                if ((pr_addr_sz > status.pr_stkbase) && (p->pr_vaddr < stk_base_sz)) {
                    name = "[stack]";
                }
                else if ((p->pr_mflags & MA_ANON) && \
                         (pr_addr_sz > status.pr_brkbase) && \
                         (p->pr_vaddr < brk_base_sz)) {
                    name = "[heap]";
                }
                else {
                    name = "[anon]";
                }
            }
        }

        pytuple = Py_BuildValue("iisslll",
                                    p->pr_vaddr,
                                    pr_addr_sz,
                                    perms,
                                    name,
                                    (long)p->pr_rss * p->pr_pagesize,
                                    (long)p->pr_anon * p->pr_pagesize,
                                    (long)p->pr_locked * p->pr_pagesize);
        if (!pytuple)
            goto error;
        if (PyList_Append(retlist, pytuple))
            goto error;
        Py_DECREF(pytuple);

        // increment pointer
        p += 1;
    }


    return retlist;

error:
    Py_XDECREF(pytuple);
    Py_DECREF(retlist);
    if (xmap != NULL)
        free(xmap);
    return NULL;
}


/*
 * Return a list of tuples for network I/O statistics.
 */
static PyObject*
get_network_io_counters(PyObject* self, PyObject* args)
{
    kstat_ctl_t	*kc = NULL;
    kstat_t *ksp;
    kstat_named_t *rbytes, *wbytes, *rpkts, *wpkts, *ierrs, *oerrs;

    PyObject* py_retdict = PyDict_New();
    PyObject* py_ifc_info = NULL;

    kc = kstat_open();
    if (kc == NULL)
        goto error;

    ksp = kc->kc_chain;
    while (ksp != NULL) {
        if (ksp->ks_type != KSTAT_TYPE_NAMED)
            goto next;
        if (strcmp(ksp->ks_class, "net") != 0)
            goto next;
        /*
        // XXX "lo" (localhost) interface makes kstat_data_lookup() fail
        // (maybe because "ifconfig -a" says it's a virtual interface?).
        if ((strcmp(ksp->ks_module, "link") != 0) &&
            (strcmp(ksp->ks_module, "lo") != 0)) {
            goto skip;
        */
        if ((strcmp(ksp->ks_module, "link") != 0)) {
            goto next;
        }

        if (kstat_read(kc, ksp, NULL) == -1) {
            errno = 0;
			continue;
		}

        rbytes = (kstat_named_t *)kstat_data_lookup(ksp, "rbytes");
        wbytes = (kstat_named_t *)kstat_data_lookup(ksp, "obytes");
        rpkts = (kstat_named_t *)kstat_data_lookup(ksp, "ipackets");
        wpkts = (kstat_named_t *)kstat_data_lookup(ksp, "opackets");
        ierrs = (kstat_named_t *)kstat_data_lookup(ksp, "ierrors");
        oerrs = (kstat_named_t *)kstat_data_lookup(ksp, "oerrors");

        if ((rbytes == NULL) || (wbytes == NULL) || (rpkts == NULL) ||
            (wpkts == NULL) || (ierrs == NULL) || (oerrs == NULL))
        {
            PyErr_SetString(PyExc_RuntimeError, "kstat_data_lookup() failed");
            goto error;
        }

#if defined(_INT64_TYPE)
        py_ifc_info = Py_BuildValue("(KKKKkkii)", rbytes->value.ui64,
                                                  wbytes->value.ui64,
                                                  rpkts->value.ui64,
                                                  wpkts->value.ui64,
                                                  ierrs->value.ui32,
                                                  oerrs->value.ui32,
#else
        py_ifc_info = Py_BuildValue("(kkkkkkii)", rbytes->value.ui32,
                                                  wbytes->value.ui32,
                                                  rpkts->value.ui32,
                                                  ierrs->value.ui32,
                                                  oerrs->value.ui32,
#endif
                                                  0,  // dropin not supported
                                                  0   // dropout not supported
                                    );
        if (!py_ifc_info)
            goto error;
        if (PyDict_SetItemString(py_retdict, ksp->ks_name, py_ifc_info))
            goto error;
        Py_DECREF(py_ifc_info);
        goto next;

        next:
            ksp = ksp->ks_next;
    }

    kstat_close(kc);
    return py_retdict;

error:
    Py_XDECREF(py_ifc_info);
    Py_DECREF(py_retdict);
    if (kc != NULL)
        kstat_close(kc);
    return NULL;
}


/*
 * define the psutil C module methods and initialize the module.
 */
static PyMethodDef
PsutilMethods[] =
{
     // --- process-related functions

     {"get_process_basic_info", get_process_basic_info, METH_VARARGS,
        "Return process ppid, rss, vms, ctime, nice, nthreads, status and tty"},
     {"get_process_name_and_args", get_process_name_and_args, METH_VARARGS,
        "Return process name and args."},
     {"get_process_cpu_times", get_process_cpu_times, METH_VARARGS,
        "Return process user and system CPU times."},
     {"get_process_cred", get_process_cred, METH_VARARGS,
        "Return process uids/gids."},
     {"query_process_thread", query_process_thread, METH_VARARGS,
        "Return info about a process thread"},
     {"get_process_memory_maps", get_process_memory_maps, METH_VARARGS,
        "Return process memory mappings"},
     {"get_process_num_ctx_switches", get_process_num_ctx_switches, METH_VARARGS,
        "Return the number of context switches performed by process"},

     // --- system-related functions

     {"get_swap_mem", get_swap_mem, METH_VARARGS,
        "Return information about system swap memory."},
     {"get_system_users", get_system_users, METH_VARARGS,
        "Return currently connected users."},
     {"get_disk_partitions", get_disk_partitions, METH_VARARGS,
        "Return disk partitions."},
     {"get_system_per_cpu_times", get_system_per_cpu_times, METH_VARARGS,
        "Return system per-CPU times."},
     {"get_disk_io_counters", get_disk_io_counters, METH_VARARGS,
        "Return a Python dict of tuples for disk I/O statistics."},
     {"get_network_io_counters", get_network_io_counters, METH_VARARGS,
        "Return a Python dict of tuples for network I/O statistics."},

     {NULL, NULL, 0, NULL}
};


struct module_state {
    PyObject *error;
};

#if PY_MAJOR_VERSION >= 3
#define GETSTATE(m) ((struct module_state*)PyModule_GetState(m))
#else
#define GETSTATE(m) (&_state)
#endif

#if PY_MAJOR_VERSION >= 3

static int
psutil_sunos_traverse(PyObject *m, visitproc visit, void *arg) {
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int
psutil_sunos_clear(PyObject *m) {
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef
moduledef = {
        PyModuleDef_HEAD_INIT,
        "psutil_sunos",
        NULL,
        sizeof(struct module_state),
        PsutilMethods,
        NULL,
        psutil_sunos_traverse,
        psutil_sunos_clear,
        NULL
};

#define INITERROR return NULL

PyObject *
PyInit__psutil_sunos(void)

#else
#define INITERROR return

void init_psutil_sunos(void)
#endif
{
#if PY_MAJOR_VERSION >= 3
    PyObject *module = PyModule_Create(&moduledef);
#else
    PyObject *module = Py_InitModule("_psutil_sunos", PsutilMethods);
#endif
    PyModule_AddIntConstant(module, "SSLEEP", SSLEEP);
    PyModule_AddIntConstant(module, "SRUN", SRUN);
    PyModule_AddIntConstant(module, "SZOMB", SZOMB);
    PyModule_AddIntConstant(module, "SSTOP", SSTOP);
    PyModule_AddIntConstant(module, "SIDL", SIDL);
    PyModule_AddIntConstant(module, "SONPROC", SONPROC);
    PyModule_AddIntConstant(module, "SWAIT", SWAIT);

    PyModule_AddIntConstant(module, "PRNODEV", PRNODEV);  // for process tty

    if (module == NULL) {
        INITERROR;
    }
#if PY_MAJOR_VERSION >= 3
    return module;
#endif
}
