"""Entry point used inside the AppImage."""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

from rawm_control.__main__ import main  # noqa: E402

sys.exit(main())
