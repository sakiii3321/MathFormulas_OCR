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


def is_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            command, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(command)
    except FileNotFoundError:
        return False


def set_enabled(enabled):
    if sys.platform != "win32":
        raise OSError("开机自启仅支持 Windows。")
    import winreg
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, startup_command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
