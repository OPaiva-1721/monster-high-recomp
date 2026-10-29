"""Own-child lifecycle. A minimized window is visible and is never stopped."""
import ctypes
import os
import subprocess
import time
from contextlib import contextmanager


@contextmanager
def single_game(name='Local\\ps3-port-installer-game-session'):
    """Close the check/spawn race across our launchers; no persistent lock file."""
    if os.name != 'nt':
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, True, name)
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    if error == 183:  # ERROR_ALREADY_EXISTS: another launcher owns the session.
        kernel.CloseHandle(handle)
        raise ValueError('Outro launcher já está abrindo ou executando um jogo.')
    try:
        yield
    finally:
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


class ClosedWindow:
    def __init__(self, grace=30):
        self.seen = False
        self.absent_since = None
        self.grace = grace

    def expired(self, visible, now):
        if visible is None:
            self.absent_since = None
            return False
        if visible:
            self.seen, self.absent_since = True, None
        elif self.seen and self.absent_since is None:
            self.absent_since = now
        return self.absent_since is not None and now - self.absent_since >= self.grace


def visible_window(pid):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.EnumWindows.argtypes = [callback_type, ctypes.c_ssize_t]
    found = False

    @callback_type
    def visit(window, _):
        nonlocal found
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(window):
            found = True
            return False
        return True

    if not user32.EnumWindows(visit, 0) and not found:
        return None  # Unknown observation; never infer user closure from an API error.
    return found


def wait_owned(process, log, observe=None):
    if os.name != 'nt' and observe is None:
        return process.wait()
    watch = ClosedWindow()
    observe = observe or visible_window
    while process.poll() is None:
        if watch.expired(observe(process.pid), time.monotonic()):
            # No timeout while playing: only after an observed window disappears.
            # The Popen handle identifies the still-live child, never an arbitrary PID.
            if process.poll() is None:
                log.write(b'\n[launcher] Window closed for 30s; stopping remaining owned game process.\n')
                log.flush()
                try:
                    result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                            stdout=log, stderr=subprocess.STDOUT, timeout=10,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode and process.poll() is None:
                        process.terminate()
                except (OSError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        process.terminate()
                return process.wait(timeout=10)
            break
        time.sleep(.5)
    return process.wait()
