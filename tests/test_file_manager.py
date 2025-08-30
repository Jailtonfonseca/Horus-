import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

# Adiciona o diretório raiz ao sys.path para encontrar o pacote 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.file_manager import get_file_content, apply_changes, setup_workspace

class TestFileManager(unittest.TestCase):

    def test_get_file_content_exists(self):
        """Testa a leitura de um arquivo que existe."""
        mock_file_content = "Hello, World!"
        # Simula um arquivo existente com conteúdo
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)) as mock_file:
                content = get_file_content("dummy/path.txt")
                self.assertEqual(content, mock_file_content)
                mock_file.assert_called_once_with("dummy/path.txt", 'r', encoding='utf-8')

    def test_get_file_content_not_exists(self):
        """Testa a leitura de um arquivo que não existe."""
        with patch("os.path.exists", return_value=False):
            content = get_file_content("nonexistent/path.txt")
            self.assertIsNone(content)

    @patch('src.file_manager.os.makedirs')
    def test_setup_workspace(self, mock_makedirs):
        """Testa a criação do workspace."""
        setup_workspace("/tmp/test_workspace")
        mock_makedirs.assert_called_once_with(os.path.join("/tmp/test_workspace", "backups"), exist_ok=True)

    @patch('src.file_manager.os.fdopen')
    @patch('src.file_manager.os.replace')
    @patch('src.file_manager.tempfile.mkstemp')
    @patch('src.file_manager.create_backup')
    @patch('src.file_manager.get_file_content', return_value='original content')
    def test_apply_changes_replace_file(self, mock_get_content, mock_create_backup, mock_mkstemp, mock_replace, mock_fdopen):
        """Testa a ação 'replace_file'."""
        mock_mkstemp.return_value = (123, '/tmp/tempfile')

        # Configura o mock para ser um context manager
        mock_fd_obj = MagicMock()
        mock_fd_obj.__enter__.return_value = mock_fd_obj
        mock_fd_obj.__exit__.return_value = None
        mock_fdopen.return_value = mock_fd_obj

        workspace = "/workspace"
        change = {
            "action": "replace_file",
            "target_path": "test.txt",
            "code": "new content"
        }

        result = apply_changes(workspace, change, dry_run=False)

        self.assertTrue(result)
        mock_create_backup.assert_called_once()
        mock_fdopen.assert_called_with(123, 'w', encoding='utf-8')
        mock_fd_obj.write.assert_called_once_with("new content")
        mock_replace.assert_called_once_with('/tmp/tempfile', os.path.join(workspace, "test.txt"))

    @patch('src.file_manager.os.fdopen')
    @patch('src.file_manager.os.replace')
    @patch('src.file_manager.tempfile.mkstemp')
    @patch('src.file_manager.create_backup')
    @patch('src.file_manager.get_file_content')
    def test_apply_changes_append(self, mock_get_content, mock_create_backup, mock_mkstemp, mock_replace, mock_fdopen):
        """Testa a ação 'append'."""
        mock_mkstemp.return_value = (123, '/tmp/tempfile')
        mock_get_content.return_value = "original content"

        # Configura o mock para ser um context manager
        mock_fd_obj = MagicMock()
        mock_fd_obj.__enter__.return_value = mock_fd_obj
        mock_fd_obj.__exit__.return_value = None
        mock_fdopen.return_value = mock_fd_obj

        workspace = "/workspace"
        change = {
            "action": "append",
            "target_path": "test.txt",
            "code": "appended content"
        }

        result = apply_changes(workspace, change, dry_run=False)

        self.assertTrue(result)
        mock_create_backup.assert_called_once()
        mock_fdopen.assert_called_with(123, 'w', encoding='utf-8')
        self.assertEqual(mock_fd_obj.write.call_count, 2)
        mock_fd_obj.write.assert_any_call("original content")
        mock_fd_obj.write.assert_any_call("\nappended content")
        mock_replace.assert_called_once()

    def test_apply_changes_noop(self):
        """Testa a ação 'noop'."""
        result = apply_changes("/workspace", {"action": "noop"}, dry_run=False)
        self.assertTrue(result)

    def test_apply_changes_dry_run(self):
        """Testa se o dry_run previne a escrita."""
        change = {
            "action": "replace_file",
            "target_path": "test.txt",
            "code": "new content"
        }
        with patch('src.file_manager.create_backup') as mock_backup:
            result = apply_changes("/workspace", change, dry_run=True)
            self.assertTrue(result)
            mock_backup.assert_not_called()

if __name__ == '__main__':
    unittest.main()
