import sys
from media_importer.domains.import_flow.steps import file as _file

sys.modules[__name__] = _file
