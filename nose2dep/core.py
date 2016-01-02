"""Nosetest plugin for test dependencies.

Normally tests should not depend on each other - and it should be avoided
as long as possible. Optimally each test should be able to run in isolation.

However there might be rare cases or special circumstances where one would
want this. For example very slow integration tests where redoing what test
A did just to run test B would simply be too costly. Or temporarily while
testing or debugging. It's also possible that one wants some test to run first
as 'smoke tests' such that the rest can be skipped if those tests fail.

The current implementation allows marking tests with the `@depends` decorator
where it can be declared if the test needs to run before or after some
other specific test(s).

There is also support for skipping tests based on the dependency results,
thus if test B depends on test A and test A fails then B will be skipped
with the reason that A failed.

Nosedep also supports running the necessary dependencies for a single test,
thus if you specify to run only test B and test B depends on A; then A will
run before B to satisfy that dependency.

Note that 'before' dependencies are treated as soft. A soft dependency will only
affect the test ordering, not force inclusion. For example if we have::

    def test_a:
      pass

    @depends(before=test_a)
    def test_b:
      pass

and run all tests they would run in the order b,a. If you specify to run only
either one of them only that test would run. However changing it to::

    @depends(after=test_b)
    def test_a:
      pass

    def test_b:
      pass

would affect the case when you specify to run only test a, since it would have
to run test b first to specify the 'after' dependency since it's a 'hard' dependency.

Finally there is prioritization support. Each test can be given an integer priority
and the tests will run in order from lowest to highest. Dependencies take
precedence so in total the ordering will be:

1. All tests with a priority lower or equal to the default that are not part of any
   dependency chain ordered first by priority then by name.
2. Priority groups in order, while each priority group is internally ordered
   the same as point 1.
3. All tests with priority higher than the default that are not part of any
   dependency chain ordered first by priority then by name.

Default priority if not specified is 50.
"""
import inspect
import unittest
from collections import defaultdict
from functools import partial
from itertools import chain, tee

from nose2.events import Plugin
from toposort import toposort

dependencies = defaultdict(set)
default_priority = 50
priorities = defaultdict(lambda: default_priority)

class depends(object):
    def __init__(self, *args, after=None, before=None, priority=None):
        """Decorator to specify test dependencies

        :param after: The test needs to run after this/these tests. String or list of strings.
        :param before: The test needs to run before this/these tests. String or list of strings.
        """
        if not (after or before or priority):
            raise ValueError("depends decorator needs at least one argument")

        self.after = after or []
        self.before = before or []
        self.priority = priority or default_priority

    def handle_dep(self, fn, prerequisites, _before=True):
            if type(prerequisites) is not list:
                prerequisites = [prerequisites]

            prerequisite_names = [prereq.__name__ if hasattr(prereq, '__call__') else prereq for prereq in prerequisites]

            for prereq_name in prerequisite_names:
                if fn == prereq_name:
                    raise ValueError("Test '{}' cannot depend on itself".format(fn))

                if _before:
                    dependencies[prereq_name].add(fn)
                else:
                    dependencies[fn].add(prereq_name)

    def __call__(self, func):
        if not (func is None or inspect.ismethod(func) or inspect.isfunction(func)):
            raise ValueError("depends decorator can only be used on functions or methods")

        fn = func.__name__
        self.handle_dep(fn, self.before)
        self.handle_dep(fn, self.after, False)
        priorities[fn] = self.priority

        return func

def extractTests(ts):
    tests = []
    for item in ts:
        if isinstance(item, unittest.TestCase):
            tests.append(item)
        else:
            tests.extend(extractTests(item))
    return tests

class NoseDepUtils(object):
    @staticmethod
    def calculate_dependencies():
        """Calculate test dependencies
        First do a topological sorting based on the dependencies.
        Then sort the different dependency groups based on priorities.
        """
        order = []
        for group in toposort(dependencies):
            priority_sorted_group = sorted(group, key=lambda x: (priorities[x], x))
            order.extend(priority_sorted_group)

        return order

    @staticmethod
    def orderTests(all_tests):
        """Determine test ordering based on the dependency graph"""
        order = NoseDepUtils.calculate_dependencies()
        ordered_all_tests = sorted(list(all_tests.keys()), key=lambda x: (priorities[x], x))

        no_deps_l = (t for t in ordered_all_tests if t not in order and priorities[t] <= default_priority)
        no_deps_h = (t for t in ordered_all_tests if t not in order and priorities[t] > default_priority)
        deps = (t for t in order if t in all_tests)
        return unittest.TestSuite([all_tests[t] for t in chain(no_deps_l, deps, no_deps_h)])

    @staticmethod
    def test_name(test):
        # Internally we are currently only using the method/function names
        # could be that we might want to use the full qualified name in the future

        test_name = test.id() if isinstance(test, unittest.TestCase) else test

        return test_name.split('.')[-1]

    @staticmethod
    def dependency_failed(test, results):
        """Returns an error string if any of the dependencies failed"""
        for d in (NoseDepUtils.test_name(i) for i in dependencies[test]):
            if results.get(d) and results.get(d) != 'passed':
                return "Required test '{}' {}".format(d, results.get(d).upper())
        return None


class NoseDep(Plugin):
    """Allow specifying test dependencies with the depends decorator."""
    configSection = "nosedep"
    commandLineSwitch = (None, 'nosedep', 'Honour dependency ordering')

    def __init__(self):
        super(NoseDep, self).__init__()
        self.results = {}

    def startTestRun(self, event):
        """Prepare and determine test ordering"""
        tests = extractTests(event.suite)
        all_tests = {NoseDepUtils.test_name(test): test for test in tests}
        event.suite = NoseDepUtils.orderTests(all_tests)

    def startTest(self, event):
        """Skip or Error the test if the dependencies are not fulfilled"""
        tn = NoseDepUtils.test_name(event.test)

        res = NoseDepUtils.dependency_failed(tn, self.results)
        if res:
            setattr(event.test, tn, partial(event.test.skipTest, res))
            return

    def testOutcome(self, event):
        self.results[NoseDepUtils.test_name(event.test)] = event.outcome