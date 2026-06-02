import sys
from media_importer.features.import_flow import steps as _steps

sys.modules[__name__] = _steps
