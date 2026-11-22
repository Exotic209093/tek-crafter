"""Temporarily turn Windows 'Enhance pointer precision' off (not saved),
measure stepped-turn drift, then restore the original setting."""
import ctypes
import subprocess
import sys

SPI_GETMOUSE, SPI_SETMOUSE = 0x0003, 0x0004
u = ctypes.windll.user32
orig = (ctypes.c_int * 3)()
u.SystemParametersInfoW(SPI_GETMOUSE, 0, orig, 0)
print("original mouse params", list(orig))
off = (ctypes.c_int * 3)(0, 0, 0)
try:
    u.SystemParametersInfoW(SPI_SETMOUSE, 0, off, 0)   # fWinIni=0: not persisted
    now = (ctypes.c_int * 3)()
    u.SystemParametersInfoW(SPI_GETMOUSE, 0, now, 0)
    print("during test", list(now))
    subprocess.run([sys.executable, "step_test.py", *sys.argv[1:]])
finally:
    u.SystemParametersInfoW(SPI_SETMOUSE, 0, orig, 0)
    back = (ctypes.c_int * 3)()
    u.SystemParametersInfoW(SPI_GETMOUSE, 0, back, 0)
    print("restored", list(back))
