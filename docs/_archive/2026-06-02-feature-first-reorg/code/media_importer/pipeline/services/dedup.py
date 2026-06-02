import sys
from media_importer.features.import_flow.services import dedup as _dedup

sys.modules[__name__] = _dedup
