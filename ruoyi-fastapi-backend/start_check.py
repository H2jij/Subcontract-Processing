import sys
sys.path.insert(0, '.')
from config.env import GetConfig; GetConfig()
try:
    from server import create_app
    print("Import OK")
except Exception as e:
    import traceback
    traceback.print_exc()
