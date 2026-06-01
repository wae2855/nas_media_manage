import sys
from media_importer.domains.import_flow.services import import_service as _import_service

sys.modules[__name__] = _import_service
