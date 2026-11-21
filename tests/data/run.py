"""Run a module or all normal-use functional tests, without legacy-suite discovery."""
from pathlib import Path
import argparse
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).parent))
parser=argparse.ArgumentParser()
parser.add_argument('--module',choices=['all','crud','orchestration','cli','sample','branch','initialization','runtime','help','creative','dialogue','business','recall','presentation','maintenance','management','history','event_actions','capsule','migration','scene_revision','scene_maintenance','setup'],default='all')
parser.add_argument('--backend',choices=['sqlite'],default='sqlite')
args=parser.parse_args()
names=['crud','orchestration','cli','sample','branch','initialization','runtime','help','creative','dialogue','business','recall','presentation','maintenance','management','history','event_actions','capsule','migration','scene_revision','scene_maintenance','setup'] if args.module=='all' else [args.module]
suite=unittest.TestSuite()
def include(tests):
    for test in tests:
        if isinstance(test,unittest.TestSuite):
            include(test)
        elif getattr(test,'backend',None)==args.backend:
            suite.addTest(test)
for name in names:
    include(unittest.defaultTestLoader.loadTestsFromName('test_'+name))
if unittest.defaultTestLoader.errors:
    parser.exit(1,'\n'.join(unittest.defaultTestLoader.errors))
if suite.countTestCases()==0:
    raise SystemExit('No functional tests selected')
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
