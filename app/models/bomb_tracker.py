"""
Bomb Tracker - Quản lý bom và vùng nổ
"""

from typing import Dict, Set, Tuple, Optional
import time

class BombInfo:
    """Thông tin về 1 quả bom"""
    
    def __init__(
        self, 
        bomb_id: int,
        position: Tuple[int, int],  # Cell position (1-indexed)
        explosion_range: int,
        created_at: float,  # Timestamp (ms)
        lifetime: float = 5000.0,  # ms
        owner_uid: str = ""
    ):
        self.bomb_id = bomb_id
        self.position = position
        self.explosion_range = explosion_range
        self.created_at = created_at
        self.lifetime = lifetime
        self.owner_uid = owner_uid
        self.blast_zone: Set[Tuple[int, int]] = set()
        
    def will_explode_at(self) -> float:
        """Thời gian bom sẽ nổ (ms)"""
        return self.created_at + self.lifetime
    
    def time_until_explode(self, current_time: float) -> float:
        """Thời gian còn lại đến khi nổ (ms)"""
        return max(0, self.will_explode_at() - current_time)


class BombTracker:
    """
    Quản lý tất cả bom đang hoạt động và vùng nổ của chúng
    
    === SPEC BOM NỔ (theo z-bom-rules.txt) ===
    - Bom nổ sau 5 giây (5000ms) kể từ khi đặt
    - Nổ theo 4 hướng: UP, DOWN, LEFT, RIGHT (không chéo)
    - Tầm nổ = explosionRange (mặc định 2, có thể tăng bằng item R)
    - Dừng khi gặp tường (W) - KHÔNG nổ tường
    - Dừng TẠI rương (C) - NỔ rương nhưng không nổ phía sau
    - Nổ qua ô trống và bot
    """
    
    def __init__(self):
        self.bombs: Dict[int, BombInfo] = {}  # bomb_id -> BombInfo
        self._all_blast_zones: Set[Tuple[int, int]] = set()  # Union của tất cả blast zones
        
    def add_bomb(
        self, 
        bomb_id: int,
        position: Tuple[int, int],
        explosion_range: int,
        created_at: float,
        lifetime: float = 5000.0,
        owner_uid: str = ""
    ) -> None:
        """
        Thêm bom mới và tính blast zone
        
        Args:
            bomb_id: ID của bom
            position: Vị trí bom (cell, 1-indexed)
            explosion_range: Tầm nổ
            created_at: Thời gian đặt (ms)
            lifetime: Thời gian sống (ms)
            owner_uid: UID của người đặt
        """
        bomb = BombInfo(bomb_id, position, explosion_range, created_at, lifetime, owner_uid)
        
        # Tính blast zone theo spec
        bomb.blast_zone = self._calculate_blast_zone(position, explosion_range)
        
        # Lưu bomb
        self.bombs[bomb_id] = bomb
        
        # Update union blast zone
        self._rebuild_all_blast_zones()
        
    def remove_bomb(self, bomb_id: int) -> None:
        """Xóa bom (khi nổ)"""
        if bomb_id in self.bombs:
            del self.bombs[bomb_id]
            self._rebuild_all_blast_zones()
    
    def get_all_blast_zones(self) -> Set[Tuple[int, int]]:
        """Lấy tất cả ô nguy hiểm (union của blast zones)"""
        return self._all_blast_zones.copy()
    
    def is_cell_dangerous(self, cell: Tuple[int, int]) -> bool:
        """Check ô có nguy hiểm không"""
        return cell in self._all_blast_zones
    
    def get_bombs_near(self, cell: Tuple[int, int], radius: int = 3) -> list:
        """Lấy danh sách bom gần ô này"""
        nearby = []
        for bomb in self.bombs.values():
            distance = abs(bomb.position[0] - cell[0]) + abs(bomb.position[1] - cell[1])
            if distance <= radius:
                nearby.append(bomb)
        return nearby
    
    def clear(self) -> None:
        """Xóa toàn bộ bombs"""
        self.bombs.clear()
        self._all_blast_zones.clear()
    
    def _calculate_blast_zone(
        self, 
        bomb_position: Tuple[int, int], 
        explosion_range: int
    ) -> Set[Tuple[int, int]]:
        """
        Tính vùng nổ của bom theo SPEC
        
        === SPEC ===
        - Nổ theo 4 hướng (không chéo)
        - Dừng trước tường (W/x)
        - Dừng tại rương (r/C) - nổ rương nhưng không nổ phía sau
        """
        from ..game_state import game_state
        from ..config import DIRECTIONS
        
        blast_zone = set()
        blast_zone.add(bomb_position)
        
        map_data = game_state.get("map", [])
        if not map_data:
            return blast_zone
        
        # Tính theo 4 hướng
        for direction, (dx, dy) in DIRECTIONS.items():
            for distance in range(1, explosion_range + 1):
                nx = bomb_position[0] + dx * distance
                ny = bomb_position[1] + dy * distance
                
                # Check bounds (1-14)
                if not (1 <= nx <= 14 and 1 <= ny <= 14):
                    break
                
                # Add vào blast zone
                blast_zone.add((nx, ny))
                
                # Check obstacle
                try:
                    if ny < len(map_data) and nx < len(map_data[ny]):
                        cell_value = map_data[ny][nx]
                        
                        # Dừng nếu gặp tường
                        if cell_value in ['W', 'x', 1]:
                            break
                        
                        # Dừng sau khi nổ rương
                        if cell_value in ['r', 'C']:
                            # Đã add vào blast_zone, giờ dừng
                            break
                except:
                    break
        
        return blast_zone
    
    def _rebuild_all_blast_zones(self) -> None:
        """Rebuild union của tất cả blast zones"""
        self._all_blast_zones.clear()
        for bomb in self.bombs.values():
            self._all_blast_zones.update(bomb.blast_zone)


# Global bomb tracker instance
_bomb_tracker = BombTracker()


def get_bomb_tracker() -> BombTracker:
    """Lấy global bomb tracker instance"""
    return _bomb_tracker




