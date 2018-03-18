import betamax
import unittest

with betamax.Betamax.configure() as config:
    config.cassette_library_dir = 'tests/data/cassettes'

    
class BaseTest(unittest.TestCase):

    def load_policy(
            self, data, config=None, session_factory=None):
        pass

        
        
