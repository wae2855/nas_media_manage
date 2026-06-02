import sys
from media_importer.features.import_flow.services import source_cleanup as _source_cleanup

sys.modules[__name__] = _source_cleanup
