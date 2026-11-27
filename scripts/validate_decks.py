#!/usr/bin/env python
"""校验随应用提供的口语词书 JSON。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.decks import public_catalog

if __name__ == "__main__":
    try:
        books = public_catalog()
        if not books:
            raise ValueError("没有可校验的公开词书")
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    for key, book in books.items():
        print(key, len(book["units"]), sum(len(unit["cards"]) for unit in book["units"]))
