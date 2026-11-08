"""rawmctl entry point inside the Flatpak sandbox: no GTK import."""
import sys

sys.path.insert(0, "/app/share/rawm-control")

from rawm_control.cli import main  # noqa: E402

sys.exit(main())
