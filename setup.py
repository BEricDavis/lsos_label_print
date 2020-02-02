# distutils script for use with cx_freeze
# run:
#     C:\Users\Eric\Anaconda3\envs\print_labels_env\Scripts\activate print_labels_env
#     from a Windows cmd window run 'python setup.py build ' in this directory

import sys
from cx_Freeze import setup, Executable

setup(
    name='LSOS Label Printer',
    version='4.1',
    description='Trying to print labels',
    executables=[Executable(script="print_labels.py")]
)