"""Completion-detection tests for the native AGY transcript bridge."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.agent import agy_bridge


def row(step, msg_type, status="DONE", content=None, tool_calls=None):
    value = {
        "step_index": step,
        "type": msg_type,
        "status": status,
    }
    if content is not None:
        value["content"] = content
    if tool_calls is not None:
        value["tool_calls"] = tool_calls
    return value


class TranscriptFile:
    def __init__(self, root):
        self.path = Path(root) / "transcript.jsonl"

    def write(self, *rows):
        self.path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
            encoding="utf-8",
        )


class AgyBridgeCompletionTests(unittest.TestCase):
    def test_snapshot_ignores_rows_before_request_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(8, "PLANNER_RESPONSE", content="旧回答"),
                row(9, "GENERIC", content="旧工具结果"),
            )

            snapshot = agy_bridge.read_transcript_snapshot(
                str(transcript.path),
                min_step=10,
            )

        self.assertIsNone(snapshot.candidate_content)
        self.assertEqual(snapshot.latest_step, 9)

    def test_highest_step_includes_tool_and_empty_planner_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(20, "PLANNER_RESPONSE", content="旧回答"),
                row(
                    21,
                    "PLANNER_RESPONSE",
                    tool_calls={"name": "run_command", "args": {}},
                ),
                row(22, "GENERIC", content="工具结果"),
            )

            highest = agy_bridge.get_highest_transcript_step(
                str(transcript.path)
            )

        self.assertEqual(highest, 22)

    def test_tool_call_planner_row_is_not_user_facing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    30,
                    "PLANNER_RESPONSE",
                    content="不应发送",
                    tool_calls={"name": "view_file", "args": {}},
                )
            )

            snapshot = agy_bridge.read_transcript_snapshot(str(transcript.path))

        self.assertIsNone(snapshot.candidate_content)

    def test_candidate_followed_by_tool_activity_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(35, "PLANNER_RESPONSE", content="先给出一个阶段结论。"),
                row(
                    36,
                    "PLANNER_RESPONSE",
                    tool_calls={"name": "run_command", "args": {}},
                ),
            )

            answer, step = agy_bridge.get_latest_response_from_transcript(
                str(transcript.path),
                min_step=35,
            )

        self.assertIsNone(answer)
        self.assertEqual(step, 35)

    def test_snapshot_tracks_and_resolves_background_task(self):
        task_id = "conversation-id/task-41"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    40,
                    "GENERIC",
                    status="RUNNING",
                    content=f"Tool is running with task id: {task_id}",
                ),
                row(41, "PLANNER_RESPONSE", content="正在查询，请稍候..."),
            )
            running = agy_bridge.read_transcript_snapshot(str(transcript.path))

            transcript.write(
                row(
                    40,
                    "GENERIC",
                    status="RUNNING",
                    content=f"Tool is running with task id: {task_id}",
                ),
                row(41, "PLANNER_RESPONSE", content="正在查询，请稍候..."),
                row(
                    42,
                    "SYSTEM_MESSAGE",
                    content=f'sender={task_id} Task id "{task_id}" finished with result: ok',
                ),
            )
            finished = agy_bridge.read_transcript_snapshot(str(transcript.path))

        self.assertEqual(running.active_task_ids, (task_id,))
        self.assertEqual(finished.active_task_ids, ())

    def test_unresolved_background_task_blocks_substantive_candidate(self):
        task_id = "conversation-id/task-45"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    45,
                    "GENERIC",
                    status="RUNNING",
                    content=f"Tool is running with task id: {task_id}",
                ),
                row(
                    46,
                    "PLANNER_RESPONSE",
                    content="目前检查结果正常，但后台核验仍未结束。",
                ),
            )

            answer, _ = agy_bridge.get_latest_response_from_transcript(
                str(transcript.path),
                min_step=45,
            )

        self.assertIsNone(answer)

    def test_finishing_one_background_task_does_not_clear_another(self):
        first = "conversation-id/task-47"
        second = "conversation-id/task-48"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(47, "GENERIC", "RUNNING", f"task id: {first}"),
                row(48, "GENERIC", "RUNNING", f"task id: {second}"),
                row(
                    49,
                    "SYSTEM_MESSAGE",
                    content=f'sender={first} Task id "{first}" finished with result: ok',
                ),
            )

            snapshot = agy_bridge.read_transcript_snapshot(str(transcript.path))

        self.assertEqual(snapshot.active_task_ids, (second,))

    def test_timer_helper_and_task_log_path_do_not_block_final_answer(self):
        task_id = "conversation-id/task-2801"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    2801,
                    "GENERIC",
                    status="RUNNING",
                    content=(
                        f"Tool is running as a background task with task id: {task_id}\n"
                        "Task Description: Timer: 12s, Prompt: Wait for task completion\n"
                        "Task logs are available at: "
                        "file:///brain/conversation-id/.system_generated/tasks/task-2801.log"
                    ),
                ),
                row(
                    2897,
                    "PLANNER_RESPONSE",
                    content="所有任务已经完成，这是最终答复。",
                ),
            )

            snapshot = agy_bridge.read_transcript_snapshot(
                str(transcript.path),
                min_step=2788,
            )
            answer, step = agy_bridge.get_latest_response_from_transcript(
                str(transcript.path),
                min_step=2788,
            )

        self.assertEqual(snapshot.active_task_ids, ())
        self.assertEqual(answer, "所有任务已经完成，这是最终答复。")
        self.assertEqual(step, 2897)

    def test_task_log_path_is_not_mistaken_for_a_second_task(self):
        task_id = "conversation-id/task-90"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    90,
                    "GENERIC",
                    status="RUNNING",
                    content=(
                        f"background task id: {task_id}\n"
                        "Task Description: Verify output\n"
                        "Task logs: file:///brain/.system_generated/tasks/task-90.log"
                    ),
                ),
            )

            snapshot = agy_bridge.read_transcript_snapshot(str(transcript.path))

        self.assertEqual(snapshot.active_task_ids, (task_id,))

    def test_partial_trailing_jsonl_row_is_ignored_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(row(50, "PLANNER_RESPONSE", content="完整回答"))
            with transcript.path.open("a", encoding="utf-8") as handle:
                handle.write('{"step_index": 51, "type": "PLANNER_RESP')

            snapshot = agy_bridge.read_transcript_snapshot(str(transcript.path))

        self.assertEqual(snapshot.latest_step, 50)
        self.assertEqual(snapshot.candidate_content, "完整回答")

    def test_content_wording_does_not_affect_structural_readiness(self):
        content = "正在运行是系统的正常最终状态，请稍候也可能是引用文本。"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(row(55, "PLANNER_RESPONSE", content=content))

            answer, step = agy_bridge.get_latest_response_from_transcript(
                str(transcript.path),
                min_step=55,
            )

        self.assertEqual(answer, content)
        self.assertEqual(step, 55)

    def test_real_incident_shape_selects_only_later_final_answer(self):
        task_id = "conversation-id/task-1268"
        with tempfile.TemporaryDirectory() as tmp:
            transcript = TranscriptFile(tmp)
            transcript.write(
                row(
                    1268,
                    "GENERIC",
                    status="RUNNING",
                    content=f"background task id: {task_id}",
                ),
                row(
                    1269,
                    "PLANNER_RESPONSE",
                    content="正在调研待办任务与日历现有排期，请稍候...",
                ),
                row(
                    1270,
                    "SYSTEM_MESSAGE",
                    content=f'sender={task_id} Task id "{task_id}" finished with result: ok',
                ),
                row(
                    1271,
                    "PLANNER_RESPONSE",
                    tool_calls={"name": "run_command", "args": {}},
                ),
                row(1272, "GENERIC", content="command completed"),
                row(
                    1285,
                    "PLANNER_RESPONSE",
                    content="已完成日历调整与公安备案任务更新。",
                ),
            )

            snapshot = agy_bridge.read_transcript_snapshot(
                str(transcript.path),
                min_step=1268,
            )
            answer, step = agy_bridge.get_latest_response_from_transcript(
                str(transcript.path),
                min_step=1268,
            )

        self.assertEqual(snapshot.active_task_ids, ())
        self.assertTrue(snapshot.candidate_is_latest)
        self.assertEqual(answer, "已完成日历调整与公安备案任务更新。")
        self.assertEqual(step, 1285)

    def test_waiter_blocks_active_task_and_waits_for_stable_final(self):
        progress = agy_bridge.TranscriptSnapshot(
            latest_step=51,
            candidate_content="正在处理，请稍候...",
            candidate_step=51,
            active_task_ids=("conversation/task-50",),
        )
        final = agy_bridge.TranscriptSnapshot(
            latest_step=60,
            candidate_content="任务已经全部完成。",
            candidate_step=60,
            active_task_ids=(),
        )
        clock_values = iter((0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 2.0, 2.0))

        with mock.patch.object(
            agy_bridge,
            "read_transcript_snapshot",
            side_effect=(progress, final, final),
        ), mock.patch.object(
            agy_bridge.time,
            "monotonic",
            side_effect=lambda: next(clock_values),
        ), mock.patch.object(
            agy_bridge.time,
            "sleep",
            return_value=None,
        ):
            answer = agy_bridge.wait_for_agy_response(
                "conversation",
                start_step=50,
                max_wait_sec=10,
                settle_sec=0.4,
                poll_interval_sec=0.01,
            )

        self.assertEqual(answer, "任务已经全部完成。")

    def test_waiter_timeout_never_returns_incomplete_candidate(self):
        incomplete = agy_bridge.TranscriptSnapshot(
            latest_step=71,
            candidate_content="任意阶段性内容",
            candidate_step=71,
            active_task_ids=("conversation/task-70",),
        )
        clock_values = iter((0.0, 0.0, 2.0, 2.0))

        with mock.patch.object(
            agy_bridge,
            "read_transcript_snapshot",
            return_value=incomplete,
        ), mock.patch.object(
            agy_bridge.time,
            "monotonic",
            side_effect=lambda: next(clock_values),
        ), mock.patch.object(
            agy_bridge.time,
            "sleep",
            return_value=None,
        ):
            answer = agy_bridge.wait_for_agy_response(
                "conversation",
                start_step=70,
                max_wait_sec=1,
                settle_sec=0,
                poll_interval_sec=0.01,
            )

        self.assertIn("等待超时", answer)
        self.assertNotIn("任意阶段性内容", answer)


if __name__ == "__main__":
    unittest.main()
