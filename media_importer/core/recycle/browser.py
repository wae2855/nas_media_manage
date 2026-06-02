import sys
from media_importer.features.recycle import browser as _browser

sys.modules[__name__] = _browser
