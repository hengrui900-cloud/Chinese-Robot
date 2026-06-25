import threading
import time
import unittest
from unittest.mock import patch

from web_simulation import app as web_app


class RecognizerConcurrencyTests(unittest.TestCase):
    def test_concurrent_get_recognizer_creates_one_instance(self):
        original_recognizer = web_app.recognizer
        original_index = web_app.current_camera_index
        original_source = web_app.current_camera_source
        created = []
        result_instances = []
        state_lock = threading.Lock()

        class FakeCameraManager:
            camera_source = 1
            source_label = "1"

        class FakeRecognizer:
            def __init__(self, camera_index, camera_source):
                time.sleep(0.05)
                self.camera_manager = FakeCameraManager()
                with state_lock:
                    created.append(self)

            def start(self):
                return True

        def get_instance():
            result = web_app.get_recognizer(camera_index=1)
            with state_lock:
                result_instances.append(result)

        try:
            web_app.recognizer = None
            with patch.object(web_app, "BoardRecognizer", FakeRecognizer):
                threads = [threading.Thread(target=get_instance) for _ in range(4)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=1.0)
        finally:
            web_app.recognizer = original_recognizer
            web_app.current_camera_index = original_index
            web_app.current_camera_source = original_source

        self.assertEqual(len(created), 1)
        self.assertEqual(len({id(instance) for instance in result_instances}), 1)


if __name__ == "__main__":
    unittest.main()
