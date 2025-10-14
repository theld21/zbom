"""
Data models cho actions
"""

from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass


class ActionType(Enum):
    """Loại hành động"""
    MOVE = "move"
    BOMB = "bomb"
    IDLE = "idle"


@dataclass
class Action:
    """Hành động của bot"""
    type: ActionType
    orient: Optional[str] = None  # UP, DOWN, LEFT, RIGHT
    goal_cell: Optional[Tuple[int, int]] = None
    reason: Optional[str] = None
    
    def to_dict(self):
        """Convert to dictionary"""
        result = {"type": self.type.value}
        if self.orient:
            result["orient"] = self.orient
        if self.goal_cell:
            result["goal_cell"] = self.goal_cell
        if self.reason:
            result["reason"] = self.reason
        return result
