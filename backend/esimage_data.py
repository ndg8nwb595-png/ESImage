"""``esimage-data`` 的免安装入口。

在 backend/ 目录直接运行：
    python esimage_data.py db upgrade
    python esimage_data.py seed
    python esimage_data.py verify --scope all

等价于 ``pip install -e .`` 后调用 ``esimage-data``。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.modules.data.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
