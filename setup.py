#!/usr/bin/env python
import sys
import os
import time
import subprocess
from setuptools import setup, find_packages

long_description = """GUI for TomoPY, eesspecially for 13BM"""

install_reqs = ['numpy', 'scipy', 'scikit-image', 'netCDF4', 'tomopy',
                'dxchange', 'wxPython', 'wxmplot', 'pyshortcuts']

apps = [('tomopy_13bmapp', 'tomopy_ui:tomopy_13bmapp'),]

gui_scripts = ['{0:s}={1:s}'.format(*app) for app in apps]

setup(name='tomopy_gui',
      version='1.0',
      author='Brandt M. Gibson',
      author_email='brandt.m.gibson@vanderbilt.edu',
      url='https://github.com/bramgibs/TomoPy_GUI',
      license = 'OSI Approved :: MIT License',
      python_requires='>=3.5',
      description='TomoPy GUI',
      long_description=long_description,
      packages=find_packages(),
      package_data={'tomopy_ui': ['icons/*']},
      install_requires=install_reqs,
      classifiers=['Intended Audience :: End Users/Desktop',
                   'Intended Audience :: Science/Research',
                   'Intended Audience :: Developers',
                   'Operating System :: MacOS :: MacOS X',
                   'Operating System :: Microsoft :: Windows',
                   'Operating System :: POSIX',
                   'Programming Language :: Python'],
      entry_points={'gui_scripts': gui_scripts})

def fix_darwin_exe(script):
    "fix anaconda python apps on MacOs to launch with pythonw"
    pyapp = os.path.join(sys.prefix, 'python.app',
                         'Contents', 'MacOS', 'python')
    if os.path.exists(script):
        with open(script, 'r') as fh:
            try:
                lines = fh.readlines()
            except IOError:
                lines = ['-']
        time.sleep(.05)
        if len(lines) > 1:
            text = ["#!%s\n" % pyapp]
            text.extend(lines[1:])
            with open(script, 'w') as fh:
                fh.write("".join(text))

# post-install:
#   1. fix scripts on MacOSX + Anaconda3 to use Python.app
#   2. make sure script is executable by itself on Linux
#   3. try to create desktop shortcut by running script with `-s` option.
if len(sys.argv) > 1 and (sys.argv[1] == 'install'):
    bindir = 'bin'
    pyexe = os.path.join(sys.prefix, bindir, 'python')
    if os.uname == 'win':
        pyexe = os.path.join(sys.prefix, 'python.exe')
        bindir = 'Scripts'

    for script, func in apps:
        fullscript = os.path.join(sys.prefix, bindir, script)
        if (sys.platform.lower().startswith('darwin') and 'Anaconda' in sys.version):
            fix_darwin_exe(fullscript)
        elif sys.platform.lower().startswith('linux'):
            os.chmod(fullscript, 493)

        time.sleep(0.25)
        ret = subprocess.check_call((pyexe, fullscript, '-s'))
