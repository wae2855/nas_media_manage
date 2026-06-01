import sys
from media_importer.domains.recycle import manager as _manager

sys.modules[__name__] = _manager
