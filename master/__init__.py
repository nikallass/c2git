"""
C2Git - Command & Control over Git
"""

from .cli import Commander
from .core import Crypto, GitHandler, SessionManager, JobManager
from .util import Config

__version__ = '0.1.0'
__author__ = 'Nikita Medvedev'
__email__ = 'nikandrmed@gmail.com'

__all__ = [
    'Commander',
    'SessionManager',
    'JobManager',
    'Config',
    'Crypto',
    'GitHandler'
]
