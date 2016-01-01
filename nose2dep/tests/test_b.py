import unittest
import nose2
from nose2.main import PluggableTestProgram
from nose2dep.core import depends

from collections import OrderedDict

class OutcomeTracker(object):
    def __init__(self):
        self.dict = OrderedDict()

    def testOutcome(self, event):
        self.dict[event.test.id()] = event.outcome

class NoseDepPluginTester(unittest.TestCase):
    class TC(unittest.TestCase):

        @depends(priority=200)
        def test_a(self):
            pass

        @depends(before="test_c")
        def test_b(self):
            self.fail()

        def test_c(self):
            pass

    class TC2(unittest.TestCase):
        @depends(after="test_z")
        def test_impossible(self):
            pass


    def setUp(self):
        self._outcometracker = OutcomeTracker()
        self._program =  PluggableTestProgram(exit=False,
                                              plugins=['nose2dep.core'],
                                              excludePlugins=['nose2.plugins.loader.discovery',
                                                              'nose2.plugins.loader.testcases',
                                                              'nose2.plugins.loader.functions',
                                                              'nose2.plugins.loader.testclasses',
                                                              'nose2.plugins.loader.generators',
                                                              'nose2.plugins.loader.parameters',
                                                              'nose2.plugins.loader.loadtests',
                                                              'nose2.plugins.result'],
                                              extraHooks=[('testOutcome', self._outcometracker)])

    def test_basic_function(self):
        self._program.test = unittest.defaultTestLoader.loadTestsFromTestCase(self.TC)
        self._program.runTests()
        # Expected behaviour: test_b runs first (as test_c depends on it and test_a has a higher priority value), then test_c, then test_a.
        # Because test_b fails and test_c depends on it, test_c is skipped.
        self.assertEqual(OrderedDict([('__main__.TC.test_b', 'failed'), ('__main__.TC.test_c', 'skipped'), ('__main__.TC.test_a', 'passed')]), self._outcometracker.dict)

    def test_unsatisfied_dependency(self):
        self._program.test = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(self.TC2)])
        self._program.runTests()
        # Expected behaviour: test_impossible fails, as it must run after the nonexistent test_z.
        self.assertEqual(OrderedDict([('__main__.TC2.test_impossible', 'failed')]), self._outcometracker.dict)

    def test_no_args_exception(self):
        # Using @depends with no arguments should cause an exception
        with self.assertRaises(ValueError):
            class TC3(unittest.TestCase):
                @depends
                def test_impossible(self):
                    pass

    def test_classmethod_exception(self):
        # Using @depends on something that's not a method or function should cause an exception
        with self.assertRaises(ValueError):
            class TC3(unittest.TestCase):
                @depends(priority=1)
                @classmethod
                def test_impossible(self):
                    pass

    def test_circular_exception(self):
        # Making a test depend on itself should cause an exception
        with self.assertRaises(ValueError):
            class TC3(unittest.TestCase):
                @depends(before="test_impossible")
                def test_impossible(self):
                    pass

if __name__ == "__main__":
    unittest.main()