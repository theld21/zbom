"""
Survival strategy - Refactored version
Import từ survival_ai.py cũ để giữ backward compatibility
"""

# Import survival AI class từ file cũ
from ..survival_ai import SimpleSurvivalAI as LegacySurvivalAI, choose_next_action, reset_ai_state


class SurvivalStrategy(LegacySurvivalAI):
    """
    Survival strategy với cấu trúc tốt hơn
    Kế thừa từ SimpleSurvivalAI để giữ tất cả logic cũ
    """
    pass


# Global instance
survival_ai = SurvivalStrategy()


__all__ = ["SurvivalStrategy", "survival_ai", "choose_next_action", "reset_ai_state"]
