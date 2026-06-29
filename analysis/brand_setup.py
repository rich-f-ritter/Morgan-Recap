"""Wire up the Milestone brandkit on this (Linux) box: add it to sys.path and
substitute available fonts for the Windows brand faces (Bell MT / Calibri),
keeping the exact palette + layout spec intact."""
import sys, os
BK = os.path.join(os.path.dirname(__file__), "..", "_uploads", "milestone_brand", "milestone-brand", "scripts")
sys.path.insert(0, os.path.abspath(BK))

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm

# register the Linux serif/sans we'll substitute
for p in ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
    try:
        fm.fontManager.addfont(p)
    except Exception:
        pass

from brandkit import theme as T
T.use_theme()
# Bell MT -> Liberation Serif (elegant Times-like title face); Calibri -> Liberation Sans
T.SERIF = "Liberation Serif"
T.SANS = "Liberation Sans"
T.SANSL = "Liberation Sans"
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family": T.SANS})

# also fix the Excel helper's font names
try:
    from brandkit import xl as XL
    XL.SERIF = "Calibri"   # Excel keeps Calibri (Excel substitutes natively if absent)
    XL.SANS = "Calibri"
except Exception:
    pass
