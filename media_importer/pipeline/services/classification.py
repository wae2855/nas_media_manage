import sys
from media_importer.domains.import_flow.services import classification as _classification

sys.modules[__name__] = _classification
