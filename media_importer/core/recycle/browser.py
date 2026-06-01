import sys
from media_importer.domains.recycle import browser as _browser

sys.modules[__name__] = _browser
