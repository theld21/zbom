"""
Base strategy class
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseStrategy(ABC):
    """Base class cho tất cả strategies"""
    
    @abstractmethod
    def choose_next_action(self) -> Optional[Dict[str, Any]]:
        """Chọn hành động tiếp theo"""
        pass
    
    @abstractmethod
    def reset_state(self):
        """Reset state của strategy"""
        pass
