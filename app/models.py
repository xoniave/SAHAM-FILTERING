from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    average_entry: float = Field(gt=0)
    lots: int = Field(gt=0)
    style: Literal["SWING", "SUPER"]


class PortfolioUpdate(BaseModel):
    average_entry: float | None = Field(default=None, gt=0)
    lots: int | None = Field(default=None, gt=0)
    style: Literal["SWING", "SUPER"] | None = None
