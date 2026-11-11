"""Double-click (or point a shortcut) to start battery-bar without a console window."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battery_bar.app import main  # noqa: E402

main()
