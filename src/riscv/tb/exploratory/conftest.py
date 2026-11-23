#------------------------------------------------------------------------------
# Module      : conftest
# Description : Put tb/exploratory on sys.path so the cocotb modules import.
# Author      : Claude Code (Anthropic)
# Date        : 2026-11-19
#------------------------------------------------------------------------------

import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
