import sys
from media_importer.features.import_flow.services import review as _review

sys.modules[__name__] = _review
