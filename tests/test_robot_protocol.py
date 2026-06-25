import socket
import threading
import time
import unittest

import robot.protocol as robot_protocol
from robot.protocol import (
    BoardToArmConfig,
    RobotArmCommand,
    RobotHomingCommand,
    RobotPersistentClient,
    RobotSendResult,
    send_robot_command,
    uci_to_arm_command,
)


class RobotProtocolTests(unittest.TestCase):
    def test_homing_command_uses_exact_motor_angles_and_signal(self):
        command = robot_protocol.RobotHomingCommand(-17.1848, -55.6304)

        self.assertEqual(command.to_wire(), "-17.1848,-55.6304,0,0,99")

    def test_homing_sender_requires_command_specific_completion_ack(self):
        ready = threading.Event()
        received = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1,CMD:99\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = robot_protocol.send_homing_command(
            robot_protocol.RobotHomingCommand(-17.1848, -55.6304),
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.acknowledged_for(99))
        self.assertEqual(received, ["-17.1848,-55.6304,0,0,99\r\n"])

    def test_homing_sender_accepts_finish_state_completion_without_command_id(self):
        ready = threading.Event()
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                with conn:
                    conn.recv(1024)
                    conn.sendall(b"STATE:5,RESULT:1\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = robot_protocol.send_homing_command(
            robot_protocol.RobotHomingCommand(-17.1848, -55.6304),
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.homing_acknowledged)

    def test_homing_sender_rejects_normal_move_ack(self):
        ready = threading.Event()
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                with conn:
                    conn.recv(1024)
                    conn.sendall(b"STATE:5,RESULT:1,CMD:0\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = robot_protocol.send_homing_command(
            robot_protocol.RobotHomingCommand(-17.1848, -55.6304),
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertFalse(result.success)
        self.assertIn("homing acknowledgement", result.error)

    def test_idle_state_without_homing_command_id_is_not_homing_ack(self):
        result = RobotSendResult(
            success=True,
            command_text="-17.1848,-55.6304,0,0,99",
            response="STATE:0,RESULT:1\r\n",
        )

        self.assertFalse(result.homing_acknowledged)

    def test_robot_connection_probe_reports_reachable_endpoint(self):
        ready = threading.Event()
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                conn.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = robot_protocol.probe_robot_connection(
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.command_text, "")

    def test_uci_move_uses_measured_board_dimensions(self):
        config = BoardToArmConfig(
            origin_x=0,
            origin_y=0,
            file_spacing_mm=34,
            rank_spacing_mm=30,
            river_spacing_mm=32,
        )

        command = uci_to_arm_command("a0i9", board_state={}, config=config)

        self.assertEqual(command.to_tuple(), [272, 272, 0, 0, 0])
        self.assertEqual(command.to_wire(), "272,272,0,0,0")

    def test_middle_square_uses_independent_horizontal_and_vertical_spacing(self):
        config = BoardToArmConfig(
            origin_x=10,
            origin_y=20,
            file_spacing_mm=34,
            rank_spacing_mm=30,
            river_spacing_mm=32,
        )

        command = uci_to_arm_command("c3g7", board_state={}, config=config)

        self.assertEqual(command.to_tuple(), [214, 202, 78, 80, 0])

    def test_crossing_river_uses_32_mm_vertical_spacing(self):
        config = BoardToArmConfig(
            file_spacing_mm=34,
            rank_spacing_mm=30,
            river_spacing_mm=32,
        )

        command = uci_to_arm_command("e5e4", board_state={}, config=config)

        self.assertEqual(command.to_tuple(), [136, 120, 136, 152, 0])

    def test_capture_signal_uses_target_occupancy_before_move(self):
        config = BoardToArmConfig(
            origin_x=0,
            origin_y=0,
            file_spacing_mm=34,
            rank_spacing_mm=30,
            river_spacing_mm=32,
        )
        board_state = {"8,0": "r"}

        command = uci_to_arm_command("a0i9", board_state=board_state, config=config)

        self.assertEqual(command.signal, 1)

    def test_sender_accepts_only_five_value_robot_arm_command(self):
        class FakeMotionPlan:
            def to_wire(self):
                return "PLAN;0;3;1,2,PICK"

        with self.assertRaises(TypeError):
            send_robot_command(FakeMotionPlan())

    def test_robot_move_rejects_non_finish_state_completion_ack(self):
        result = RobotSendResult(
            success=True,
            command_text="0,0,272,272,0",
            response="STATE:0,RESULT:1\r\n",
        )

        self.assertFalse(result.motion_acknowledged)

    def test_robot_move_accepts_state5_result1_completion_ack(self):
        result = RobotSendResult(
            success=True,
            command_text="0,0,272,272,0",
            response="STATE:5,RESULT:1\r\n",
        )

        self.assertTrue(result.motion_acknowledged)

    def test_invalid_uci_move_is_rejected(self):
        with self.assertRaises(ValueError):
            uci_to_arm_command("z9a0")

    def test_tcp_sender_reports_success_and_response(self):
        ready = threading.Event()
        received = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = send_robot_command(
            RobotArmCommand(0, 0, 272, 272, 1),
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.response, "STATE:5,RESULT:1")
        self.assertEqual(received, ["0,0,272,272,1\r\n"])

    def test_tcp_sender_waits_for_state5_result_after_intermediate_state(self):
        ready = threading.Event()
        received = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:0,RESULT:1\r\n")
                    time.sleep(0.05)
                    conn.sendall(b"STATE:5,RESULT:1\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        result = send_robot_command(
            RobotArmCommand(0, 0, 272, 272, 1),
            host="127.0.0.1",
            port=port_holder[0],
            timeout=1.0,
        )

        thread.join(timeout=2.0)
        self.assertTrue(result.success, result.error)
        self.assertIn("STATE:5,RESULT:1", result.response)
        self.assertEqual(received, ["0,0,272,272,1\r\n"])

    def test_persistent_client_reuses_one_socket_for_homing_and_move(self):
        ready = threading.Event()
        received = []
        accepted_count = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(1)
                ready.set()
                conn, _ = sock.accept()
                accepted_count.append(1)
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1,CMD:99\r\n")
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1,CMD:0\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        client = RobotPersistentClient("127.0.0.1", port_holder[0], timeout=1.0)
        try:
            homing = client.send_homing_command(RobotHomingCommand(-17.1848, -55.6304))
            move = client.send_robot_command(RobotArmCommand(0, 0, 272, 272, 1))
        finally:
            client.close()

        thread.join(timeout=2.0)
        self.assertTrue(homing.homing_acknowledged, homing.error)
        self.assertTrue(move.motion_acknowledged, move.error)
        self.assertEqual(len(accepted_count), 1)
        self.assertEqual(received, ["-17.1848,-55.6304,0,0,99\r\n", "0,0,272,272,1\r\n"])

    def test_persistent_client_reconnects_when_peer_closes_after_homing_ack(self):
        ready = threading.Event()
        received = []
        accepted_count = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(2)
                sock.settimeout(3.0)
                ready.set()

                conn, _ = sock.accept()
                accepted_count.append(1)
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1,CMD:99\r\n")

                conn, _ = sock.accept()
                accepted_count.append(1)
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    conn.sendall(b"STATE:5,RESULT:1,CMD:0\r\n")

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        client = RobotPersistentClient("127.0.0.1", port_holder[0], timeout=1.0)
        try:
            homing = client.send_homing_command(RobotHomingCommand(-17.1848, -55.6304))
            move = client.send_robot_command(RobotArmCommand(68, 0, 136, 60, 0))
        finally:
            client.close()

        thread.join(timeout=4.0)
        self.assertTrue(homing.homing_acknowledged, homing.error)
        self.assertTrue(move.motion_acknowledged, move.error)
        self.assertEqual(len(accepted_count), 2)
        self.assertEqual(received, ["-17.1848,-55.6304,0,0,99\r\n", "68,0,136,60,0\r\n"])

    def test_persistent_client_does_not_resend_motion_command_after_no_reply(self):
        ready = threading.Event()
        received = []
        accepted_count = []
        port_holder = []

        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                port_holder.append(sock.getsockname()[1])
                sock.listen(2)
                sock.settimeout(3.0)
                ready.set()

                conn, _ = sock.accept()
                accepted_count.append(1)
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))
                    time.sleep(0.25)

                sock.settimeout(0.5)
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    return
                accepted_count.append(1)
                with conn:
                    received.append(conn.recv(1024).decode("ascii"))

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        client = RobotPersistentClient("127.0.0.1", port_holder[0], timeout=0.1)
        try:
            move = client.send_robot_command(RobotArmCommand(204, 60, 136, 90, 1), timeout=0.1)
        finally:
            client.close()

        thread.join(timeout=4.0)
        self.assertFalse(move.motion_acknowledged)
        self.assertIn("without any reply", move.error)
        self.assertEqual(len(accepted_count), 1)
        self.assertEqual(received, ["204,60,136,90,1\r\n"])


if __name__ == "__main__":
    unittest.main()
