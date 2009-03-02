/*
 * $Id$
 *
 * FreeBSD platform-specific module methods for _psutil_bsd
 */

#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <sys/proc.h>

#include <Python.h>
#include "_psutil_bsd.h"
#include "arch/bsd/process_info.h"


/*
 * define the psutil C module methods and initialize the module.
 */
static PyMethodDef PsutilMethods[] =
{
     {"get_pid_list", get_pid_list, METH_VARARGS, 
     	"Returns a python list of PIDs currently running on the host system"},
     {"get_process_info", get_process_info, METH_VARARGS,
       	"Returns a psutil.ProcessInfo object for the given PID"},
     {NULL, NULL, 0, NULL}
};


static PyObject *NoSuchProcessException;
 
PyMODINIT_FUNC
init_psutil_bsd(void)
{
     PyObject *m;
     m = Py_InitModule("_psutil_bsd", PsutilMethods);
     NoSuchProcessException = PyErr_NewException("_psutil_bsd.NoSuchProcess", NULL, NULL);
     Py_INCREF(NoSuchProcessException);
     PyModule_AddObject(m, "NoSuchProcess", NoSuchProcessException);
}


/*
 * Return a Python list of all the PIDs running on the system.
 */
static PyObject* get_pid_list(PyObject* self, PyObject* args)
{
    kinfo_proc *proclist = NULL;
    kinfo_proc *orig_address = NULL;
    size_t num_processes;
    size_t idx;
    PyObject* retlist = PyList_New(0);
    PyObject* pid;

    if (get_proc_list(&proclist, &num_processes) != 0) {
        Py_DECREF(retlist);
        PyErr_SetString(PyExc_RuntimeError, "failed to retrieve process list.");
        return NULL;
    }

    if (num_processes > 0) {
        orig_address = proclist; //save so we can free it after we're done
        for (idx=0; idx < num_processes; idx++) {
            pid = Py_BuildValue("i", proclist->ki_pid);
            PyList_Append(retlist, pid);
            Py_XDECREF(pid);
            proclist++;
        }
        free(orig_address);
    }
   
    return retlist;
}


static int pid_exists(long pid) {
    int kill_ret;

    //save some time if it's an invalid PID
    if (pid < 0) {
        return 0;
    }

    //if kill returns success of permission denied we know it's a valid PID
    kill_ret = kill(pid , 0);
    if ( (0 == kill_ret) || (EPERM == errno) ) {
        return 1;
    }
    
    return 0;
}


static PyObject* get_process_info(PyObject* self, PyObject* args)
{

    int mib[4];
    size_t len;
    struct kinfo_proc kp;
	long pid;
    PyObject* infoTuple = NULL;
    PyObject* arglist = NULL;

	//the argument passed should be a process id
	if (! PyArg_ParseTuple(args, "l", &pid)) {
		return PyErr_Format(PyExc_RuntimeError, "Invalid argument - no PID provided.");
	}

    if (0 == pid) {
        //USER   PID %CPU %MEM   VSZ   RSS  TT  STAT STARTED      TIME COMMAND
        //root     0  0.0  0.0     0     0  ??  DLs  12:22AM   0:00.13 [swapper]
        return Py_BuildValue("llssNll", pid, 0, "swapper", "", Py_BuildValue("[]"), 0, 0);
    }

    //build the mib to pass to sysctl to tell it what PID and what info we want
    len = 4;
    sysctlnametomib("kern.proc.pid", mib, &len);
    mib[0] = CTL_KERN;
    mib[1] = KERN_PROC;
    mib[2] = KERN_PROC_PID;
    mib[3] = pid;
    
    //fetch the info with sysctl()
    len = sizeof(kp);
    if (sysctl(mib, 4, &kp, &len, NULL, 0) == -1) {
        // raise an exception if it failed, since we won't get any data
        if (ESRCH == errno) {
            return PyErr_Format(NoSuchProcessException, "No process found with pid %lu", pid);
        }
        return PyErr_SetFromErrno(PyExc_OSError);
    } 

    if (len > 0) { //if 0 then no data was retrieved

        //get the commandline, since we got everything else 
        arglist = get_arg_list(pid);

        //get_arg_list() returns NULL only if getcmdargs failed with ESRCH (no process with that PID)
        if (NULL == arglist) {
            return PyErr_Format(NoSuchProcessException, "No such process found with pid %lu", pid);
        }

        //hooray, we got all the data, so return it as a tuple to be passed to ProcessInfo() constructor
        infoTuple = Py_BuildValue("llssNll", pid, kp.ki_ppid, kp.ki_comm, "", arglist, kp.ki_ruid, kp.ki_rgid);
        if (NULL == infoTuple) {
            PyErr_SetString(PyExc_RuntimeError, "Failed to build process information tuple!");
        }    
        return infoTuple;
    }

    //something went wrong, throw an error
	return PyErr_Format(PyExc_RuntimeError, "Failed to retrieve process information.");
}

