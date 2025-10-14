"""
Data models cho vị trí và ô
"""

from typing import Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """Vị trí pixel"""
    x: float
    y: float
    
    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Cell:
    """Ô trên lưới"""
    x: int
    y: int
    
    def to_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)
    
    def __iter__(self):
        return iter((self.x, self.y))
    
    def is_valid(self, min_val: int = 1, max_val: int = 14) -> bool:
        """Kiểm tra ô có hợp lệ không"""
        return min_val <= self.x <= max_val and min_val <= self.y <= max_val
