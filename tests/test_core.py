import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "exact_bag_png_mutil_process_slave01.py"
SPEC = importlib.util.spec_from_file_location("rosbag_video_extractor", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TimestampTests(unittest.TestCase):
    def test_format_normalizes_nanoseconds(self):
        self.assertEqual(MODULE._format_sec_nsec(1, 1_500_000_000), "0000000002.500000")

    def test_index_matching(self):
        result = MODULE._match_lidar_timestamps(
            [1.0, 2.0],
            ["l1", "l2", "l3"],
            [0.9, 2.1, 3.0],
            strategy="index",
        )
        self.assertEqual(result, ["l1", "l2"])

    def test_nearest_matching(self):
        result = MODULE._match_lidar_timestamps(
            [1.1, 2.8],
            ["l1", "l2", "l3"],
            [1.0, 2.0, 3.0],
            strategy="nearest",
        )
        self.assertEqual(result, ["l1", "l3"])

    def test_padding_reaches_expected_count(self):
        timestamps, times = MODULE._pad_lidar_series(
            ["0000000001.000000"], [1.0], expected=3, default_step_sec=0.1
        )
        self.assertEqual(len(timestamps), 3)
        self.assertEqual(times, [1.0, 1.1, 1.2])

    def test_frame_sampling(self):
        self.assertEqual(
            MODULE._sample_timestamp_series(["a", "b", "c", "d"], "frame", 2),
            ["a", "c"],
        )

    def test_frame_sampling_returns_source_indices(self):
        sampled, indices = MODULE._sample_timestamp_series(
            ["a", "b", "c", "d"], "frame", 2, return_indices=True
        )
        self.assertEqual(sampled, ["a", "c"])
        self.assertEqual(indices, [0, 2])


if __name__ == "__main__":
    unittest.main()
