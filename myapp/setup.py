from setuptools import setup

long_description = """
This is a foo app to exercise deployment to AWS
"""

setup(
    name="foo-",
    version="0.1-dev",
    description="Basic Data Structures",
    long_description=long_description,
    # The project URL.
    url='http://github.com/<jay-tyler/foo-git-deploy',
    # Author details
    author='Jason Tyler',
    author_email='jmtyler@gmail.com',
    # Choose your license
    #   and remember to include the license text in a 'docs' directory.
    # license='MIT',
    packages=['foo_git_deploy'],
    install_requires=['setuptools', ]
)