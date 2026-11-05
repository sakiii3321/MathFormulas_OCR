"""Current-user Windows sign-in startup for source and packaged editions."""
from pathlib import Path
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FormulaOCR"


def startup_command():
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        arguments = [str(executable)]
    else:
        # pythonw uses the same environment without opening a console at sign-in.
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            executable = pythonw
        arguments = [str(executable), str(Path(sys.argv[0]).resolve())]
    return subprocess.list2cmdline([*arguments, "--background"])


def _registered_value():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None


def is_enabled():
    if sys.platform != "win32":
        return False
    value = _registered_value()
    return bool(value and value[0])


def set_enabled(enabled):
    if sys.platform != "win32":
        raise OSError("开机自启仅支持 Windows。")
    import winreg
    desired = (startup_command(), winreg.REG_SZ) if enabled else None
    if _registered_value() == desired:
        return
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            command, kind = desired
            winreg.SetValueEx(key, VALUE_NAME, 0, kind, command)
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
