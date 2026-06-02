import sys
from media_importer.features.import_flow.steps import scrape as _scrape

sys.modules[__name__] = _scrape
