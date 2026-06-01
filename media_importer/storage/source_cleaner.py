import sys
from media_importer.domains.source_cleaning import cleaner as _cleaner

sys.modules[__name__] = _cleaner
