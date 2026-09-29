"""UI-only desktop size and current game window measurements."""

import ctypes
import ctypes.util
import sys


class Rect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("left", "top", "right", "bottom")]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", Rect),
        ("rcWork", Rect),
        ("dwFlags", ctypes.c_uint32),
    ]


class Display:
    def __init__(self) -> None:
        self.win32 = sys.platform == "win32"
        self.api = ctypes.windll.user32 if self.win32 else None
        self.sdl = None
        if self.api:
            self.api.GetForegroundWindow.restype = ctypes.c_void_p
            self.api.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(Rect)]
            self.api.GetWindowTextW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_int,
            ]
            self.api.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.api.MonitorFromWindow.restype = ctypes.c_void_p
            self.api.GetMonitorInfoW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(MonitorInfo),
            ]
        if not self.win32:
            library = ctypes.util.find_library("SDL2")
            if library:
                self.sdl = ctypes.CDLL(library)
                self.sdl.SDL_GetKeyboardFocus.restype = ctypes.c_void_p
                self.sdl.SDL_GetMouseFocus.restype = ctypes.c_void_p
                self.sdl.SDL_GetWindowFlags.argtypes = [ctypes.c_void_p]
                self.sdl.SDL_GetWindowFlags.restype = ctypes.c_uint32
                self.sdl.SDL_GetWindowTitle.argtypes = [ctypes.c_void_p]
                self.sdl.SDL_GetWindowTitle.restype = ctypes.c_char_p
                self.sdl.SDL_GetWindowSize.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ]
                self.sdl.SDL_GetDisplayUsableBounds.argtypes = [
                    ctypes.c_int,
                    ctypes.POINTER(Rect),
                ]

    def desktop_size(self) -> tuple[int, int]:
        if self.win32:
            area = Rect()
            if self.api.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
                return area.right - area.left, area.bottom - area.top
            return self.api.GetSystemMetrics(0), self.api.GetSystemMetrics(1)
        if self.sdl:
            self.sdl.SDL_InitSubSystem(0x20)  # SDL_INIT_VIDEO
            area = Rect()
            if self.sdl.SDL_GetDisplayUsableBounds(0, ctypes.byref(area)) == 0:
                return area.right - area.left, area.bottom - area.top
        return 1280, 720

    def window(self) -> tuple[int, int, bool] | None:
        if self.win32:
            window = self.api.GetForegroundWindow()
            area = Rect()
            title = ctypes.create_unicode_buffer(256)
            if window:
                self.api.GetWindowTextW(window, title, len(title))
            if (
                window
                and title.value == "Echo Shift"
                and self.api.GetClientRect(window, ctypes.byref(area))
            ):
                width, height = area.right - area.left, area.bottom - area.top
                monitor = MonitorInfo()
                monitor.cbSize = ctypes.sizeof(MonitorInfo)
                handle = self.api.MonitorFromWindow(window, 2)
                if handle and self.api.GetMonitorInfoW(handle, ctypes.byref(monitor)):
                    screen_w = monitor.rcMonitor.right - monitor.rcMonitor.left
                    screen_h = monitor.rcMonitor.bottom - monitor.rcMonitor.top
                else:
                    screen_w = self.api.GetSystemMetrics(0)
                    screen_h = self.api.GetSystemMetrics(1)
                return width, height, width == screen_w and height == screen_h
            return None
        if self.sdl:
            window = self.sdl.SDL_GetKeyboardFocus() or self.sdl.SDL_GetMouseFocus()
            if window and self.sdl.SDL_GetWindowTitle(window) == b"Echo Shift":
                width, height = ctypes.c_int(), ctypes.c_int()
                self.sdl.SDL_GetWindowSize(
                    window, ctypes.byref(width), ctypes.byref(height)
                )
                flags = self.sdl.SDL_GetWindowFlags(window)
                return width.value, height.value, bool(flags & 0x1001)
        return None
