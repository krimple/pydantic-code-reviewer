"""Tests for repository cloning and management."""

from pathlib import Path
from unittest.mock import patch

from code_reviewer.repo import cleanup_repo, clone_repo


class TestCloneRepo:
    @patch("code_reviewer.repo.Repo")
    def test_clone_creates_temp_dir(self, mock_repo_class):
        path = clone_repo("https://github.com/user/repo", "main")
        assert isinstance(path, Path)
        assert path.exists()
        mock_repo_class.clone_from.assert_called_once()
        # Cleanup
        cleanup_repo(path)

    @patch("code_reviewer.repo.Repo")
    def test_clone_passes_branch(self, mock_repo_class):
        path = clone_repo("https://github.com/user/repo", "develop")
        mock_repo_class.clone_from.assert_called_once_with(
            "https://github.com/user/repo", str(path), branch="develop"
        )
        cleanup_repo(path)


class TestCleanupRepo:
    def test_cleanup_removes_directory(self, tmp_path):
        test_dir = tmp_path / "test-repo"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test")
        assert test_dir.exists()
        cleanup_repo(test_dir)
        assert not test_dir.exists()

    def test_cleanup_nonexistent_is_noop(self, tmp_path):
        fake_path = tmp_path / "nonexistent"
        cleanup_repo(fake_path)  # Should not raise
