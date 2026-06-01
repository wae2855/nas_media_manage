import sys
from media_importer.domains.import_flow.services import paths as _paths

sys.modules[__name__] = _paths
