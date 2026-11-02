from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

from formula_ocr.app import SettingsDialog

APP = QApplication.instance() or QApplication([])


def test_provider_switch_and_save(tmp_path):
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    parent.settings.setValue('provider', 'OpenAI 官方')
    parent.settings.setValue('base', 'https://api.openai.com/v1')
    parent.api_key = 'openai-test-key'
    parent.session_keys = {'https://api.openai.com/v1': parent.api_key}
    parent.update_model_label = lambda: None
    dialog = SettingsDialog(parent)
    dialog.provider.setCurrentText('DeepSeek 官方')
    assert dialog.base.text() == 'https://api.deepseek.com'
    assert dialog.model.text() == 'deepseek-flash'
    assert dialog.key.text() == ''
    dialog.key.setText('deepseek-test-key')
    dialog.remember.setChecked(True)
    with patch('formula_ocr.app.keyring.set_password') as save:
        dialog.save()
        save.assert_called_once_with('FormulaOCR', 'https://api.deepseek.com', 'deepseek-test-key')
    assert parent.settings.value('provider') == 'DeepSeek 官方'
    parent.settings.sync()
    assert 'test-key' not in (tmp_path / 'settings.ini').read_text()
    second = SettingsDialog(parent)
    second.provider.setCurrentText('OpenAI 官方')
    assert second.key.text() == 'openai-test-key'
    second.provider.setCurrentText('硅基流动')
    assert second.base.text() == 'https://api.siliconflow.cn/v1'
    assert second.key.text() == ''
    dialog.close()
    second.close()
