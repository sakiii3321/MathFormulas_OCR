import sys
from unittest.mock import MagicMock, patch

import pytest

from formula_ocr import autostart


@pytest.mark.parametrize('entry', ['main.py', 'main_webview2.py'])
def test_source_startup_quotes_paths_and_uses_pythonw(tmp_path, monkeypatch, entry):
    folder = tmp_path / 'Formula OCR 测试'
    folder.mkdir()
    python = folder / 'python.exe'
    pythonw = folder / 'pythonw.exe'
    pythonw.touch()
    script = folder / entry
    monkeypatch.setattr(sys, 'executable', str(python))
    monkeypatch.setattr(sys, 'argv', [str(script), '--unrelated'])
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    assert autostart.startup_command() == f'"{pythonw}" "{script}" --background'


def test_source_startup_without_pythonw_uses_current_interpreter(tmp_path, monkeypatch):
    python = tmp_path / 'python.exe'
    script = tmp_path / 'main.py'
    monkeypatch.setattr(sys, 'executable', str(python))
    monkeypatch.setattr(sys, 'argv', [str(script)])
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    command = autostart.startup_command()
    assert str(python) in command
    assert str(script) in command
    assert command.endswith(' --background')


def test_packaged_startup_uses_persistent_executable_path(tmp_path, monkeypatch):
    executable = tmp_path / 'Formula OCR' / 'FormulaOCR-WebView2.exe'
    monkeypatch.setattr(sys, 'executable', str(executable))
    monkeypatch.setattr(sys, 'argv', [str(tmp_path / '_MEI123' / 'main_webview2.py')])
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert autostart.startup_command() == f'"{executable}" --background'


@pytest.fixture
def registry(monkeypatch):
    registry = MagicMock()
    registry.OpenKey.return_value.__enter__.return_value = registry.handle
    registry.CreateKeyEx.return_value.__enter__.return_value = registry.handle
    monkeypatch.setattr(sys, 'platform', 'win32')
    with patch.dict(sys.modules, {'winreg': registry}):
        yield registry


def test_enable_registers_only_current_user_run_value(registry):
    with patch.object(autostart, 'startup_command', return_value='"C:\\My App\\FormulaOCR.exe" --background'):
        autostart.set_enabled(True)
    registry.CreateKeyEx.assert_called_once_with(
        registry.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, registry.KEY_SET_VALUE)
    registry.SetValueEx.assert_called_once_with(
        registry.handle, 'FormulaOCR', 0, registry.REG_SZ, '"C:\\My App\\FormulaOCR.exe" --background')
    registry.DeleteValue.assert_not_called()


def test_reads_actual_startup_registration(registry):
    registry.QueryValueEx.return_value = ('"C:\\FormulaOCR.exe" --background', registry.REG_SZ)
    assert autostart.is_enabled()
    registry.QueryValueEx.assert_called_with(registry.handle, 'FormulaOCR')
    registry.QueryValueEx.return_value = ('', registry.REG_SZ)
    assert not autostart.is_enabled()
    registry.QueryValueEx.side_effect = FileNotFoundError
    assert not autostart.is_enabled()


def test_disable_removes_only_our_value_and_is_idempotent(registry):
    autostart.set_enabled(False)
    registry.OpenKey.assert_called_once_with(
        registry.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, registry.KEY_SET_VALUE)
    registry.DeleteValue.assert_called_once_with(registry.handle, 'FormulaOCR')
    registry.CreateKeyEx.assert_not_called()
    registry.DeleteValue.side_effect = FileNotFoundError
    autostart.set_enabled(False)
    registry.OpenKey.side_effect = FileNotFoundError
    autostart.set_enabled(False)


def test_registry_permission_errors_are_reported(registry):
    registry.OpenKey.side_effect = PermissionError('read denied')
    with pytest.raises(PermissionError, match='read denied'):
        autostart.is_enabled()
    registry.CreateKeyEx.side_effect = PermissionError('write denied')
    with pytest.raises(PermissionError, match='write denied'):
        autostart.set_enabled(True)
    with pytest.raises(PermissionError, match='read denied'):
        autostart.set_enabled(False)


def test_autostart_on_unsupported_platform(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert not autostart.is_enabled()
    with pytest.raises(OSError, match='Windows'):
        autostart.set_enabled(True)


@pytest.mark.parametrize('backend', ['qt', 'webview2'])
@pytest.mark.parametrize('arguments,background', [([], False), (['--background'], True)])
def test_entrypoint_routes_background_flag_to_window(monkeypatch, backend, arguments, background):
    from formula_ocr.app import main

    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(sys, 'argv', ['main.py', *arguments])
    with patch('formula_ocr.app.QApplication') as application, patch(
        'formula_ocr.app.Window'
    ) as window, patch('formula_ocr.app.sys.exit') as exit_app:
        application.return_value.exec.return_value = 0
        main(preview_backend=backend)
    window.assert_called_once_with(preview_backend=backend)
    window.return_value.show_on_startup.assert_called_once_with(background=background)
    application.return_value.setQuitOnLastWindowClosed.assert_called_once_with(False)
    exit_app.assert_called_once_with(0)
