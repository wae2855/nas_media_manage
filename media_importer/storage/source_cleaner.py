import sys
from media_importer.features.source_cleaning import cleaner as _cleaner

sys.modules[__name__] = _cleaner
