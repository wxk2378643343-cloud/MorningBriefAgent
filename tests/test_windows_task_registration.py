from pathlib import Path
import unittest


class WindowsTaskRegistrationTests(unittest.TestCase):
    def test_registration_removes_obsolete_vbs_startup_entries(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "register_windows_tasks.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("Remove-LegacyBotStartup", script)
        self.assertIn('"FeishuBidirectionalBot.lnk"', script)
        self.assertIn('"FeishuBidirectionalBot"', script)
        self.assertIn("Remove-ItemProperty", script)
        self.assertNotIn("run_bot_silent.vbs", script)
        self.assertNotIn("start_feishu_bot_silent.vbs", script)

    def test_bot_task_uses_pythonw_without_a_vbs_wrapper(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "register_windows_tasks.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("-Execute $pythonwPath", script)
        self.assertIn(
            'Register-LogonWorkflow -Name "MorningBriefAgentBot" '
            '-Arguments "-m server.feishu_bot_server"',
            script,
        )


if __name__ == "__main__":
    unittest.main()
