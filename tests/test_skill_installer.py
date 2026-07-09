from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skills.installer import (
    SkillInstallError,
    _validate_files,
    download_skill,
    install_skill,
    list_installed_skills,
)


SKILL_CONTENT = b"""---
name: custom-research
description: A test research workflow.
---

# Custom research

Use trusted sources and preserve links.
"""


class SkillInstallerTests(unittest.TestCase):
    def test_installs_and_isolates_skills_by_user(self):
        files = {PurePosixPath("SKILL.md"): SKILL_CONTENT}
        with TemporaryDirectory() as temporary_root:
            with (
                patch("skills.installer.INSTALLED_SKILLS_ROOT", Path(temporary_root)),
                patch("skills.installer.download_skill", return_value=files),
            ):
                first = install_skill(
                    skill_url="https://github.com/example/skills/tree/main/custom-research",
                    target_agent="internet",
                    user_id="alice",
                )
                self.assertEqual(first["name"], "custom-research")
                self.assertEqual(
                    list_installed_skills("alice"),
                    [{"name": "custom-research", "target_agent": "internet"}],
                )
                self.assertEqual(list_installed_skills("bob"), [])

    def test_rejects_executable_files_by_default(self):
        with patch.dict("os.environ", {"SKILL_ALLOW_EXECUTABLE_FILES": "false"}):
            with self.assertRaisesRegex(SkillInstallError, "默认禁止"):
                _validate_files(
                    {
                        PurePosixPath("SKILL.md"): SKILL_CONTENT,
                        PurePosixPath("scripts/run.py"): b"print('unsafe')",
                    }
                )

    def test_rejects_non_github_source(self):
        with self.assertRaisesRegex(SkillInstallError, "只允许"):
            download_skill("https://example.com/SKILL.md")

    def test_rejects_builtin_skill_name(self):
        files = {
            PurePosixPath("SKILL.md"): SKILL_CONTENT.replace(
                b"name: custom-research",
                b"name: web-research",
            )
        }
        with TemporaryDirectory() as temporary_root:
            with (
                patch("skills.installer.INSTALLED_SKILLS_ROOT", Path(temporary_root)),
                patch("skills.installer.download_skill", return_value=files),
            ):
                with self.assertRaisesRegex(SkillInstallError, "不能覆盖"):
                    install_skill(
                        skill_url="https://github.com/example/skills/tree/main/web-research",
                        target_agent="internet",
                        user_id="alice",
                    )


if __name__ == "__main__":
    unittest.main()
