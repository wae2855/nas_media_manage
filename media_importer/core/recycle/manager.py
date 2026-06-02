import sys
from media_importer.features.recycle import manager as _manager

sys.modules[__name__] = _manager
