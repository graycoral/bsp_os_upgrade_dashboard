"""One Windows common file dialog. No Qt, file uploads, or arbitrary commands."""
import json
import os
import sys


def choose(kind):
    if os.name != 'nt' or kind not in {'python', 'ssh_key', 'putty'}:
        raise ValueError('Unsupported file picker')
    import ctypes
    from ctypes import wintypes as w

    class OpenFileName(ctypes.Structure):
        _fields_ = [('lStructSize', w.DWORD), ('hwndOwner', w.HWND), ('hInstance', w.HINSTANCE),
                    ('lpstrFilter', w.LPCWSTR), ('lpstrCustomFilter', w.LPWSTR), ('nMaxCustFilter', w.DWORD),
                    ('nFilterIndex', w.DWORD), ('lpstrFile', w.LPWSTR), ('nMaxFile', w.DWORD),
                    ('lpstrFileTitle', w.LPWSTR), ('nMaxFileTitle', w.DWORD), ('lpstrInitialDir', w.LPCWSTR),
                    ('lpstrTitle', w.LPCWSTR), ('Flags', w.DWORD), ('nFileOffset', w.WORD),
                    ('nFileExtension', w.WORD), ('lpstrDefExt', w.LPCWSTR), ('lCustData', w.LPARAM),
                    ('lpfnHook', ctypes.c_void_p), ('lpTemplateName', w.LPCWSTR), ('pvReserved', ctypes.c_void_p),
                    ('dwReserved', w.DWORD), ('FlagsEx', w.DWORD)]
    buffer = ctypes.create_unicode_buffer(32768)
    dialog = OpenFileName()
    dialog.lStructSize = ctypes.sizeof(dialog)
    dialog.lpstrFile = ctypes.cast(buffer, w.LPWSTR)
    dialog.nMaxFile = len(buffer)
    dialog.lpstrTitle = {'python': 'TC Python 선택', 'ssh_key': 'SSH 개인 키 선택', 'putty': 'PuTTY 선택'}[kind]
    dialog.lpstrFilter = '모든 파일\0*.*\0\0' if kind == 'ssh_key' else '실행 파일\0*.exe\0모든 파일\0*.*\0\0'
    dialog.Flags = 0x00001000 | 0x00000800 | 0x00000008 | 0x00080000  # existing file/path, no cwd change, Explorer
    api = ctypes.WinDLL('comdlg32', use_last_error=True)
    api.GetOpenFileNameW.argtypes = [ctypes.POINTER(OpenFileName)]
    api.GetOpenFileNameW.restype = w.BOOL
    if api.GetOpenFileNameW(ctypes.byref(dialog)):
        return buffer.value
    if api.CommDlgExtendedError():
        raise OSError('Windows common dialog failed')
    return ''


if __name__ == '__main__':
    try:
        print(json.dumps({'path': choose(sys.argv[1])}, ensure_ascii=True))
    except Exception:
        raise SystemExit(2)
