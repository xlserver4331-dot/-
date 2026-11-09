import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from bbox_math import make_box, union_boxes, compare_box


class TestAABB(unittest.TestCase):
    def test_make(self):
        self.assertEqual(make_box([0, 1, 2], [2, 5, 6])["center"], [1, 3, 4])

    def test_union(self):
        a, b = make_box([-1, 0, 0], [1, 1, 1]), make_box([0, -2, 0], [3, 1, 4])
        self.assertEqual(union_boxes([a, b])["size"], [4, 3, 4])

    def test_no_reference(self):
        self.assertEqual(compare_box(make_box([0]*3, [1]*3), None, [0]*3)["status"], "PENDING")

    def test_fail_and_margin(self):
        actual = make_box([-0.1, 0, 0], [1, 1, 1])
        ref = {"min": [0]*3, "max": [1]*3}
        self.assertEqual(compare_box(actual, ref, [0]*3)["status"], "FAIL")
        self.assertEqual(compare_box(actual, ref, [0.11, 0, 0])["status"], "PASS")

    def test_bad_bounds(self):
        with self.assertRaises(ValueError):
            make_box([1]*3, [0]*3)


if __name__ == "__main__":
    unittest.main()
