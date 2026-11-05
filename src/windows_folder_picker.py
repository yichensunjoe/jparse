"""Open the Windows folder picker without adding a GUI runtime dependency."""

import ctypes
from pathlib import Path
import sys
import uuid


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


_CANCELLED = 0x800704C7
_HRESULT = ctypes.c_int32


def _method(interface, index, return_type, *argument_types):
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(return_type, ctypes.c_void_p, *argument_types)(vtable[index])


def _check(result, action):
    if result < 0:
        raise RuntimeError("%s失败（Windows 错误 0x%08X）" % (action, result & 0xFFFFFFFF))


def _show_dialog(dialog):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return _method(dialog, 3, _HRESULT, ctypes.c_void_p)(dialog, user32.GetForegroundWindow())


def choose_output_folder(initial):
    """Return a selected filesystem folder, or None when the user cancels."""
    if sys.platform != "win32":
        raise RuntimeError("当前系统无法打开 Windows 文件夹选择器，请手动输入路径")

    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = _HRESULT
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_Guid), ctypes.c_void_p, ctypes.c_uint32,
                                      ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = _HRESULT
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell32.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                                     ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHCreateItemFromParsingName.restype = _HRESULT

    _check(ole32.CoInitializeEx(None, 0x2), "初始化文件夹选择器")  # Single-threaded apartment.
    dialog = ctypes.c_void_p()
    item = ctypes.c_void_p()
    name = ctypes.c_void_p()
    try:
        clsid = _Guid.from_string("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
        iid_dialog = _Guid.from_string("D57C7288-D4AD-4768-BE02-9D969532D960")
        iid_item = _Guid.from_string("43826D1E-E718-42EE-BC55-A1E261C37BFE")
        _check(ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_dialog),
                                      ctypes.byref(dialog)), "创建文件夹选择器")
        options = ctypes.c_uint32()
        _check(_method(dialog, 10, _HRESULT, ctypes.POINTER(ctypes.c_uint32))(dialog, ctypes.byref(options)), "读取选择器设置")
        # Pick only filesystem folders and leave the process working directory alone.
        flags = options.value | 0x20 | 0x40 | 0x8 | 0x800
        _check(_method(dialog, 9, _HRESULT, ctypes.c_uint32)(dialog, flags), "设置文件夹选择器")
        _check(_method(dialog, 17, _HRESULT, ctypes.c_wchar_p)(dialog, "选择成果文件夹"), "设置选择器标题")
        if initial and shell32.SHCreateItemFromParsingName(str(initial), None, ctypes.byref(iid_item), ctypes.byref(item)) >= 0:
            try:
                _method(dialog, 12, _HRESULT, ctypes.c_void_p)(dialog, item)
            finally:
                _method(item, 2, ctypes.c_ulong)(item)
                item = ctypes.c_void_p()

        result = _show_dialog(dialog)
        if result & 0xFFFFFFFF == _CANCELLED:
            return None
        _check(result, "选择文件夹")
        _check(_method(dialog, 20, _HRESULT, ctypes.POINTER(ctypes.c_void_p))(dialog, ctypes.byref(item)), "读取所选文件夹")
        _check(_method(item, 5, _HRESULT, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(
            item, 0x80058000, ctypes.byref(name)), "读取文件夹路径")
        return Path(ctypes.wstring_at(name))
    finally:
        if name:
            ole32.CoTaskMemFree(name)
        if item:
            _method(item, 2, ctypes.c_ulong)(item)
        if dialog:
            _method(dialog, 2, ctypes.c_ulong)(dialog)
        ole32.CoUninitialize()
