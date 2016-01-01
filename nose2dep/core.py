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
soft_dependencies = defaultdict(set)
default_priority = 50
priorities = defaultdict(lambda: default_priority)


def depends(func=None, after=None, before=None, priority=None):
    """Decorator to specify test dependencies

    :param after: The test needs to run after this/these tests. String or list of strings.
    :param before: The test needs to run before this/these tests. String or list of strings.
    """
    if not (func is None or inspect.ismethod(func) or inspect.isfunction(func)):
        raise ValueError("depends decorator can only be used on functions or methods")
    if not (after or before or priority):
        raise ValueError("depends decorator needs at least one argument")

    # This avoids some nesting in the decorator
    # If called without func the decorator was called with optional args
    # so we'll return a function with those args filled in.
    if func is None:
        return partial(depends, after=after, before=before, priority=priority)

    if after is None:
        after = []
    if before is None:
        before = []

    def handle_dep(prerequisites, _before=True):
        if type(prerequisites) is not list:
            prerequisites = [prerequisites]

        prerequisite_names = [prereq.__name__ if hasattr(prereq, '__call__') else prereq for prereq in prerequisites]

        for prereq_name in prerequisite_names:
            if func.__name__ == prereq_name:
                raise ValueError("Test '{}' cannot depend on itself".format(func.__name__))

            if _before:
                soft_dependencies[prereq_name].add(func.__name__)
            else:
                dependencies[func.__name__].add(prereq_name)

    handle_dep(before)
    handle_dep(after, False)

    if priority:
        priorities[func.__name__] = priority

    return func


def merge_dicts(d1, d2):
    d3 = defaultdict(set)
    for k, v in chain(iter(d1.items()), iter(d2.items())):
        d3[k] |= v
    return d3


def split_on_condition(seq, condition):
    """Split a sequence into two iterables without looping twice"""
    l1, l2 = tee((condition(item), item) for item in seq)
    return (i for p, i in l1 if p), (i for p, i in l2 if not p)


def lo_prio(x):
    return priorities[x] <= default_priority

def extractTests(ts):
    tests = []
    for item in ts:
        if isinstance(item, unittest.TestCase):
            tests.append(item)
        else:
            tests.extend(extractTests(item))
    return tests

class NoseDep(Plugin):
    """Allow specifying test dependencies with the depends decorator."""
    configSection = "nosedep"
    commandLineSwitch = (None, 'nosedep', 'Honour dependency ordering')

    def __init__(self):
        super(NoseDep, self).__init__()
        self.results = {}

    @staticmethod
    def calculate_dependencies():
        """Calculate test dependencies
        First do a topological sorting based on the dependencies.
        Then sort the different dependency groups based on priorities.
        """
        order = []
        for g in toposort(merge_dicts(dependencies, soft_dependencies)):
            for t in sorted(g, key=lambda x: (priorities[x], x)):
                order.append(t)
        return order

    def orderTests(self, all_tests):
        """Determine test ordering based on the dependency graph"""
        order = self.calculate_dependencies()
        ordered_all_tests = sorted(list(all_tests.keys()), key=lambda x: (priorities[x], x))
        conds = [lambda t: True, lambda t: t in all_tests]

        no_deps = (t for t in ordered_all_tests if t not in order and conds[0](t))
        deps = (t for t in order if conds[1](t))
        no_deps_l, no_deps_h = split_on_condition(no_deps, lo_prio)
        return unittest.TestSuite([all_tests[t] for t in chain(no_deps_l, deps, no_deps_h)])

    def startTestRun(self, event):
        """Prepare and determine test ordering"""
        tests = extractTests(event.suite)
        all_tests = {self.test_name(test): test for test in tests}
        event.suite = self.orderTests(all_tests)

    def dependency_failed(self, test):
        """Returns an error string if any of the dependencies failed"""
        for d in (self.test_name(i) for i in (dependencies[test] | soft_dependencies[test])):
            if self.results.get(d) and self.results.get(d) != 'passed':
                return "Required test '{}' {}".format(d, self.results.get(d).upper())
        return None

    def dependency_ran(self, test):
        """Returns an error string if any of the dependencies did not run"""
        for d in (self.test_name(i) for i in dependencies[test]):
            if d not in self.results:
                return "Required test '{}' did not run (does it exist?)".format(d)
        return None

    def startTest(self, event):
        """Skip or Error the test if the dependencies are not fulfilled"""
        tn = self.test_name(event.test)

        res = self.dependency_failed(tn)
        if res:
            setattr(event.test, tn, partial(event.test.skipTest, res))
            return

        res = self.dependency_ran(tn)
        if res:
            setattr(event.test, tn, partial(event.test.fail, res))
            return

    @staticmethod
    def test_name(test):
        # Internally we are currently only using the method/function names
        # could be that we might want to use the full qualified name in the future

        test_name = test.id() if isinstance(test, unittest.TestCase) else test

        return test_name.split('.')[-1]

    def testOutcome(self, event):
        """The result object does not store successful results, so we have to do it"""
        self.results[self.test_name(event.test)] = event.outcome