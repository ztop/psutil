#include <Python.h>
#include <windows.h>
#include <Psapi.h>

static PyObject* get_pid_list(PyObject* self, PyObject* args)
{
	int procArraySz = 1024;
	
	/* Win32 SDK says the only way to know if our process array
	 * wasn't large enough is to check the returned size and make
	 * sure that it doesn't match the size of the array.
	 * If it does we allocate a larger array and try again*/
	
	/* Stores the actual array */
	DWORD* procArray = NULL;
	/* Stores the byte size of the returned array from enumprocesses */
	DWORD enumReturnSz = 0;
	
	do {
		free(procArray);
		
		DWORD procArrayByteSz = procArraySz * sizeof(DWORD);
		procArray = malloc(procArrayByteSz);
		
		
		if (! EnumProcesses(procArray, procArrayByteSz, &enumReturnSz)) 
		{
			free(procArray);
			
			/* Throw exception to python */
		}  
		else if (enumReturnSz == procArrayByteSz) 
		{
			/* Process list was too large.  Allocate more space*/
			procArraySz += 1024;
		}
		
		/* else we have a good list */
		
	} while(enumReturnSz == procArraySz * sizeof(DWORD));
	
	/* The number of elements is the returned size / size of each element */
	DWORD numberOfReturnedPIDs = enumReturnSz / sizeof(DWORD);
	
	PyObject* retlist = PyList_New(0);
	int i;
    for (i = 0; i < numberOfReturnedPIDs; i++) {
        PyList_Append(retlist, Py_BuildValue("i", procArray[i]) );
    }

    return retlist;
}
 
static PyMethodDef PsutilMethods[] =
{
     {"get_pid_list", get_pid_list, METH_VARARGS, 
     	"Returns a python list of PIDs currently running on the host system"},
     	
     {NULL, NULL, 0, NULL}
};
 
PyMODINIT_FUNC
 
init_psutil_mswindows(void)
{
     (void) Py_InitModule("_psutil_mswindows", PsutilMethods);
}
