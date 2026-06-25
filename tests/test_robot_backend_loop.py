import unittest
import time
from unittest.mock import patch

from robot.protocol import RobotArmCommand, RobotSendResult
from web_simulation import app as web_app


class RobotBackendLoopTests(unittest.TestCase):
    def setUp(self):
        self.original_game_state = dict(web_app.game_state)
        web_app.game_state['is_game_running'] = False
        web_app.game_state['robot_mode'] = 'hardware'
        self.client = web_app.app.test_client()

    def tearDown(self):
        web_app.game_state.clear()
        web_app.game_state.update(self.original_game_state)

    def test_backend_uses_top_right_origin_for_ai_move(self):
        command = web_app.uci_to_robot_command("a0i9", board_state={})

        self.assertEqual(command, [272, 272, 0, 0, 0])

    def test_startup_ip_parameter_accepts_last_octet_or_full_ip(self):
        self.assertEqual(
            web_app.parse_robot_ip_parameter("103", "192.168.0.102"),
            "192.168.0.103",
        )
        self.assertEqual(
            web_app.parse_robot_ip_parameter("192.168.0.104", "192.168.0.102"),
            "192.168.0.104",
        )
        self.assertEqual(
            web_app.parse_robot_ip_parameter("", "192.168.0.102"),
            "192.168.0.102",
        )
        with self.assertRaises(ValueError):
            web_app.parse_robot_ip_parameter("300", "192.168.0.102")

    def test_startup_board_spacing_requires_positive_integer(self):
        self.assertEqual(web_app.parse_positive_int_parameter("35", 34, "横向"), 35)
        self.assertEqual(web_app.parse_positive_int_parameter("", 34, "横向"), 34)
        with self.assertRaises(ValueError):
            web_app.parse_positive_int_parameter("0", 34, "横向")
        with self.assertRaises(ValueError):
            web_app.parse_positive_int_parameter("34.5", 34, "横向")

    def test_backend_sends_five_value_command_to_netassist(self):
        class FakeRobotClient:
            def __init__(self):
                self.sent_command = None
                self.sent_timeout = None

            def send_robot_command(self, command, timeout=None):
                self.sent_command = command
                self.sent_timeout = timeout
                return RobotSendResult(
                    success=True,
                    command_text="0,0,272,272,1",
                    response="STATE:5,RESULT:1",
                )

        fake_client = FakeRobotClient()
        with patch.object(web_app, "get_robot_tcp_client", return_value=fake_client) as get_client:
            result = web_app.send_robot_command_to_controller([0, 0, 272, 272, 1])

        get_client.assert_called_once_with()
        self.assertTrue(result.success)
        self.assertIsInstance(fake_client.sent_command, RobotArmCommand)
        self.assertEqual(fake_client.sent_command.to_wire(), "0,0,272,272,1")
        self.assertEqual(fake_client.sent_timeout, web_app.config.ROBOT_CAPTURE_COMMAND_TIMEOUT)
        self.assertNotIn("PLAN", result.command_text)

    def test_backend_uses_normal_timeout_for_non_capture_robot_command(self):
        class FakeRobotClient:
            def __init__(self):
                self.sent_timeout = None

            def send_robot_command(self, command, timeout=None):
                self.sent_timeout = timeout
                return RobotSendResult(
                    success=True,
                    command_text=command.to_wire(),
                    response="STATE:5,RESULT:1",
                )

        fake_client = FakeRobotClient()
        with patch.object(web_app, "get_robot_tcp_client", return_value=fake_client):
            result = web_app.send_robot_command_to_controller([0, 0, 272, 272, 0])

        self.assertTrue(result.success)
        self.assertEqual(fake_client.sent_timeout, web_app.config.ROBOT_NORMAL_COMMAND_TIMEOUT)

    def test_backend_homing_uses_shared_tcp_client(self):
        class FakeRobotClient:
            def __init__(self):
                self.homing_command = None

            def send_homing_command(self, command, timeout=None):
                self.homing_command = command
                return RobotSendResult(
                    success=True,
                    command_text="-17.1848,-55.6304,0,0,99",
                    response="STATE:5,RESULT:1,CMD:99",
                )

        fake_client = FakeRobotClient()
        with patch.object(web_app, "get_robot_tcp_client", return_value=fake_client) as get_client:
            result = web_app.send_homing_command_to_controller()

        get_client.assert_called_once_with()
        self.assertTrue(result.homing_acknowledged)
        self.assertEqual(
            fake_client.homing_command.to_wire(),
            "-17.1848,-55.6304,0,0,99",
        )

    def test_start_game_homes_before_enabling_game(self):
        homing_result = RobotSendResult(
            success=True,
            command_text="-17.1848,-55.6304,0,0,99",
            response="STATE:5,RESULT:1,CMD:99\r\n",
        )

        with (
            patch.object(
                web_app,
                "send_homing_command_to_controller",
                return_value=homing_result,
                create=True,
            ) as sender,
            patch.object(web_app, "get_ai_engine") as get_engine,
        ):
            response = self.client.post("/api/game/start", json={})

        data = response.get_json()
        sender.assert_called_once_with()
        get_engine.return_value.reset_game.assert_called_once_with()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertTrue(data["homing_acknowledged"])
        self.assertTrue(web_app.game_state["is_game_running"])

    def test_start_game_stays_stopped_when_homing_fails(self):
        homing_result = RobotSendResult(
            success=False,
            command_text="-17.1848,-55.6304,0,0,99",
            error="connection refused",
        )

        with (
            patch.object(
                web_app,
                "send_homing_command_to_controller",
                return_value=homing_result,
                create=True,
            ),
            patch.object(web_app, "get_ai_engine") as get_engine,
        ):
            response = self.client.post("/api/game/start", json={})

        data = response.get_json()
        get_engine.assert_not_called()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(data["success"])
        self.assertFalse(web_app.game_state["is_game_running"])

    def test_start_game_simulation_mode_skips_homing(self):
        with (
            patch.object(web_app, "send_homing_command_to_controller") as homing,
            patch.object(web_app, "get_ai_engine") as get_engine,
        ):
            response = self.client.post("/api/game/start", json={"mode": "simulation"})

        data = response.get_json()
        homing.assert_not_called()
        get_engine.return_value.reset_game.assert_called_once_with()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["robot_mode"], "simulation")
        self.assertEqual(web_app.game_state["robot_mode"], "simulation")

    def test_apply_ai_best_move_in_hardware_mode_predisplays_before_controller_wait(self):
        web_app.game_state.update(
            robot_mode="hardware",
            board_state={"0,0": "r"},
            move_history=["a0a1"],
            display_history=["red a0a1"],
            turn_count=1,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
        )
        observed_during_send = {}

        def fake_sender(_command):
            observed_during_send.update(
                board_state=dict(web_app.game_state["board_state"]),
                move_history=list(web_app.game_state["move_history"]),
                robot_moving=web_app.game_state["robot_moving"],
                vision_pause_reason=web_app.game_state["vision_pause_reason"],
            )
            return RobotSendResult(
                success=True,
                command_text="272,0,272,30,0",
                response="STATE:5,RESULT:1,CMD:0",
            )

        with patch.object(web_app, "send_robot_command_to_controller", side_effect=fake_sender):
            result = web_app.apply_ai_best_move("a9a8")

        self.assertTrue(result.success)
        self.assertEqual(observed_during_send["move_history"], ["a0a1", "a9a8"])
        self.assertEqual(observed_during_send["board_state"], {"0,1": "r"})
        self.assertTrue(observed_during_send["robot_moving"])
        self.assertEqual(observed_during_send["vision_pause_reason"], "robot_move")
        self.assertFalse(web_app.game_state["robot_moving"])
        self.assertEqual(web_app.game_state["vision_pause_reason"], "")
        self.assertEqual(web_app.game_state["vision_pause_until"], 0.0)

    def test_hardware_ai_ack_resumes_dynamic_recognition_immediately(self):
        class FakeRecognizer:
            def __init__(self):
                self.synced_boards = []
                self.reset_count = 0

            def sync_dynamic_baseline(self, board):
                self.synced_boards.append(dict(board))

            def reset_dynamic_tracking(self):
                self.reset_count += 1

        fake_recognizer = FakeRecognizer()
        web_app.game_state.update(
            robot_mode="hardware",
            board_state={"0,0": "r"},
            move_history=["a0a1"],
            display_history=["red a0a1"],
            turn_count=1,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=False,
        )

        with (
            patch.object(web_app, "recognizer", fake_recognizer),
            patch.object(
                web_app,
                "send_robot_command_to_controller",
                return_value=RobotSendResult(
                    success=True,
                    command_text="272,0,272,30,0",
                    response="STATE:5,RESULT:1,CMD:0",
                ),
            ),
        ):
            result = web_app.apply_ai_best_move("a9a8")

        self.assertTrue(result.success)
        self.assertFalse(web_app.game_state["awaiting_physical_baseline"])
        self.assertFalse(web_app.game_state["robot_moving"])
        self.assertEqual(web_app.game_state["vision_pause_until"], 0.0)
        self.assertEqual(web_app.game_state["vision_pause_reason"], "")
        self.assertEqual(web_app.game_state["post_robot_guard_until"], 0.0)
        self.assertEqual(fake_recognizer.reset_count, 1)
        self.assertEqual(fake_recognizer.synced_boards[-1], {(0, 1): "r"})

    def test_capture_ai_ack_resumes_without_settle_window(self):
        web_app.game_state.update(
            robot_mode="hardware",
            board_state={"1,2": "c", "6,2": "P"},
            move_history=["g4g7"],
            display_history=["red g4g7"],
            turn_count=1,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=False,
            post_robot_guard_until=0.0,
        )

        with patch.object(
            web_app,
            "send_robot_command_to_controller",
            return_value=RobotSendResult(
                success=True,
                command_text="238,60,68,60,1",
                response="STATE:5,RESULT:1",
            ),
        ):
            result = web_app.apply_ai_best_move("b7g7")

        self.assertTrue(result.success)
        self.assertFalse(web_app.game_state["awaiting_physical_baseline"])
        self.assertTrue(web_app.game_state["last_robot_move_capture"])
        self.assertEqual(web_app.game_state["vision_pause_reason"], "")
        self.assertEqual(web_app.game_state["vision_pause_until"], 0.0)
        self.assertEqual(web_app.game_state["post_robot_guard_until"], 0.0)

    def test_dynamic_endpoint_locks_robot_physical_baseline_without_accepting_move(self):
        class FakeCameraManager:
            def capture_frame(self):
                return object()

        class FakeDynamicRecognizer:
            def __init__(self):
                self.camera_manager = FakeCameraManager()
                self.dynamic_tracker = type("Tracker", (), {"saved_board": None})()
                self.synced_boards = []
                self.reset_count = 0

            def sync_dynamic_baseline(self, board):
                self.synced_boards.append(dict(board))

            def reset_dynamic_tracking(self):
                self.reset_count += 1
                self.dynamic_tracker.saved_board = None

            def recognize_dynamic_frame(self, _frame):
                return {
                    "stable": True,
                    "event": "move",
                    "message": "容错识别: C (4, 7)->(4, 3)，忽略噪声点6个",
                    "move": {
                        "from": {"col": 4, "row": 7},
                        "to": {"col": 4, "row": 3},
                        "piece": "C",
                    },
                    "board_state": {(4, 3): "C"},
                }

        fake_recognizer = FakeDynamicRecognizer()
        web_app.game_state.update(
            is_game_running=True,
            robot_mode="hardware",
            board_state={"4,3": "C"},
            current_fen="9/9/9/9/9/9/4C4/9/9/9 w - - 0 1",
            move_history=["b6e6", "c7e6"],
            display_history=["b6e6", "204,60,136,90,1"],
            turn_count=2,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=True,
        )

        with patch.object(web_app, "get_recognizer", return_value=fake_recognizer):
            self.client.post("/api/recognize/dynamic", json={})
            self.client.post("/api/recognize/dynamic", json={})
            response = self.client.post("/api/recognize/dynamic", json={})

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["event"], "robot_board_confirmed")
        self.assertIsNone(data["move"])
        self.assertFalse(web_app.game_state["awaiting_physical_baseline"])
        self.assertEqual(fake_recognizer.synced_boards[-1], {(4, 3): "C"})
        self.assertEqual(web_app.game_state["move_history"], ["b6e6", "c7e6"])

    def test_dynamic_endpoint_requires_consecutive_robot_baseline_matches(self):
        class FakeCameraManager:
            def capture_frame(self):
                return object()

        class FakeDynamicRecognizer:
            def __init__(self):
                self.camera_manager = FakeCameraManager()
                self.dynamic_tracker = type("Tracker", (), {"saved_board": None})()
                self.synced_boards = []
                self.reset_count = 0

            def sync_dynamic_baseline(self, board):
                self.synced_boards.append(dict(board))

            def reset_dynamic_tracking(self):
                self.reset_count += 1
                self.dynamic_tracker.saved_board = None

            def recognize_dynamic_frame(self, _frame):
                return {
                    "stable": True,
                    "event": "initial_locked",
                    "message": "initial locked",
                    "move": None,
                    "board_state": {(4, 3): "C"},
                }

        fake_recognizer = FakeDynamicRecognizer()
        web_app.game_state.update(
            is_game_running=True,
            robot_mode="hardware",
            board_state={"4,3": "C"},
            current_fen="9/9/9/9/9/9/4C4/9/9/9 w - - 0 1",
            move_history=["b6e6", "c7e6"],
            display_history=["b6e6", "204,60,136,90,1"],
            turn_count=2,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=True,
            robot_baseline_match_count=0,
        )

        with patch.object(web_app, "get_recognizer", return_value=fake_recognizer):
            first = self.client.post("/api/recognize/dynamic", json={}).get_json()
            second = self.client.post("/api/recognize/dynamic", json={}).get_json()

        self.assertEqual(first["event"], "robot_board_waiting")
        self.assertEqual(second["event"], "robot_board_waiting")
        self.assertTrue(web_app.game_state["awaiting_physical_baseline"])
        self.assertEqual(fake_recognizer.synced_boards, [])
        self.assertEqual(web_app.game_state["move_history"], ["b6e6", "c7e6"])

    def test_dynamic_endpoint_keeps_waiting_when_robot_baseline_mismatches_expected_board(self):
        class FakeCameraManager:
            def capture_frame(self):
                return object()

        class FakeDynamicRecognizer:
            def __init__(self):
                self.camera_manager = FakeCameraManager()
                self.dynamic_tracker = type("Tracker", (), {"saved_board": None})()
                self.reset_count = 0
                self.synced_boards = []

            def sync_dynamic_baseline(self, board):
                self.synced_boards.append(dict(board))

            def reset_dynamic_tracking(self):
                self.reset_count += 1
                self.dynamic_tracker.saved_board = None

            def recognize_dynamic_frame(self, _frame):
                return {
                    "stable": True,
                    "event": "initial_locked",
                    "message": "初始基准已锁定",
                    "move": None,
                    "board_state": {(4, 3): "C", (1, 0): "r"},
                }

        fake_recognizer = FakeDynamicRecognizer()
        web_app.game_state.update(
            is_game_running=True,
            robot_mode="hardware",
            board_state={"4,3": "C", "0,0": "r"},
            current_fen="r8/9/9/9/9/9/4C4/9/9/9 w - - 0 1",
            move_history=["b6e6", "c7e6"],
            display_history=["b6e6", "204,60,136,90,1"],
            turn_count=2,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=True,
        )

        with patch.object(web_app, "get_recognizer", return_value=fake_recognizer):
            response = self.client.post("/api/recognize/dynamic", json={})

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["event"], "robot_board_waiting")
        self.assertIsNone(data["move"])
        self.assertTrue(web_app.game_state["awaiting_physical_baseline"])
        self.assertEqual(fake_recognizer.reset_count, 1)
        self.assertEqual(fake_recognizer.synced_boards, [])
        self.assertEqual(web_app.game_state["move_history"], ["b6e6", "c7e6"])

    def test_dynamic_endpoint_ignores_player_like_move_during_post_robot_settle_guard(self):
        class FakeCameraManager:
            def capture_frame(self):
                return object()

        class FakeDynamicRecognizer:
            def __init__(self):
                self.camera_manager = FakeCameraManager()
                self.dynamic_tracker = type("Tracker", (), {"saved_board": {}})()
                self.synced_boards = []

            def sync_dynamic_baseline(self, board):
                self.synced_boards.append(dict(board))

            def recognize_dynamic_frame(self, _frame):
                return {
                    "stable": True,
                    "event": "move",
                    "message": "N (1, 9)->(2, 7)",
                    "move": {
                        "from": {"col": 1, "row": 9},
                        "to": {"col": 2, "row": 7},
                        "piece": "N",
                    },
                    "board_state": {
                        (0, 0): "r",
                        (2, 7): "N",
                    },
                }

        fake_recognizer = FakeDynamicRecognizer()
        web_app.game_state.update(
            is_game_running=True,
            robot_mode="hardware",
            board_state={"0,0": "r", "1,9": "N"},
            current_fen="r8/9/9/9/9/9/9/9/9/1N7 w - - 0 1",
            move_history=["g4g7", "b7g7"],
            display_history=["g4g7", "238,60,68,60,1"],
            turn_count=2,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
            awaiting_physical_baseline=False,
            post_robot_guard_until=time.monotonic() + 10.0,
        )

        with patch.object(web_app, "get_recognizer", return_value=fake_recognizer):
            response = self.client.post("/api/recognize/dynamic", json={})

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["event"], "robot_settling")
        self.assertIsNone(data["move"])
        self.assertEqual(web_app.game_state["move_history"], ["g4g7", "b7g7"])
        self.assertEqual(web_app.game_state["turn_count"], 2)
        self.assertEqual(fake_recognizer.synced_boards[-1], {(0, 0): "r", (1, 9): "N"})

    def test_apply_ai_best_move_in_hardware_mode_keeps_predisplay_on_late_ack_failure(self):
        web_app.game_state.update(
            robot_mode="hardware",
            board_state={"0,0": "r"},
            move_history=["a0a1"],
            display_history=["red a0a1"],
            turn_count=1,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
        )

        with patch.object(
            web_app,
            "send_robot_command_to_controller",
            return_value=RobotSendResult(
                success=False,
                command_text="272,0,272,30,0",
                error="timed out",
            ),
        ):
            result = web_app.apply_ai_best_move("a9a8")

        self.assertFalse(result.success)
        self.assertEqual(web_app.game_state["move_history"], ["a0a1", "a9a8"])
        self.assertEqual(web_app.game_state["board_state"], {"0,1": "r"})
        self.assertTrue(web_app.game_state["robot_moving"])
        self.assertEqual(web_app.game_state["vision_pause_reason"], "robot_move")

    def test_apply_ai_best_move_ignores_duplicate_tail_without_resending(self):
        web_app.game_state.update(
            robot_mode="hardware",
            board_state={"0,1": "r"},
            move_history=["a0a1", "a9a8"],
            display_history=["red a0a1", "272,0,272,30,0"],
            turn_count=2,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
        )

        with patch.object(web_app, "send_robot_command_to_controller") as sender:
            result = web_app.apply_ai_best_move("a9a8")

        sender.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.response, "DUPLICATE_AI_MOVE_IGNORED")
        self.assertFalse(web_app.game_state["robot_moving"])

    def test_repeated_last_player_move_after_ai_is_duplicate(self):
        web_app.game_state.update(
            move_history=["e6g7", "c7e6"],
            last_player_move="e6g7",
        )

        self.assertTrue(web_app.is_duplicate_player_move("e6g7"))
        self.assertFalse(web_app.is_duplicate_player_move("a0a1"))

    def test_apply_ai_best_move_in_simulation_mode_never_sends_to_stm32(self):
        web_app.game_state.update(
            robot_mode="simulation",
            board_state={"0,9": "R"},
            move_history=["a0a1"],
            display_history=["red a0a1"],
            turn_count=1,
            robot_moving=False,
            vision_pause_reason="",
            vision_pause_until=0.0,
        )

        with patch.object(web_app, "send_robot_command_to_controller") as sender:
            result = web_app.apply_ai_best_move("a9a8")

        sender.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(web_app.game_state["move_history"], ["a0a1", "a9a8"])
        self.assertTrue(web_app.game_state["robot_moving"])
        self.assertEqual(web_app.game_state["vision_pause_reason"], "simulation_move")

    def test_robot_status_endpoint_is_passive_by_default(self):
        with patch.object(
            web_app,
            "probe_robot_controller",
            create=True,
        ) as probe:
            response = self.client.get("/api/robot/status")

        data = response.get_json()
        probe.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(data["connected"])
        self.assertEqual(data["status"], "not_probed")
        self.assertEqual(data["host"], "192.168.0.102")
        self.assertEqual(data["port"], 8086)

    def test_robot_status_endpoint_can_probe_when_explicitly_requested(self):
        probe_result = RobotSendResult(success=True, command_text="")

        with patch.object(
            web_app,
            "probe_robot_controller",
            return_value=probe_result,
            create=True,
        ) as probe:
            response = self.client.get("/api/robot/status?probe=1")

        data = response.get_json()
        probe.assert_called_once_with()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["connected"])
        self.assertEqual(data["status"], "probed")
        self.assertEqual(data["host"], "192.168.0.102")
        self.assertEqual(data["port"], 8086)

    def test_probe_robot_controller_keeps_shared_tcp_client_open(self):
        class FakeRobotClient:
            def __init__(self):
                self.connected = False
                self.closed = False
                self.timeout = None

            def connect(self, timeout=None):
                self.connected = True
                self.timeout = timeout
                return object()

            def close(self):
                self.closed = True

        fake_client = FakeRobotClient()
        with patch.object(web_app, "get_robot_tcp_client", return_value=fake_client):
            result = web_app.probe_robot_controller()

        self.assertTrue(result.success)
        self.assertTrue(fake_client.connected)
        self.assertFalse(fake_client.closed)
        self.assertEqual(fake_client.timeout, web_app.robot_network_timeout())


if __name__ == "__main__":
    unittest.main()
