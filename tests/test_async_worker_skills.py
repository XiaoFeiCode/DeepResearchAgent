import unittest

from agent.async_graphs import _prepare_worker_skill_source


class AsyncWorkerSkillTests(unittest.TestCase):
    def test_each_worker_receives_only_its_assigned_skills(self):
        expected = {
            "database": {"database-query"},
            "internet": {"web-research"},
            "ragflow": {"ragflow-knowledge-base"},
        }
        for target_agent, expected_names in expected.items():
            with self.subTest(target_agent=target_agent):
                backend = _prepare_worker_skill_source(target_agent)
                result = backend.ls("/skills/")
                names = {
                    entry["path"].rstrip("/").split("/")[-1]
                    for entry in result.entries or []
                    if entry["is_dir"]
                }
                self.assertEqual(names, expected_names)


if __name__ == "__main__":
    unittest.main()
