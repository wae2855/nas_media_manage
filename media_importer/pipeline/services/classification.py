import sys
from media_importer.features.import_flow.services import classification as _classification

sys.modules[__name__] = _classification
