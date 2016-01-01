import unittest
from nose2dep.core import depends

class TC(unittest.TestCase):

    @depends(priority=200)
    def test_a(self):
        print("a")

    @depends(before="test_c")
    def test_b(self):
        print("b")
        self.fail()

    def test_c(self):
        print("c")
