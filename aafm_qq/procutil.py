"""Find running process image paths (for auto-detecting SnowLuma/NapCat).

Uses ``CreateToolhelp32Snapshot`` via ctypes on Windows (fast, no shelling out),
``/proc`` on Linux, and PowerShell only as a last-resort fallback.
"""
from __future__ import annotations

import os
from typing import List


def _win_paths() -> List[str]:
    try:
        import ctypes
        import ctypes.wintypes as wt
    except Exception:  # noqa: BLE001
        return []

    TH32CS_SNAPPROCESS = 0x2
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    INVALID = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
            ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wt.DWORD),
            ('cntThreads', wt.DWORD), ('th32ParentProcessID', wt.DWORD),
            ('pcPriClassBase', ctypes.c_long), ('dwFlags', wt.DWORD),
            ('szExeFile', ctypes.c_char * 260),
        ]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    k32.Process32First.restype = wt.BOOL
    k32.Process32First.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32)]
    k32.Process32Next.restype = wt.BOOL
    k32.Process32Next.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32)]
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    k32.QueryFullProcessImageNameW.restype = wt.BOOL
    k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD,
                                              ctypes.c_wchar_p, ctypes.POINTER(wt.DWORD)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        return []
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    out: List[str] = []
    try:
        ok = k32.Process32First(snap, ctypes.byref(pe))
        while ok:
            try:
                name = pe.szExeFile.split(b'\x00', 1)[0].decode('mbcs', 'ignore').lower()
            except Exception:  # noqa: BLE001
                name = ''
            if name in ('node.exe', 'node'):
                h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pe.th32ProcessID)
                if h:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wt.DWORD(1024)
                    if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        out.append(buf.value)
                    k32.CloseHandle(h)
            ok = k32.Process32Next(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    return out


def _ps_paths() -> List[str]:
    try:
        import subprocess
        kwargs = {}
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        res = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
             "Select-Object -ExpandProperty ExecutablePath"],
            capture_output=True, text=True, timeout=8, **kwargs)
        return [ln.strip() for ln in (res.stdout or '').splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def _proc_paths() -> List[str]:
    out: List[str] = []
    try:
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmd = f.read().decode('utf-8', 'ignore')
            except OSError:
                continue
            if 'index.mjs' in cmd or 'node' in cmd.split('\x00')[0]:
                try:
                    out.append(os.path.join(os.readlink(f'/proc/{pid}/cwd'), 'node'))
                except OSError:
                    pass
    except OSError:
        pass
    return out


def node_process_paths() -> List[str]:
    if os.name == 'nt':
        paths = _win_paths()
        return paths if paths else _ps_paths()
    return _proc_paths()
