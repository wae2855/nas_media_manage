import sys
from media_importer.domains.import_flow import confirm as _confirm

sys.modules[__name__] = _confirm
