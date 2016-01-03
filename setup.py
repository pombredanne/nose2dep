from setuptools import setup

setup(
        name='nose2dep',
        version='0.2.2',
        packages=['nose2dep'],
        url='https://github.com/rkday/nose2dep',
        license='MIT',
        author='Rob Day',
        author_email='rkd@rkd.me.uk',
        description='The nosedep test dependency tool, ported to nose2',
        install_requires=['nose2', 'toposort'],
        test_suite="tests",
)
