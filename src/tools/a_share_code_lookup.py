"""Local A-share company-name → code lookup."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


DEFAULT_CSV_PATH = Path("data/db/a_share_code_name.csv")


class AShareCodeLookup:
    def __init__(self, csv_path: Path | str = DEFAULT_CSV_PATH) -> None:
        df = pd.read_csv(csv_path, dtype={"code": str})
        df["name"] = df["name"].astype(str).str.replace(" ", "", regex=False)
        self._df = df
        self._path = Path(csv_path)

    def lookup(self, name: str = "", short_name: str = "") -> str:
        name = (name or "").strip().replace(" ", "")
        short_name = (short_name or "").strip().replace(" ", "")
        if not name and not short_name:
            return ""
        matches = self._df[
            self._df["name"].eq(name)
            | self._df["name"].eq(short_name)
        ]
        if len(matches) == 1:
            return str(matches.iloc[0]["code"])
        if len(matches) > 1:
            return ""
        starts = self._df[
            self._df["name"].str.startswith(name)
            | self._df["name"].str.startswith(short_name)
        ]
        if len(starts) == 1:
            return str(starts.iloc[0]["code"])
        return ""

    @property
    def source(self) -> Path:
        return self._path
