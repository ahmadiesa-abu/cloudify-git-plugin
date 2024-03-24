import os
import sys
from setuptools import setup
from setuptools import find_packages


# Get the plugin version from the yaml , so you would have one source of truth
def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_file='plugin.yaml'):
    lines = read(rel_file)
    for line in lines.splitlines():
        if 'package_version' in line:
            split_line = line.split(':')
            line_no_space = split_line[-1].replace(' ', '')
            line_no_quotes = line_no_space.replace('\'', '')
            return line_no_quotes.strip('\n')
    raise RuntimeError('Unable to find version string.')


install_requires = []

if sys.version_info.major == 3 and sys.version_info.minor == 6:
    install_requires += [
        'cloudify-common>=4.5.5',
        'GitPython==3.1.18',  # shared download resource
        'gitdb==4.0.8'  # shared download resource
    ]
else:
    install_requires += [
        'cloudify-common>=7.0.2',
        'GitPython>=3.1.40',  # shared download resource
        'gitdb>=4.0.11',  # shared download resource
    ]


setup(
    name='cloudify-git-plugin',
    version=get_version(),
    author='Cloudify Platform Ltd.',
    author_email='hello@cloudify.co',
    description='A Cloudify plugin for git',
    packages=find_packages(exclude=['tests*']),
    license='LICENSE',
    zip_safe=False,
    install_requires=install_requires,
    test_requires=[
        "cloudify-common>=4.5.5",
        "nose"
    ]
)
