import unittest

from vision.stabilizer import DynamicBoardTracker, infer_one_move_from_occupancy


class DynamicBoardTrackerTests(unittest.TestCase):
    def test_sync_baseline_clears_stale_stable_buffer(self):
        tracker = DynamicBoardTracker(buffer_window=3, buffer_ratio=0.6, stable_seconds=0.0)
        old_board = {(0, 0): "r"}
        new_board = {(1, 0): "r"}

        tracker.buffer.add(old_board)
        tracker.buffer.add(old_board)
        self.assertTrue(tracker.buffer.get_stable())

        tracker.sync_baseline(new_board)

        self.assertEqual(tracker.saved_board, new_board)
        self.assertEqual(tracker.buffer.get_stable(), {})

    def test_noisy_inference_keeps_small_noise_tolerance(self):
        prev_board = {
            (4, 7): "C",
            (4, 5): "p",
            (4, 3): "p",
            (0, 0): "r",
        }
        curr_board = {
            (4, 5): "p",
            (4, 3): "C",
        }

        ok, message, move_points, logical_board = infer_one_move_from_occupancy(prev_board, curr_board)

        self.assertTrue(ok)
        self.assertIn("C (4, 7)->(4, 3)", message)
        self.assertEqual(move_points, ((4, 7), (4, 3)))
        self.assertEqual(logical_board[(4, 3)], "C")

    def test_noisy_inference_rejects_high_noise_capture_after_robot_move(self):
        prev_board = {
            (4, 7): "C",
            (4, 5): "p",
            (4, 3): "p",
            (0, 0): "r",
            (1, 0): "n",
            (2, 0): "b",
            (3, 0): "a",
        }
        curr_board = {
            (4, 5): "p",
            (4, 3): "C",
        }

        ok, message, move_points, logical_board = infer_one_move_from_occupancy(prev_board, curr_board)

        self.assertFalse(ok)
        self.assertIn("变动点数量", message)
        self.assertIsNone(move_points)
        self.assertIsNone(logical_board)


if __name__ == "__main__":
    unittest.main()
