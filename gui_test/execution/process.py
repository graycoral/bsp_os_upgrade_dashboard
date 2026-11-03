"""Contain a TC and its children; never infer termination from a lost connection."""
import ctypes
import os
import signal
import subprocess
import sys
import time


class ProcessTree:
    def __init__(self, argv, cwd, stdout, stderr, env=None):
        self.job = None
        # The trusted bootstrap waits until containment is installed before running TC code.
        bootstrap = 'import subprocess,sys; gate=sys.stdin.buffer.read(1); sys.exit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL) if gate==b"!" else 125)'
        self.process = subprocess.Popen(
            [sys.executable, '-I', '-S', '-c', bootstrap, *argv], cwd=cwd, stdin=subprocess.PIPE,
            stdout=stdout, stderr=stderr, start_new_session=os.name != 'nt',
            env={k: v for k, v in (dict(os.environ) | (env or {})).items() if k.upper() != 'GUI_TEST_RUNNER_TOKEN'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            if os.name == 'nt':
                from ctypes import wintypes
                self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
                self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
                self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
                self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
                self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
                self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
                self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]

                class BasicLimit(ctypes.Structure):
                    _fields_ = [('time1', ctypes.c_int64), ('time2', ctypes.c_int64), ('flags', wintypes.DWORD),
                                ('min', ctypes.c_size_t), ('max', ctypes.c_size_t), ('active', wintypes.DWORD),
                                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
                class IO(ctypes.Structure):
                    _fields_ = [(name, ctypes.c_uint64) for name in ('r', 'w', 'o', 'rb', 'wb', 'ob')]
                class Extended(ctypes.Structure):
                    _fields_ = [('basic', BasicLimit), ('io', IO), ('process_memory', ctypes.c_size_t),
                                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
                self.job = self.kernel.CreateJobObjectW(None, None)
                limits = Extended(); limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
                if not self.job or not self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                    raise OSError('Cannot establish Windows process containment')
                if not self.kernel.AssignProcessToJobObject(self.job, wintypes.HANDLE(int(self.process._handle))):
                    raise OSError('Cannot assign TC to Windows Job Object')
            self.process.stdin.write(b'!'); self.process.stdin.close()
        except BaseException:
            self.process.kill(); self.process.wait()
            self.close()
            raise

    def stopped(self):
        self.process.poll()
        if self.job:
            from ctypes import wintypes
            class Accounting(ctypes.Structure):
                _fields_ = [('u', ctypes.c_int64), ('k', ctypes.c_int64), ('pu', ctypes.c_int64), ('pk', ctypes.c_int64),
                            ('faults', wintypes.DWORD), ('total', wintypes.DWORD), ('active', wintypes.DWORD), ('terminated', wintypes.DWORD)]
            info = Accounting()
            if not self.kernel.QueryInformationJobObject(self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                return False
            return info.active == 0 and self.process.returncode is not None
        try:
            os.killpg(self.process.pid, 0)
            return False
        except ProcessLookupError:
            return self.process.returncode is not None

    def stop(self):
        if self.job:
            self.kernel.TerminateJobObject(self.job, 1)
        else:
            try: os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.stopped(): return True
            time.sleep(.02)
        return False

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
