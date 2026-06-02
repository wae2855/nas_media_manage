import sys
from media_importer.domains.import_flow import runner as _runner

sys.modules[__name__] = _runner
