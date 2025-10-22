"""
Advanced bombing strategy với timing và safety checks
"""

import logging
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)


class AdvancedBombingStrategy:
    """
    Chiến thuật đặt bom thông minh với:
    1. Tính toán timing chính xác
    2. Kiểm tra đường thoát TRƯỚC KHI đặt bom
    3. Ưu tiên targets có giá trị cao
    4. Tránh đặt bom tự sát
    """
    
    @staticmethod
    def find_best_bombing_position(
        current_position: Tuple[int, int],
        max_search_radius: int = 16,  # Tìm toàn bộ map 16x16
        blacklist: Optional[Dict[Tuple[int, int], float]] = None,
        current_time: float = 0.0
    ) -> Optional[Tuple[int, int]]:
        """
        Tìm vị trí đặt bom TỐT NHẤT với:
        - Có target (chest/bot) trong tầm nổ
        - CÓ ĐƯỜNG THOÁT AN TOÀN
        - Thời gian di chuyển + escape hợp lý
        - KHÔNG nằm trong blacklist
        
        Returns:
            Best position hoặc None
        """
        from ..game_state import game_state, get_bomber_explosion_range, pos_to_cell
        from .escape_planner import EscapePlanner
        from .bombing import BombingHelper
        
        my_uid = game_state.get("my_uid")
        if not my_uid:
            return None
        
        explosion_range = get_bomber_explosion_range(my_uid)
        
        # Tìm tất cả chests trong radius
        chests = BombingHelper.find_chests_in_range(current_position, max_search_radius)
        
        if not chests:
            logger.info(f"🔍 KHÔNG CÓ RƯƠNG trong tầm tìm kiếm (max_range={max_search_radius})")
            return None
        
        # Đánh giá từng vị trí có thể đặt bom
        candidates = []
        
        for chest in chests:
            # Tìm vị trí đặt bom để nổ chest này
            bomb_positions = AdvancedBombingStrategy._get_bomb_positions_for_target(
                chest, explosion_range
            )
            
            for bomb_pos in bomb_positions:
                # QUAN TRỌNG: Check blacklist trước
                if blacklist and bomb_pos in blacklist:
                    blacklist_time = blacklist[bomb_pos]
                    if current_time - blacklist_time < 5000:  # Blacklist 5s
                        continue
                
                # Kiểm tra vị trí có thể đi qua không
                from .navigation import NavigationHelper
                if not NavigationHelper.is_cell_passable(bomb_pos):
                    continue
                
                # QUAN TRỌNG 1: Kiểm tra có ĐƯỜNG ĐI đến vị trí này không
                if bomb_pos != current_position:
                    from ..game_state import astar_shortest_path
                    path_to_bomb = astar_shortest_path(current_position, bomb_pos, avoid_hazard=True, avoid_bots=False)
                    if not path_to_bomb or len(path_to_bomb) < 2:
                        # Vị trí không thể đến được, bỏ qua
                        continue
                
                # QUAN TRỌNG 2: Kiểm tra có đường thoát an toàn không
                if not EscapePlanner.is_safe_to_place_bomb(
                    bomb_pos, current_position, explosion_range
                ):
                    logger.warning(f"⚠️ BỎ QUA {bomb_pos}: không có đường thoát an toàn")
                    continue
                
                # Tính điểm cho vị trí này
                score = AdvancedBombingStrategy._calculate_bombing_score(
                    bomb_pos, chest, current_position, explosion_range
                )
                
                candidates.append((bomb_pos, score, chest))
        
        if not candidates:
            logger.warning("⚠️ KHÔNG CÓ VỊ TRÍ ĐẶT BOM AN TOÀN")
            return None
        
        # Chọn vị trí có điểm cao nhất
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_pos, best_score, target_chest = candidates[0]
        
        logger.info(
            f"✅ VỊ TRÍ ĐẶT BOM TỐT NHẤT: {best_pos} → {target_chest}, "
            f"score={best_score:.1f}"
        )
        
        return best_pos
    
    @staticmethod
    def _get_bomb_positions_for_target(
        target: Tuple[int, int],
        explosion_range: int
    ) -> List[Tuple[int, int]]:
        """Tìm các vị trí có thể đặt bom để nổ target"""
        from ..game_state import game_state
        from ..config import DIRECTIONS
        
        positions = []
        map_data = game_state.get("map", [])
        
        # Thử từng hướng từ target
        for direction, (dx, dy) in DIRECTIONS.items():
            for distance in range(0, explosion_range + 1):
                bomb_pos = (target[0] - dx * distance, target[1] - dy * distance)
                
                # Kiểm tra bounds
                if not (0 <= bomb_pos[0] <= 15 and 0 <= bomb_pos[1] <= 15):
                    break
                
                # Kiểm tra không có tường giữa bomb và target
                path_clear = True
                for check_dist in range(1, distance + 1):
                    check_pos = (target[0] - dx * check_dist, target[1] - dy * check_dist)
                    try:
                        # Convert to int for array indexing
                        check_y, check_x = int(check_pos[1]), int(check_pos[0])
                        if (check_y < len(map_data) and 
                            check_x < len(map_data[check_y])):
                            cell_value = map_data[check_y][check_x]
                            if cell_value == 'W' or cell_value == 1:
                                path_clear = False
                                break
                    except:
                        path_clear = False
                        break
                
                if path_clear:
                    positions.append(bomb_pos)
        
        return positions
    
    @staticmethod
    def _calculate_bombing_score(
        bomb_position: Tuple[int, int],
        target: Tuple[int, int],
        bot_position: Tuple[int, int],
        explosion_range: int
    ) -> float:
        """
        Tính điểm cho vị trí đặt bom
        Score cao = vị trí tốt
        """
        score = 100.0
        
        # 1. Khoảng cách đến target (gần target = tốt)
        distance_to_target = abs(bomb_position[0] - target[0]) + abs(bomb_position[1] - target[1])
        score -= distance_to_target * 5
        
        # 2. Khoảng cách đến bot (gần bot = tốt, dễ di chuyển tới)
        distance_to_bot = abs(bomb_position[0] - bot_position[0]) + abs(bomb_position[1] - bot_position[1])
        score -= distance_to_bot * 10
        
        # 3. Bonus nếu là vị trí hiện tại (không cần di chuyển)
        if bomb_position == bot_position:
            score += 50
        
        # 4. Số lượng targets trong tầm nổ
        num_chests_in_range = len(AdvancedBombingStrategy._count_targets_in_blast(
            bomb_position, explosion_range
        ))
        score += num_chests_in_range * 30
        
        # 5. Kiểm tra có bot khác gần đó (nguy hiểm)
        from ..game_state import game_state, pos_to_cell_bot
        my_uid = game_state.get("my_uid")
        for bomber in game_state.get("bombers", []):
            if bomber.get("uid") == my_uid or not bomber.get("isAlive", True):
                continue
            
            bomber_cell = pos_to_cell_bot(bomber.get("x", 0), bomber.get("y", 0))
            distance_to_enemy = abs(bomber_cell[0] - bomb_position[0]) + abs(bomber_cell[1] - bomb_position[1])
            
            if distance_to_enemy <= 3:
                score -= 30  # Giảm điểm nếu có bot khác gần
        
        return score
    
    @staticmethod
    def _count_targets_in_blast(
        bomb_position: Tuple[int, int],
        explosion_range: int
    ) -> List[Tuple[int, int]]:
        """Đếm số targets (chests) trong vùng nổ"""
        from ..game_state import game_state, pos_to_cell
        from ..config import DIRECTIONS
        
        targets = []
        map_data = game_state.get("map", [])
        chests = game_state.get("chests", [])
        
        # Kiểm tra từng hướng
        for direction, (dx, dy) in DIRECTIONS.items():
            for distance in range(1, explosion_range + 1):
                check_pos = (bomb_position[0] + dx * distance, bomb_position[1] + dy * distance)
                
                # Kiểm tra bounds
                if not (0 <= check_pos[0] <= 15 and 0 <= check_pos[1] <= 15):
                    break
                
                # Kiểm tra có chest không
                for chest in chests:
                    chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                    if chest_cell == check_pos:
                        targets.append(check_pos)
                
                # Dừng nếu gặp tường
                try:
                    # Convert to int for array indexing
                    check_y, check_x = int(check_pos[1]), int(check_pos[0])
                    if (check_y < len(map_data) and 
                        check_x < len(map_data[check_y])):
                        cell_value = map_data[check_y][check_x]
                        if cell_value == 'W' or cell_value == 1:
                            break
                except:
                    break
        
        return targets
    
    @staticmethod
    def should_place_bomb_now(
        current_position: Tuple[int, int],
        target_position: Tuple[int, int],
        can_place_bomb: bool
    ) -> bool:
        """
        Quyết định có nên đặt bom NGAY BÂY GIỜ không
        
        Chỉ đặt bom khi:
        1. Đã ở vị trí mục tiêu
        2. Có target trong tầm nổ
        3. CÓ ĐƯỜNG THOÁT AN TOÀN (QUAN TRỌNG NHẤT!)
        4. Cooldown đã hết
        """
        if not can_place_bomb:
            return False
        
        # Kiểm tra đã ở vị trí mục tiêu chưa
        if current_position != target_position:
            return False
        
        # Kiểm tra có target trong tầm nổ
        from ..game_state import game_state, get_bomber_explosion_range
        from .bombing import BombingHelper
        
        my_uid = game_state.get("my_uid")
        explosion_range = get_bomber_explosion_range(my_uid)
        
        if not BombingHelper.has_chest_in_bomb_range(current_position):
            logger.warning("⚠️ KHÔNG ĐẶT BOM: Không có rương trong tầm nổ")
            return False
        
        # QUAN TRỌNG: Kiểm tra đường thoát
        from .escape_planner import EscapePlanner
        if not EscapePlanner.is_safe_to_place_bomb(
            current_position, current_position, explosion_range
        ):
            logger.warning("⚠️ KHÔNG ĐẶT BOM: Không có đường thoát an toàn")
            return False
        
        logger.info("✅ AN TOÀN ĐẶT BOM: Có rương và có đường thoát")
        return True
