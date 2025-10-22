#!/usr/bin/env python3
"""
AI sinh tồn đơn giản - Chiến lược ưu tiên an toàn
"""

import time
import logging
from typing import List, Tuple, Optional, Dict, Any

from .config import DIRECTIONS, CELL_SIZE_PIXELS
from .game_state import (
    game_state, get_my_bomber, get_my_cell, get_bomber_explosion_range, 
    get_bomber_speed, get_bomber_bomb_count,
    get_tile_item, has_chest_at_tile, has_wall_at_tile, in_bounds,
    get_fast_state, bfs_shortest_path, astar_shortest_path, pos_to_cell, pos_to_cell_bot
)

logger = logging.getLogger(__name__)

class SimpleSurvivalAI:
    """AI sinh tồn thông minh với bộ nhớ và chiến lược"""
    
    def __init__(self):
        self.last_action_time = 0
        self.last_action = None
        self.action_count = 0
        self.last_bomb_time_ms = 0.0
        
        # Bộ nhớ khám phá - tránh quay lại nơi đã đi
        self.visited_cells = set()
        self.exploration_targets = []
        self.last_exploration_time = 0
        self.exploration_radius = 5
        
        # Chiến lược dài hạn
        self.strategic_goals = []
        self.current_goal = None
        self.goal_priority = {
            'survival': 100,
            'items': 80,
            'exploration': 60,
            'bombing': 40
        }
        
        # Tránh oscillation
        self.movement_history = []
        self.oscillation_threshold = 3
        
        # Logic bom liên tục
        self.my_bombs = set()  # Theo dõi bom của mình
        self.bomb_exploded_time = 0.0  # Thời gian bom nổ cuối cùng
        self.continuous_bombing = True  # Bật chế độ đặt bom liên tục
        
        # Blacklist các vị trí đã thử và thất bại
        self.failed_bomb_positions = {}  # {position: timestamp} - vị trí đã thử và thất bại
        self.blacklist_duration = 10000  # 10 giây blacklist
        
        # Plan hiện tại
        self.current_plan = None
        
        # Flag thoát hiểm
        self.must_escape_bomb = False  # BẮT BUỘC thoát sau khi đặt bom
        
        # Theo dõi vị trí để phát hiện hồi sinh
        self._last_position = None
    
    def reset_state(self):
        """Reset AI state về trạng thái ban đầu"""
        self.last_action_time = 0
        self.last_action = None
        self.action_count = 0
        self.last_bomb_time_ms = 0.0
        self.visited_cells.clear()
        self.exploration_targets.clear()
        self.last_exploration_time = 0
        self.strategic_goals.clear()
        self.current_goal = None
        self.movement_history.clear()
        self.my_bombs.clear()
        self.bomb_exploded_time = 0.0
        self.failed_bomb_positions.clear()
        self.current_plan = None
        self.must_escape_bomb = False
        
        # Reset oscillation detector nếu có
        if hasattr(self, '_oscillation_detector'):
            self._oscillation_detector.clear()
        
        # Reset vị trí theo dõi
        self._last_position = None
        
        logger.info(f"🔄 AI RESET: Đã reset toàn bộ trạng thái AI")
        
    def _get_move_time_ms(self, my_uid: str) -> float:
        """Tính thời gian di chuyển 1 bước (ms) dựa trên tốc độ"""
        speed = get_bomber_speed(my_uid)
        # Tốc độ 1 = 1px/bước, tốc độ 2 = 2px/bước, tốc độ 3 = 3px/bước
        # Thời gian di chuyển = 1000ms / tốc độ
        return 1000.0 / speed
        
    def _update_visited_cells(self, cell: Tuple[int, int]):
        """Cập nhật bộ nhớ các ô đã thăm"""
        self.visited_cells.add(cell)
        # Giữ tối đa 50 ô gần nhất
        if len(self.visited_cells) > 50:
            # Xóa các ô cũ nhất
            old_cells = list(self.visited_cells)[:-50]
            for old_cell in old_cells:
                self.visited_cells.discard(old_cell)
    
    def _is_oscillating(self) -> bool:
        """Kiểm tra xem có đang oscillation không"""
        if len(self.movement_history) < self.oscillation_threshold * 2:
            return False
            
        # Kiểm tra pattern A-B-A-B
        recent = self.movement_history[-self.oscillation_threshold * 2:]
        for i in range(0, len(recent) - 1, 2):
            if i + 1 < len(recent) and recent[i] == recent[i + 1]:
                return False
        return True
    
    def _get_exploration_targets(self, current_cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm các mục tiêu khám phá chưa được thăm"""
        targets = []
        for dx in range(-self.exploration_radius, self.exploration_radius + 1):
            for dy in range(-self.exploration_radius, self.exploration_radius + 1):
                if dx == 0 and dy == 0:
                    continue
                target = (current_cell[0] + dx, current_cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and 
                    target not in self.visited_cells and 
                    self._is_cell_passable(target)):
                    targets.append(target)
        return targets
    
    def _get_strategic_goal(self, current_cell: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Lập kế hoạch chiến lược thông minh - TRÁNH VÒNG LẶP"""
        # Kiểm tra vị trí hiện tại có hợp lệ không
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            logger.warning(f"🚫 VỊ TRÍ KHÔNG HỢP LỆ: {current_cell} - Tìm vị trí an toàn gần nhất")
            # Tìm vị trí an toàn gần nhất trong map
            for radius in range(1, 8):
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        target = (current_cell[0] + dx, current_cell[1] + dy)
                        if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and 
                            self._is_cell_passable(target)):
                            logger.info(f"🎯 TÌM THẤY VỊ TRÍ AN TOÀN: {target}")
                            return target
            return None
        
        # 1. Ưu tiên sinh tồn - tìm nơi an toàn (ưu tiên ô chưa thăm)
        # Convert float to int for safe areas calculation
        current_cell_int = (int(current_cell[0]), int(current_cell[1]))
        safe_goals = self._find_safe_areas(current_cell_int)
        if safe_goals:
            # Ưu tiên ô chưa thăm
            unexplored_safe = [goal for goal in safe_goals if goal not in self.visited_cells]
            if unexplored_safe:
                logger.info(f"🎯 CHỌN VÙNG AN TOÀN CHƯA THĂM: {unexplored_safe[0]}")
                return unexplored_safe[0]
            else:
                logger.info(f"🎯 CHỌN VÙNG AN TOÀN: {safe_goals[0]}")
                return safe_goals[0]
            
        # 2. Tìm vật phẩm quan trọng
        item_goals = self._find_important_items(current_cell)
        if item_goals:
            logger.info(f"🎯 CHỌN ITEM QUAN TRỌNG: {item_goals[0]}")
            return item_goals[0]
            
        # 3. Khám phá khu vực mới (ưu tiên ô xa)
        exploration_goals = self._get_exploration_targets(current_cell)
        if exploration_goals:
            logger.info(f"🎯 CHỌN KHÁM PHÁ: {exploration_goals[0]}")
            return exploration_goals[0]
        
        # 4. Fallback: Tìm ô an toàn bất kỳ (tránh vòng lặp)
        safe_goal = self._find_safe_goal(current_cell, time.time() * 1000)
        if safe_goal:
            logger.info(f"🎯 FALLBACK AN TOÀN: {safe_goal}")
            return safe_goal
            
        return None
    
    def _execute_long_term_plan(self, plan: Dict, current_cell: Tuple[int, int], current_time: float, can_place_bomb: bool) -> Optional[Dict[str, Any]]:
        """Thực hiện plan dài hạn"""
        plan_type = plan.get("type")
        plan_goal = plan.get("goal_cell")
        
        if plan_type == "collect_item":
            logger.info(f"💎 PLAN DÀI HẠN - NHẶT VẬT PHẨM: đến {plan_goal}")
            self.last_action_time = current_time
            self._update_last_direction(current_cell, plan_goal)
            return {"type": "move", "goal_cell": plan_goal}
        elif plan_type == "bomb_chest":
            # So sánh int với float: (14, 4) == (14.0, 4.0)
            if (int(plan_goal[0]) == int(current_cell[0]) and 
                int(plan_goal[1]) == int(current_cell[1])):
                if can_place_bomb and self._should_place_bomb_for_chest(current_cell, current_time, can_place_bomb):
                    # Hiển thị plan chi tiết
                    bomb_pos = plan_goal
                    escape_pos = plan.get("escape_cell", "chưa tính")
                    escape_path = plan.get("escape_path", [])
                    
                    logger.info(f"💣 PLAN DÀI HẠN - ĐẶT BOM TẠI VỊ TRÍ HIỆN TẠI")
                    logger.info(f"🎯 PLAN CHI TIẾT: ĐẾN {bomb_pos} → ĐẶT BOM → THOÁT ĐẾN {escape_pos}")
                    if escape_path:
                        logger.info(f"🛡️ ĐƯỜNG THOÁT: {escape_path}")
                    
                    self.last_action_time = current_time
                    self.last_bomb_time_ms = current_time
                    self.must_escape_bomb = True  # BẮT BUỘC thoát lần loop tiếp
                    
                    # BLACKLIST VỊ TRÍ ĐÃ ĐẶT BOM trong 8s để tránh quay lại ngay
                    self.failed_bomb_positions[current_cell] = current_time
                    logger.warning(f"⚡ SET FLAG: must_escape_bomb = True + BLACKLIST {current_cell} trong 8s")
                    
                    # Clear plan sau khi đặt bom
                    self.current_plan = None
                    return {"type": "bomb"}
                else:
                    logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM tại {current_cell}: blacklist 5s")
                    # BLACKLIST vị trí này để tránh lặp lại
                    self.failed_bomb_positions[current_cell] = current_time
                    self.current_plan = None
                    # Tìm mục tiêu khác ngay
                    fallback = self._get_fallback_action(current_cell, current_time)
                    if fallback:
                        logger.info(f"🔄 CHUYỂN SANG MỤC TIÊU KHÁC")
                        return fallback
                    return None
            else:
                # Hiển thị plan chi tiết khi di chuyển
                bomb_pos = plan_goal
                escape_pos = plan.get("escape_cell", "chưa tính")
                escape_path = plan.get("escape_path", [])
                
                logger.info(f"💣 PLAN DÀI HẠN - ĐẾN VỊ TRÍ ĐẶT BOM: {plan_goal}")
                logger.info(f"🎯 PLAN CHI TIẾT: ĐẾN {bomb_pos} → ĐẶT BOM → THOÁT ĐẾN {escape_pos}")
                if escape_path:
                    logger.info(f"🛡️ ĐƯỜNG THOÁT: {escape_path}")
                
                self.last_action_time = current_time
                self._update_last_direction(current_cell, plan_goal)
                return {"type": "move", "goal_cell": plan_goal}
        return None
    
    def _calculate_escape_plan(self, bomb_position: Tuple[int, int], current_cell: Tuple[int, int]) -> Dict[str, Any]:
        """Tính escape plan cho bomb position"""
        try:
            from .helpers.escape_planner import EscapePlanner
            
            # Tính escape path từ bomb position
            escape_result = EscapePlanner.find_escape_path_from_bomb(
                bomb_position=bomb_position,
                bot_position=current_cell,
                explosion_range=2,  # Default explosion range
                bomb_lifetime=5000.0
            )
            
            if escape_result:
                escape_path, escape_time = escape_result
                return {
                    "escape_cell": escape_path[-1] if escape_path else None,
                    "escape_path": escape_path,
                    "escape_time": escape_time
                }
            else:
                return {
                    "escape_cell": None,
                    "escape_path": [],
                    "escape_time": 0
                }
        except Exception as e:
            logger.warning(f"⚠️ LỖI TÍNH ESCAPE PLAN: {e}")
            return {
                "escape_cell": None,
                "escape_path": [],
                "escape_time": 0
            }
    
    def _get_fallback_action(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Xử lý tất cả fallback strategies"""
        # Kiểm tra vị trí hiện tại có hợp lệ không
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            logger.warning(f"🚫 FALLBACK: Vị trí không hợp lệ {current_cell}")
            return None
        
        # 1. Chiến lược dài hạn
        strategic_goal = self._get_strategic_goal(current_cell)
        if strategic_goal and strategic_goal != current_cell and strategic_goal not in self.movement_history[-3:]:
            # Kiểm tra có thể di chuyển đến mục tiêu không
            if self._can_reach_goal(current_cell, strategic_goal):
                logger.info(f"🎯 CHIẾN LƯỢC: đến {strategic_goal}")
                self.last_action_time = current_time
                self._update_last_direction(current_cell, strategic_goal)
                return {"type": "move", "goal_cell": strategic_goal}
            else:
                logger.warning(f"🚫 KHÔNG THỂ ĐẾN MỤC TIÊU: {strategic_goal} - Tìm mục tiêu khác")
        
        # 2. Di chuyển an toàn
        safe_goal = self._find_safe_goal(current_cell, current_time)
        if safe_goal and safe_goal != current_cell and safe_goal not in self.movement_history[-2:]:
            if self._can_reach_goal(current_cell, safe_goal):
                logger.info(f"🎯 AN TOÀN: đến {safe_goal}")
                self.last_action_time = current_time
                self._update_last_direction(current_cell, safe_goal)
                return {"type": "move", "goal_cell": safe_goal}
            else:
                logger.warning(f"🚫 KHÔNG THỂ ĐẾN AN TOÀN: {safe_goal}")
        
        # 3. Khám phá khu vực mới
        exploration_goals = self._get_exploration_targets(current_cell)
        if exploration_goals:
            best_goal = max(exploration_goals, key=lambda g: abs(g[0] - current_cell[0]) + abs(g[1] - current_cell[1]))
            if best_goal not in self.movement_history[-2:] and self._can_reach_goal(current_cell, best_goal):
                logger.info(f"🔍 KHÁM PHÁ: đến {best_goal}")
                self.last_action_time = current_time
                self._update_last_direction(current_cell, best_goal)
                return {"type": "move", "goal_cell": best_goal}
            else:
                logger.warning(f"🚫 KHÔNG THỂ ĐẾN KHÁM PHÁ: {best_goal}")
        
        # 4. Xử lý oscillation
        if self._is_oscillating():
            logger.warning(f"🚫 PHÁT HIỆN OSCILLATION: thay đổi chiến lược")
            self.movement_history = []
            for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
                dx, dy = DIRECTIONS[direction]
                next_cell = (current_cell[0] + dx, current_cell[1] + dy)
                if self._is_cell_passable(next_cell):
                    logger.info(f"🔄 THAY ĐỔI CHIẾN LƯỢC: {direction} đến {next_cell}")
                    self._update_last_direction(current_cell, next_cell)
                    self.last_action_time = current_time
                    return {"type": "move", "goal_cell": next_cell}
        
        # 5. Reset plan nếu không thể di chuyển
        logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Reset plan và tìm hướng mới")
        self.current_plan = None
        self.movement_history = []
        self.visited_cells = set()
        
        # 6. Fallback cuối cùng
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if next_cell not in self.movement_history[-2:]:
                logger.info(f"🎲 FALLBACK: {direction} đến {next_cell}")
                self._update_last_direction(current_cell, next_cell)
                self.last_action_time = current_time
                return {"type": "move", "goal_cell": next_cell}
        
        # 7. Reset history và di chuyển bất kỳ
        logger.warning(f"🚨 RESET HISTORY: Không thể tránh vòng lặp")
        self.movement_history = []
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if self._is_cell_passable(next_cell):
                logger.info(f"🎲 RESET FALLBACK: {direction} đến {next_cell}")
                self._update_last_direction(current_cell, next_cell)
                self.last_action_time = current_time
                return {"type": "move", "goal_cell": next_cell}
            
        return None
    
    def _can_reach_goal(self, current_cell: Tuple[int, int], goal_cell: Tuple[int, int]) -> bool:
        """Kiểm tra có thể di chuyển đến mục tiêu không"""
        try:
            from .game_state import bfs_shortest_path
            path = bfs_shortest_path(current_cell, goal_cell)
            return path is not None and len(path) > 1
        except Exception:
            return (abs(goal_cell[0] - current_cell[0]) + abs(goal_cell[1] - current_cell[1])) <= 3
        
    def _find_safe_areas(self, current_cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm các khu vực an toàn"""
        safe_areas = []
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx == 0 and dy == 0:
                    continue
                target = (current_cell[0] + dx, current_cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and 
                    self._is_cell_passable(target) and 
                    not self._is_in_danger(target, time.time() * 1000)):
                    safe_areas.append(target)
        return safe_areas
    
    def _find_important_items(self, current_cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm các vật phẩm quan trọng"""
        items = []
        try:
            item_tile_map = game_state.get("item_tile_map", {})
            for (x, y), item_type in item_tile_map.items():
                if (0 <= x <= 15 and 0 <= y <= 15 and 
                    item_type in ["SPEED", "EXPLOSION_RANGE", "BOMB_COUNT"]):
                    distance = abs(x - current_cell[0]) + abs(y - current_cell[1])
                    if distance <= 5:
                        items.append((x, y))
        except Exception:
            pass
        return items
        
    def choose_next_action(self) -> Optional[Dict[str, Any]]:
        """Hàm quyết định chính - Ưu tiên sinh tồn với plan dài hạn"""
        # Kiểm tra trạng thái game
        if not game_state.get("game_started", False):
            return None
            
        # Kiểm tra map có tồn tại không (tránh lỗi sau khi hồi sinh)
        if not game_state.get("map") or len(game_state.get("map", [])) == 0:
            logger.warning(f"🚫 AI TẠM DỪNG: Map chưa sẵn sàng sau khi hồi sinh")
            return None
            
        me = get_my_bomber()
        if not me:
            return None
            
        if not me.get("movable", True):
            return None
            
        current_cell = get_my_cell()
        if not current_cell:
            return None
        
        # Kiểm tra vị trí hiện tại có hợp lệ không
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            logger.warning(f"🚫 VỊ TRÍ BOT KHÔNG HỢP LỆ: {current_cell} - Bỏ qua AI")
            return None
        
        # Cập nhật bộ nhớ khám phá
        self._update_visited_cells(current_cell)
        
        # Cập nhật theo dõi bom của mình
        self._update_my_bombs()
        
        # Reset plan nếu vị trí thay đổi đột ngột (hồi sinh)
        if hasattr(self, '_last_position'):
            if self._last_position and self._last_position != current_cell:
                distance = abs(current_cell[0] - self._last_position[0]) + abs(current_cell[1] - self._last_position[1])
                if distance > 3:  # Di chuyển xa hơn 3 ô = có thể hồi sinh
                    logger.info(f"🔄 VỊ TRÍ THAY ĐỔI: từ {self._last_position} đến {current_cell}, reset plan")
                    self.current_plan = None
                    self.movement_history.clear()
                    self.visited_cells.clear()
        self._last_position = current_cell
        
        # Lấy thông tin hiện tại
        current_time = time.time() * 1000  # ms
        my_uid = game_state.get("my_uid")
        can_place_bomb = get_bomber_bomb_count(my_uid) > 0
        
        # Tránh spam commands
        move_time = self._get_move_time_ms(my_uid)
        if current_time - self.last_action_time < move_time:
            return None
        
        # 0. ƯU TIÊN TUYỆT ĐỐI - THOÁT SAU KHI ĐẶT BOM
        if self.must_escape_bomb:
            logger.warning(f"🏃 BẮT BUỘC THOÁT: vừa đặt bom, phải chạy ngay!")
            self.must_escape_bomb = False
            escape_move = self._get_escape_move(current_cell, current_time)
            if escape_move:
                self.last_action_time = current_time
                return escape_move
            # Nếu không tìm được đường thoát, cố gắng di chuyển bất kỳ hướng nào
            for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
                dx, dy = DIRECTIONS[direction]
                next_cell = (current_cell[0] + dx, current_cell[1] + dy)
                if self._is_cell_passable(next_cell):
                    logger.warning(f"🏃 THOÁT KHẨN CẤP: {direction}")
                    self.last_action_time = current_time
                    return {"type": "move", "goal_cell": next_cell}
            
            # Nếu không thể thoát, clear plan để tạo plan mới
            logger.warning(f"🚫 KHÔNG THỂ THOÁT: Clear plan và tạo plan mới")
            self.current_plan = None
        
        # 1. KIỂM TRA AN TOÀN TUYỆT ĐỐI - Chạy khỏi bom
        in_danger = self._is_in_danger(current_cell, current_time)
        if in_danger:
            safe_goal = self._find_safe_goal(current_cell, current_time)
            if safe_goal:
                logger.warning(f"🚨 THOÁT HIỂM: đến {safe_goal}")
                self.last_action_time = current_time
                return {"type": "move", "goal_cell": safe_goal}
            logger.warning(f"🚨 THOÁT HIỂM: Không tìm thấy nơi an toàn!")
            return None
        
        # 1.5. LẬP PLAN DÀI HẠN - Mục tiêu rõ ràng
        # CHỈ tạo plan mới khi chưa có plan hoặc plan đã hoàn thành
        if not self.current_plan:
            long_term_plan = self._create_long_term_plan(current_cell, current_time)
            if long_term_plan:
                self.current_plan = long_term_plan
                return self._execute_long_term_plan(long_term_plan, current_cell, current_time, can_place_bomb)
        else:
            # Đang có plan cũ - tiếp tục thực hiện
            logger.debug(f"🔄 TIẾP TỤC PLAN CŨ: {self.current_plan.get('type')} → {self.current_plan.get('goal_cell')}")
            return self._execute_long_term_plan(self.current_plan, current_cell, current_time, can_place_bomb)
        
        # 1.6. ƯU TIÊN ĐẶT BOM LIÊN TỤC - Sau khi bom nổ
        if self._should_continue_bombing(current_cell, current_time, can_place_bomb):
            logger.info(f"💣 ĐẶT BOM LIÊN TỤC: tiếp tục sau khi bom nổ")
            self.last_action_time = current_time
            self.last_bomb_time_ms = current_time
            self.must_escape_bomb = True  # BẮT BUỘC thoát lần loop tiếp
            logger.warning(f"⚡ SET FLAG: must_escape_bomb = True (bomb liên tục)")
            return {"type": "bomb"}
        
        # 1.6.5. ƯU TIÊN THOÁT KHỎI VÙNG NGUY HIỂM SAU KHI ĐẶT BOM
        if self._should_escape_after_bomb(current_cell, current_time):
            logger.info(f"🏃 THOÁT KHỎI VÙNG NGUY HIỂM: sau khi đặt bom")
            escape_move = self._get_escape_move(current_cell, current_time)
            if escape_move:
                self.last_action_time = current_time
                return escape_move
        
        # 1.7. ƯU TIÊN DI CHUYỂN THÔNG MINH KHI GẦN BOT KHÁC
        if self._has_enemies_nearby(current_cell, radius=3):  # Tăng radius để phát hiện sớm hơn
            logger.info(f"🤖 GẦN BOT KHÁC: ưu tiên di chuyển thông minh")
            smart_move = self._get_smart_move_near_enemy(current_cell, current_time)
            if smart_move:
                self.last_action_time = current_time
                return smart_move
        
        # 1.8. ƯU TIÊN TRÁNH BOT KHÁC NGAY CẢ KHI KHÔNG GẦN
        if self._should_avoid_enemies(current_cell):
            logger.info(f"🤖 TRÁNH BOT KHÁC: ưu tiên di chuyển xa khỏi bot khác")
            avoid_move = self._get_avoid_enemy_move(current_cell, current_time)
            if avoid_move:
                self.last_action_time = current_time
                return avoid_move
            
        # 4. BỎ QUA kiểm tra đứng im để bot luôn di chuyển
        # should_idle = self._should_idle(current_cell, current_time)
        # if should_idle:
        #     idle_time = current_time - self.last_action_time
        #     if idle_time > 2000:  # 2 giây
        #         logger.info(f"🚨 ĐÃ ĐỨNG IM QUÁ LÂU: {idle_time:.0f}ms, tìm cách thoát")
        #         for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
        #             dx, dy = DIRECTIONS[direction]
        #             next_cell = (current_cell[0] + dx, current_cell[1] + dy)
        #             if self._is_cell_passable(next_cell):
        #                 logger.info(f"🚨 THOÁT KẸT: di chuyển {direction} đến {next_cell}")
        #                 self._update_last_direction(current_cell, next_cell)
        #                 self.last_action_time = current_time
        #                 return {"type": "move", "goal_cell": next_cell}
        #         logger.info(f"🚨 KHÔNG THỂ THOÁT: tất cả hướng đều bị chặn")
        #     else:
        #         logger.info(f"🚫 QUYẾT ĐỊNH ĐỨNG IM: không có hành động nào (đã đứng im {idle_time:.0f}ms)")
        #     return None
            
        # 5. FALLBACK STRATEGIES
        fallback_action = self._get_fallback_action(current_cell, current_time)
        if fallback_action:
            # Clear plan khi dùng fallback
            self.current_plan = None
        return fallback_action
        
    def _update_last_direction(self, from_cell: Tuple[int, int], to_cell: Tuple[int, int]) -> None:
        """Cập nhật hướng di chuyển cuối cùng để tránh oscillation"""
        # Xử lý float: (14.0, 4.0) -> (14, 4)
        from_cell_int = (int(from_cell[0]), int(from_cell[1]))
        to_cell_int = (int(to_cell[0]), int(to_cell[1]))
        
        dx = to_cell_int[0] - from_cell_int[0]
        dy = to_cell_int[1] - from_cell_int[1]
        
        if dx > 0:
            direction = "RIGHT"
        elif dx < 0:
            direction = "LEFT"
        elif dy > 0:
            direction = "DOWN"
        elif dy < 0:
            direction = "UP"
        else:
            direction = None
            
        if direction:
            self._last_direction = direction
            # Cập nhật movement history để phát hiện oscillation
            self.movement_history.append(direction)
            # Giữ tối đa 10 hướng gần nhất
            if len(self.movement_history) > 10:
                self.movement_history = self.movement_history[-10:]
        
    def _has_enemies_nearby(self, cell: Tuple[int, int], radius: int = 2) -> bool:
        """Kiểm tra có đối thủ gần đó không (giảm radius để ít nhạy cảm hơn)"""
        my_uid = game_state.get("my_uid")
        
        for bomber in game_state.get("bombers", []):
            if bomber.get("uid") == my_uid:
                continue
                
            if not bomber.get("isAlive", True):
                continue
                
            bomber_x, bomber_y = bomber.get("x", 0), bomber.get("y", 0)
            # Đối thủ cũng là bot 35x35: dùng phân ô theo bbox để khớp va chạm/định vị
            from .game_state import pos_to_cell_bot
            bomber_cell = pos_to_cell_bot(bomber_x, bomber_y)
            
            distance = abs(bomber_cell[0] - cell[0]) + abs(bomber_cell[1] - cell[1])
            if distance <= radius:
                logger.info(f"🔍 ĐỐI THỦ GẦN: {bomber.get('name')} tại {bomber_cell}, distance={distance}")
                return True
                
        return False
        
    def _get_smart_move_near_enemy(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi thông minh khi gần bot khác - ưu tiên di chuyển tối ưu"""
        # Tìm vị trí tốt nhất để di chuyển (xa bot khác, gần item/chest, an toàn)
        best_move = None
        best_score = -1
        
        # Kiểm tra các hướng di chuyển có thể
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            
            # Kiểm tra ô có thể đi được không
            if not self._is_cell_passable(next_cell):
                continue
                
            # Tính điểm cho hướng này
            score = self._calculate_move_score(current_cell, next_cell, current_time)
            
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🤖 DI CHUYỂN THÔNG MINH: từ {current_cell} đến {best_move} (score={best_score})")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        
        return None
    
    def _calculate_move_score(self, current_cell: Tuple[int, int], next_cell: Tuple[int, int], current_time: float) -> float:
        """Tính điểm cho nước đi - cao hơn = tốt hơn"""
        score = 0.0
        
        # 1. Tránh bot khác (ưu tiên cao nhất)
        if not self._has_enemies_nearby(next_cell, radius=2):
            score += 100.0  # Tăng điểm để ưu tiên cao hơn
        
        # 1.5. Ưu tiên di chuyển xa khỏi bot khác
        distance_from_enemies = self._get_distance_from_nearest_enemy(next_cell)
        if distance_from_enemies > 0:
            score += distance_from_enemies * 25.0  # Tăng điểm để ưu tiên xa bot khác
        
        # 2. Tránh nguy hiểm
        if not self._is_in_danger(next_cell, current_time):
            score += 30.0  # Quan trọng - tránh bom/lửa
        
        # 3. Hướng về item/chest gần đó
        nearby_items = self._get_nearby_items(next_cell, radius=3)
        if nearby_items:
            score += len(nearby_items) * 10.0  # Mỗi item/chest gần = +10 điểm
        
        # 4. Hướng về vùng trống (ít tường)
        open_space = self._count_open_spaces(next_cell, radius=2)
        score += open_space * 5.0  # Mỗi ô trống gần = +5 điểm
        
        # 4.5. Ưu tiên hướng có nhiều không gian mở (tránh bị kẹt)
        future_open_space = self._count_open_spaces(next_cell, radius=3)
        score += future_open_space * 3.0  # Mỗi ô trống trong tương lai = +3 điểm
        
        # 5. Tránh di chuyển lặp lại (giảm điểm nếu đã đi qua)
        if next_cell in self.visited_cells:
            score -= 20.0  # Trừ điểm nếu đã đi qua
        
        # 7. Tránh vòng lặp lên xuống (giảm điểm nếu di chuyển theo hướng ngược lại)
        if hasattr(self, '_last_direction') and self._last_direction:
            last_dx, last_dy = DIRECTIONS.get(self._last_direction, (0, 0))
            current_dx, current_dy = next_cell[0] - current_cell[0], next_cell[1] - current_cell[1]
            
            # Nếu di chuyển ngược lại hướng vừa đi
            if (current_dx == -last_dx and current_dy == -last_dy) and (current_dx != 0 or current_dy != 0):
                score -= 30.0  # Trừ điểm mạnh nếu di chuyển ngược lại
                logger.debug(f"🔄 TRÁNH VÒNG LẶP: di chuyển ngược lại hướng {self._last_direction}")
        
        # 6. Ưu tiên di chuyển xa khỏi vị trí hiện tại
        distance_from_current = abs(next_cell[0] - current_cell[0]) + abs(next_cell[1] - current_cell[1])
        if distance_from_current > 0:
            score += 5.0  # Thêm điểm nếu di chuyển thực sự
        
        return score
    
    def _get_nearby_items(self, cell: Tuple[int, int], radius: int = 3) -> List[Tuple[int, int]]:
        """Tìm item/chest gần vị trí"""
        items = []
        try:
            # Tìm items
            item_tile_map = game_state.get("item_tile_map", {})
            for (x, y), item_type in item_tile_map.items():
                distance = abs(x - cell[0]) + abs(y - cell[1])
                if distance <= radius:
                    items.append((x, y))
            
            # Tìm chests
            chest_tile_map = game_state.get("chest_tile_map", {})
            for (x, y) in chest_tile_map.keys():
                distance = abs(x - cell[0]) + abs(y - cell[1])
                if distance <= radius:
                    items.append((x, y))
        except Exception:
            pass
        
        return items
    
    def _count_open_spaces(self, cell: Tuple[int, int], radius: int = 2) -> int:
        """Đếm số ô trống xung quanh"""
        count = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                check_cell = (cell[0] + dx, cell[1] + dy)
                if self._is_cell_passable(check_cell):
                    count += 1
        return count
    
    def _get_distance_from_nearest_enemy(self, cell: Tuple[int, int]) -> int:
        """Tính khoảng cách đến bot khác gần nhất"""
        my_uid = game_state.get("my_uid")
        min_distance = 999
        
        for bomber in game_state.get("bombers", []):
            if bomber.get("uid") == my_uid:
                continue
            if not bomber.get("isAlive", True):
                continue
                
            bomber_x, bomber_y = bomber.get("x", 0), bomber.get("y", 0)
            bomber_cell = pos_to_cell_bot(bomber_x, bomber_y)
            distance = abs(bomber_cell[0] - cell[0]) + abs(bomber_cell[1] - cell[1])
            min_distance = min(min_distance, distance)
        
        return min_distance if min_distance < 999 else 0
    
    def _should_avoid_enemies(self, cell: Tuple[int, int]) -> bool:
        """Kiểm tra có nên tránh bot khác không (kể cả khi không gần)"""
        my_uid = game_state.get("my_uid")
        bombers = game_state.get("bombers", [])
        
        for bomber in bombers:
            if bomber.get("uid") == my_uid:
                continue
            if not bomber.get("isAlive", True):
                continue
                
            bomber_x, bomber_y = bomber.get("x", 0), bomber.get("y", 0)
            bomber_cell = pos_to_cell_bot(bomber_x, bomber_y)
            distance = abs(bomber_cell[0] - cell[0]) + abs(bomber_cell[1] - cell[1])
            
            # Nếu bot khác có explosion range cao và gần đó
            explosion_range = bomber.get("explosionRange", 2)
            if explosion_range >= 5 and distance <= 6:  # Bot mạnh và gần
                logger.info(f"🤖 TRÁNH BOT MẠNH: {bomber.get('name')} range={explosion_range} distance={distance}")
                return True
                
            # Nếu bot khác có nhiều bom và gần đó
            bomb_count = bomber.get("bombCount", 1)
            if bomb_count >= 3 and distance <= 5:  # Bot có nhiều bom và gần
                logger.info(f"🤖 TRÁNH BOT NHIỀU BOM: {bomber.get('name')} bombs={bomb_count} distance={distance}")
                return True
        
        return False
    
    def _get_avoid_enemy_move(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi để tránh bot khác"""
        best_move = None
        best_score = -1
        
        # Tìm hướng di chuyển xa khỏi bot khác nhất
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            
            if not self._is_cell_passable(next_cell):
                continue
                
            # Tính điểm dựa trên khoảng cách đến bot khác
            distance_from_enemies = self._get_distance_from_nearest_enemy(next_cell)
            score = distance_from_enemies * 50.0  # Ưu tiên cao để xa bot khác
            
            # Tránh nguy hiểm
            if not self._is_in_danger(next_cell, current_time):
                score += 30.0
            
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🤖 TRÁNH BOT KHÁC: từ {current_cell} đến {best_move} (score={best_score})")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        
        return None
    
    def _should_escape_after_bomb(self, cell: Tuple[int, int], current_time: float) -> bool:
        """
        Kiểm tra có cần thoát khỏi vùng nguy hiểm sau khi đặt bom không
        CÁCH MỚI: Kiểm tra ngay sau khi đặt bom, không đợi đến khi nguy hiểm
        """
        # QUAN TRỌNG: Kiểm tra NGAY LẬP TỨC sau khi đặt bom (trong vòng 500ms)
        time_since_bomb = current_time - self.last_bomb_time_ms
        if time_since_bomb <= 500:  # 500ms = ngay sau khi đặt bom
            logger.info(f"🏃 CẦN THOÁT NGAY: vừa đặt bom {time_since_bomb:.0f}ms trước")
            return True
        
        # Kiểm tra nếu vừa đặt bom gần đây (trong vòng 4 giây)
        if time_since_bomb > 4000:  # 4 giây
            return False
            
        # Kiểm tra nếu đang ở vùng nguy hiểm
        if self._is_in_danger(cell, current_time):
            logger.info(f"🏃 CẦN THOÁT: đang ở vùng nguy hiểm sau khi đặt bom")
            return True
            
        # Kiểm tra nếu có bom gần đó sắp nổ
        try:
            from .game_state import game_state
            bombs = game_state.get("bombs", [])
            for bomb in bombs:
                bomb_x, bomb_y = bomb.get("x", 0), bomb.get("y", 0)
                bomb_cell = pos_to_cell_bot(bomb_x, bomb_y)
                distance = abs(bomb_cell[0] - cell[0]) + abs(bomb_cell[1] - cell[1])
                
                # Nếu bom gần và sắp nổ (trong vòng 3.5 giây)
                if distance <= 4:
                    life_time = bomb.get("lifeTime", 5000)
                    if life_time <= 3500:  # Còn ít hơn 3.5 giây
                        logger.info(f"🏃 CẦN THOÁT: bom sắp nổ tại {bomb_cell}, còn {life_time}ms")
                        return True
        except Exception:
            pass
            
        return False
    
    def _get_escape_move(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi để thoát khỏi vùng nguy hiểm"""
        try:
            from .helpers.escape_planner import EscapePlanner
            
            my_uid = game_state.get("my_uid")
            explosion_range = get_bomber_explosion_range(my_uid)
            bombs = game_state.get("bombs", [])
            
            # Tìm bom gần nhất
            if bombs:
                nearest_bomb = min(bombs, key=lambda b: abs(pos_to_cell_bot(b.get("x", 0), b.get("y", 0))[0] - current_cell[0]) + 
                                                         abs(pos_to_cell_bot(b.get("x", 0), b.get("y", 0))[1] - current_cell[1]))
                bomb_cell = pos_to_cell_bot(nearest_bomb.get("x", 0), nearest_bomb.get("y", 0))
                life_time = nearest_bomb.get("lifeTime", 5000)
                
                result = EscapePlanner.find_escape_path_from_bomb(bomb_cell, current_cell, explosion_range, life_time)
                if result and len(result[0]) >= 2:
                    next_cell = result[0][1]
                    logger.info(f"✅ ESCAPE: {current_cell} → {next_cell}, t={result[1]:.0f}ms < {life_time:.0f}ms")
                    self._update_last_direction(current_cell, next_cell)
                    return {"type": "move", "goal_cell": next_cell}
        except Exception as e:
            logger.error(f"❌ Lỗi escape: {e}")
        
        # Fallback: tìm ô an toàn gần nhất
        best_move = None
        best_score = -1
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if not self._is_cell_passable(next_cell):
                continue
            score = 100.0 if not self._is_in_danger(next_cell, current_time) else 0.0
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🏃 ESCAPE FALLBACK: {current_cell} → {best_move}")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        return None
        
    def _is_in_danger(self, cell: Tuple[int, int], current_time: float) -> bool:
        """Kiểm tra nguy hiểm dựa trên FastGameState.hazard_until (TTL theo tick)."""
        fs = get_fast_state()
        if not fs.static:
            return False
        # Quy đổi ms -> tick (xấp xỉ giây)
        now_tick = fs.tick
        # Thêm dự báo 1 bước nhỏ nếu đang xét tương lai gần
        # delta_ms không dùng ở đây để tránh lệch lớn
        cx, cy = cell
        # Convert float to int for numpy array indexing
        cx, cy = int(cx), int(cy)
        if not fs.static.in_bounds(cx, cy):
            return True
        return fs.dynamic.hazard_until[cy, cx] > now_tick
            
    def _find_escape_move(self, cell: Tuple[int, int], current_time: float) -> Optional[str]:
        """Tìm hướng thoát hiểm"""
        # Tìm hướng an toàn
        for direction, (dx, dy) in DIRECTIONS.items():
            next_cell = (cell[0] + dx, cell[1] + dy)
            
            # Kiểm tra có thể đi qua không
            if not self._is_cell_passable(next_cell):
                continue
                
            # Kiểm tra có an toàn không
            if not self._is_in_danger(next_cell, current_time + 1000):  # 1s ahead
                return direction
                
            return None
        
    def _is_cell_passable(self, cell: Tuple[int, int]) -> bool:
        """Kiểm tra ô có thể đi qua theo FastGameState (bitmask)."""
        fs = get_fast_state()
        if not fs.static:
            return False
        cx, cy = cell
        # Convert float to int for numpy array indexing
        cx, cy = int(cx), int(cy)
        if not fs.static.in_bounds(cx, cy):
            return False
        walkable = fs.walkable_mask(avoid_hazard=False)
        return bool(walkable[cy, cx])
        
        
    def _find_nearby_items(self, cell: Tuple[int, int], radius: int = 3) -> List[Tuple[int, int]]:
        """Tìm vật phẩm gần đó từ FastGameState.dynamic.items."""
        fs = get_fast_state()
        if not fs.dynamic.items:
            return []
        nearby_items = []
        cx, cy = cell
        for (ix, iy) in fs.dynamic.items.keys():
            if abs(ix - cx) + abs(iy - cy) <= radius:
                nearby_items.append((ix, iy))
        return nearby_items
        
    def _find_item_goal(self, cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm mục tiêu vật phẩm gần nhất"""
        nearby_items = self._find_nearby_items(cell, radius=5)
        if not nearby_items:
            return None
            
        # Tìm vật phẩm gần nhất và an toàn
        best_item = None
        best_distance = float('inf')
        
        for item_cell in nearby_items:
            distance = abs(item_cell[0] - cell[0]) + abs(item_cell[1] - cell[1])
            if distance < best_distance:
                # Kiểm tra an toàn
                if not self._is_in_danger(item_cell, current_time + 2000):  # 2s ahead
                    best_distance = distance
                    best_item = item_cell
                
        return best_item
        
    def _find_safe_goal(self, cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm mục tiêu an toàn thông minh"""
        logger.info(f"🔍 TÌM MỤC TIÊU AN TOÀN: từ {cell}")
        
        # Tìm ô an toàn trong vòng 6 bước
        for radius in range(2, 7):
            candidates = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    target = (cell[0] + dx, cell[1] + dy)
                    if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                        target != cell and 
                        self._is_cell_passable(target) and 
                        not self._is_in_danger(target, current_time + 2000)):
                        distance = abs(dx) + abs(dy)
                        priority = distance
                        
                        # Ưu tiên ô chưa thăm
                        if target not in self.visited_cells:
                            priority += 5
                            
                        candidates.append((priority, target))
            
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_target = candidates[0][1]
                logger.info(f"🎯 TÌM THẤY {len(candidates)} ô an toàn trong bán kính {radius}: {best_target}")
                return best_target
        
        logger.warning(f"🚫 KHÔNG TÌM THẤY ô an toàn từ {cell}")
        return None
        
        
        
    def _should_place_bomb_for_chest(self, cell: Tuple[int, int], current_time: float, can_place: bool) -> bool:
        """
        Quyết định có nên đặt bom để nổ rương không
        CÁCH MỚI: Sử dụng AdvancedBombingStrategy với timing calculation
        """
        if not can_place:
            return False
        
        # Kiểm tra cooldown
        cooldown = 500 if current_time - self.bomb_exploded_time < 3000 else 2000
        if current_time - self.last_bomb_time_ms < cooldown:
            return False
        
        # Kiểm tra nguy hiểm hiện tại
        if self._is_in_danger(cell, current_time) or self._has_dangerous_bombs_nearby(cell, current_time):
            return False
        
        # SỬ DỤNG ADVANCED BOMBING STRATEGY
        try:
            from .helpers.advanced_bombing import AdvancedBombingStrategy
            
            # Kiểm tra có an toàn để đặt bom không
            should_place = AdvancedBombingStrategy.should_place_bomb_now(
                cell, cell, can_place
            )
            
            if should_place:
                logger.info(f"✅ AN TOÀN ĐẶT BOM: Đã kiểm tra đường thoát và timing")
                return True
            else:
                logger.warning(f"⚠️ KHÔNG AN TOÀN: Không đủ điều kiện đặt bom tại {cell}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi advanced bombing: {e}")
            # Fallback về logic cũ
            if (self._has_chest_in_bomb_range(cell) and self._has_escape_after_bomb(cell)):
                logger.info(f"💣 ĐẶT BOM (FALLBACK): có rương và có lối thoát")
                return True
            return False
    
    def _has_chest_in_bomb_range(self, cell: Tuple[int, int]) -> bool:
        """Kiểm tra có rương trong tầm nổ của bom không (tính tầm nổ thực tế)"""
        try:
            from .game_state import game_state, has_chest_at_tile, has_wall_at_tile, in_bounds
            
            my_uid = game_state.get("my_uid")
            if not my_uid:
                return False
                
            # Lấy tầm nổ của bom
            explosion_range = get_bomber_explosion_range(my_uid)
            
            # Kiểm tra 4 hướng: UP, DOWN, LEFT, RIGHT
            for direction, (dx, dy) in DIRECTIONS.items():
                chest_found = False
                
                # Duyệt từ vị trí bom ra ngoài theo hướng
                for distance in range(1, explosion_range + 1):
                    check_cell = (cell[0] + dx * distance, cell[1] + dy * distance)
                    
                    # Kiểm tra trong bounds
                    if not in_bounds(check_cell[0], check_cell[1]):
                        break
                    
                    # Nếu gặp tường, dừng lại (không nổ qua tường)
                    if has_wall_at_tile(check_cell[0], check_cell[1]):
                        break
                    
                    # Nếu có rương, đánh dấu tìm thấy
                    if has_chest_at_tile(check_cell[0], check_cell[1]):
                        chest_found = True
                        logger.info(f"💎 TÌM THẤY RƯƠNG TRONG TẦM NỔ: {check_cell} (hướng {direction}, khoảng cách {distance})")
                        break
                
                # Nếu tìm thấy rương ở bất kỳ hướng nào, return True
                if chest_found:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra tầm nổ: {e}")
            return False
        
    def _has_escape_after_bomb(self, cell: Tuple[int, int]) -> bool:
        """Kiểm tra có lối thoát sau khi đặt bom"""
        try:
            # Tính vùng nổ của bom
            my_uid = game_state.get("my_uid")
            explosion_range = get_bomber_explosion_range(my_uid)
            
            blast_cells = set()
            blast_cells.add(cell)
            
            # Tính vùng nổ theo 4 hướng
            for dx, dy in DIRECTIONS.values():
                for k in range(1, explosion_range + 1):
                    nx, ny = cell[0] + dx * k, cell[1] + dy * k
                    blast_cells.add((nx, ny))
                    
                    # Dừng tại tường
                    mp = game_state.get("map", [])
                    if (0 <= nx < len(mp[0]) and 0 <= ny < len(mp) and mp[ny][nx] == "W"):
                        break
                        
            # Tìm ô an toàn gần vị trí hiện tại (trong bán kính 3)
            safe_cells = []
            mp = game_state.get("map", [])
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    check_cell = (cell[0] + dx, cell[1] + dy)
                    if (check_cell not in blast_cells and 
                        self._is_cell_passable(check_cell) and
                        0 <= check_cell[0] < len(mp[0]) and 0 <= check_cell[1] < len(mp)):
                        safe_cells.append(check_cell)
            
            # Cần ít nhất 1 lối thoát gần đó
            has_escape = len(safe_cells) > 0
            if not has_escape:
                logger.info(f"🚫 KHÔNG CÓ LỐI THOÁT: vùng nổ={len(blast_cells)} ô, an toàn={len(safe_cells)} ô")
            else:
                logger.info(f"✅ CÓ LỐI THOÁT: {len(safe_cells)} ô an toàn gần đó")
            
            return has_escape
            
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra lối thoát: {e}")
            return False
        
    def _get_safe_move(self, cell: Tuple[int, int], current_time: float) -> Optional[str]:
        """Lấy di chuyển an toàn"""
        # Ưu tiên đi đến một ô an toàn gần nhất bằng BFS (radial search đơn giản)
        fs = get_fast_state()
        if not fs.static:
            return None
        # trước hết thử 4 hướng kề nếu an toàn
        for direction, (dx, dy) in DIRECTIONS.items():
            next_cell = (cell[0] + dx, cell[1] + dy)
            if self._is_cell_passable(next_cell) and not self._is_in_danger(next_cell, current_time + 1000):
                return direction
        # nếu không có, tìm một ô an toàn trong vòng 4 bước và đi bước đầu tiên theo BFS
        for radius in (2, 3, 4):
            candidates: list[Tuple[int, int]] = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    tgt = (cell[0] + dx, cell[1] + dy)
                    if not self._is_cell_passable(tgt):
                        continue
                    if not self._is_in_danger(tgt, current_time + 1000):
                        candidates.append(tgt)
            candidates.sort(key=lambda p: abs(p[0] - cell[0]) + abs(p[1] - cell[1]))
            for tgt in candidates[:6]:
                path = astar_shortest_path(cell, tgt, avoid_hazard=True, avoid_bots=False)
                if not path:
                    path = bfs_shortest_path(cell, tgt, avoid_hazard=True, avoid_bots=False)
                if path and len(path) >= 2:
                    return self._get_direction_to_cell(cell, path[1])
        return None
    
    def _find_bomb_position_near_chest(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm vị trí đặt bom gần rương"""
        try:
            from .helpers.advanced_bombing import AdvancedBombingStrategy
            from .game_state import astar_shortest_path
            
            best_position = AdvancedBombingStrategy.find_best_bombing_position(
                current_cell, max_search_radius=16,
                blacklist=self.failed_bomb_positions, current_time=current_time
            )
            
            if best_position and not self._is_position_blacklisted(best_position, current_time):
                if best_position != current_cell:
                    path = astar_shortest_path(current_cell, best_position, avoid_hazard=True, avoid_bots=False)
                    if not path or len(path) < 2:
                        return None
                logger.info(f"🎯 Tìm thấy vị trí đặt bom: {best_position}")
                return best_position
        except Exception as e:
            logger.error(f"❌ Lỗi bombing: {e}")
        return None
    
    def _is_position_blacklisted(self, position: Tuple[int, int], current_time: float) -> bool:
        """Kiểm tra vị trí có trong blacklist không"""
        if position in self.failed_bomb_positions:
            failed_time = self.failed_bomb_positions[position]
            if current_time - failed_time < self.blacklist_duration:
                return True
            else:
                # Xóa khỏi blacklist nếu đã hết hạn
                del self.failed_bomb_positions[position]
        return False
    
    def _add_to_blacklist(self, position: Tuple[int, int], current_time: float):
        """Thêm vị trí vào blacklist"""
        self.failed_bomb_positions[position] = current_time
        logger.info(f"🚫 BLACKLIST: Thêm {position} vào danh sách cấm ({len(self.failed_bomb_positions)} vị trí)")

    def _get_bomb_positions_for_chest_with_range(self, chest: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm vị trí đặt bom để nổ rương - SỬ DỤNG TẦM NỔ THỰC TẾ"""
        try:
            from .game_state import game_state, has_wall_at_tile, in_bounds
            
            my_uid = game_state.get("my_uid")
            if not my_uid:
                return []
                
            # Lấy tầm nổ của bom
            explosion_range = get_bomber_explosion_range(my_uid)
            bomb_positions = []
            
            # Tìm vị trí đặt bom trong tầm nổ của rương
            # Duyệt từ rương ra ngoài theo 4 hướng
            for direction, (dx, dy) in DIRECTIONS.items():
                for distance in range(1, explosion_range + 1):
                    # Vị trí đặt bom = rương - hướng * khoảng cách
                    bomb_pos = (chest[0] - dx * distance, chest[1] - dy * distance)
                    
                    # Kiểm tra trong bounds
                    if not in_bounds(bomb_pos[0], bomb_pos[1]):
                        break
                    
                    # Nếu gặp tường, dừng lại (không thể đặt bom qua tường)
                    if has_wall_at_tile(bomb_pos[0], bomb_pos[1]):
                        break
                    
                    # Kiểm tra có thể đặt bom tại vị trí này
                    if self._is_cell_passable(bomb_pos):
                        bomb_positions.append(bomb_pos)
            
            return bomb_positions
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm vị trí đặt bom: {e}")
            return []
    
    def _find_chests_in_range(self, current_cell: Tuple[int, int], max_range: int) -> List[Tuple[int, int]]:
        """Tìm rương trong tầm cho trước"""
        chests = []
        try:
            from .game_state import game_state
            chest_data = game_state.get("chests", [])
            for chest in chest_data:
                chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                distance = abs(chest_cell[0] - current_cell[0]) + abs(chest_cell[1] - current_cell[1])
                if distance <= max_range:
                    chests.append(chest_cell)
        except Exception:
            pass
        return chests
    
    def _get_bomb_positions_for_chest(self, chest_cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm các vị trí có thể đặt bom để nổ rương"""
        bomb_positions = []
        
        # Tìm vị trí đặt bom trong tầm nổ (4 ô)
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if dx == 0 and dy == 0:
                    continue
                bomb_pos = (chest_cell[0] + dx, chest_cell[1] + dy)
                
                # TRÁNH HÀNG/CỘT BIÊN: 0, 16
                if (bomb_pos[0] <= 0 or bomb_pos[0] >= 16 or 
                    bomb_pos[1] <= 0 or bomb_pos[1] >= 16):
                    continue
                
                # Kiểm tra bom có thể nổ đến rương không
                if self._can_bomb_reach_chest(bomb_pos, chest_cell):
                    bomb_positions.append(bomb_pos)
                    
        return bomb_positions
    
    def _can_bomb_reach_chest(self, bomb_pos: Tuple[int, int], chest_pos: Tuple[int, int]) -> bool:
        """Kiểm tra bom có thể nổ đến rương không"""
        # Kiểm tra cùng hàng hoặc cùng cột
        if bomb_pos[0] == chest_pos[0] or bomb_pos[1] == chest_pos[1]:
            # Kiểm tra khoảng cách trong tầm nổ (4 ô)
            distance = abs(bomb_pos[0] - chest_pos[0]) + abs(bomb_pos[1] - chest_pos[1])
            return distance <= 4
        return False
    
# Sử dụng pos_to_cell từ game_state thay vì định nghĩa lại
    
    def _update_my_bombs(self) -> None:
        """Cập nhật theo dõi bom của mình"""
        try:
            from .game_state import game_state
            my_uid = game_state.get("my_uid")
            if not my_uid:
                return
                
            current_bombs = set()
            bombs = game_state.get("bombs", [])
            
            for bomb in bombs:
                if bomb.get("uid") == my_uid:
                    bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
                    current_bombs.add(bomb_cell)
            
            # Kiểm tra bom nào đã nổ (không còn trong danh sách)
            exploded_bombs = self.my_bombs - current_bombs
            if exploded_bombs:
                self.bomb_exploded_time = time.time() * 1000
                logger.info(f"💥 BOM NỔ: {exploded_bombs} - Sẵn sàng đặt bom tiếp")
            
            self.my_bombs = current_bombs
            
        except Exception as e:
            logger.error(f"Lỗi cập nhật bom: {e}")
    
    def _should_continue_bombing(self, current_cell: Tuple[int, int], current_time: float, can_place: bool) -> bool:
        """Kiểm tra có nên tiếp tục đặt bom sau khi bom nổ"""
        if not can_place:
            return False
            
        # Chỉ đặt bom liên tục trong vòng 3 giây sau khi bom nổ
        time_since_explosion = current_time - self.bomb_exploded_time
        if time_since_explosion > 3000:  # 3 giây
            return False
            
        # Không đặt bom nếu đang trong nguy hiểm
        if self._is_in_danger(current_cell, current_time):
            return False
            
        # Kiểm tra có bom nguy hiểm gần đó không
        if self._has_dangerous_bombs_nearby(current_cell, current_time):
            return False
            
        # Kiểm tra có rương kề cạnh không
        adjacent_chest = False
        for dx, dy in DIRECTIONS.values():
            nx, ny = current_cell[0] + dx, current_cell[1] + dy
            if has_chest_at_tile(nx, ny):
                adjacent_chest = True
                break
                
        if not adjacent_chest:
            return False
            
        # Kiểm tra có lối thoát sau khi đặt bom
        if not self._has_escape_after_bomb(current_cell):
            return False
            
        logger.info(f"💣 ĐẶT BOM LIÊN TỤC: có rương kề cạnh và an toàn")
        return True
    
    def _find_best_item_to_collect(self, items: List[Tuple[int, int]], current_cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm vật phẩm tốt nhất để nhặt dựa trên ưu tiên và khoảng cách"""
        if not items:
            return None
            
        best_item = None
        best_score = -1
        
        for item_cell in items:
            # Kiểm tra an toàn
            if self._is_in_danger(item_cell, current_time + 2000):
                continue
                
            # Tính khoảng cách
            distance = abs(item_cell[0] - current_cell[0]) + abs(item_cell[1] - current_cell[1])
            
            # Lấy loại vật phẩm
            try:
                from .game_state import get_tile_item
                item_type = get_tile_item(item_cell[0], item_cell[1])
            except Exception:
                continue
                
            # Tính điểm ưu tiên
            priority = self._get_item_priority(item_type)
            score = priority - distance  # Ưu tiên cao, khoảng cách ngắn
            
            if score > best_score:
                best_score = score
                best_item = item_cell
                
        if best_item:
            try:
                from .game_state import get_tile_item
                item_type = get_tile_item(best_item[0], best_item[1])
                logger.info(f"💎 CHỌN VẬT PHẨM: {item_type} tại {best_item} (score={best_score})")
            except Exception:
                pass
                
        return best_item
    
    def _get_item_priority(self, item_type: str) -> int:
        """Lấy điểm ưu tiên của vật phẩm"""
        priorities = {
            "SPEED": 100,           # Giày - ưu tiên cao nhất (tăng tốc độ)
            "EXPLOSION_RANGE": 90,  # Liệt hỏa - ưu tiên cao (tăng tầm nổ)
            "BOMB_COUNT": 80,       # Đa bom - ưu tiên trung bình (tăng số bom)
        }
        return priorities.get(item_type, 0)
    
    def _create_long_term_plan(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict]:
        """Tạo plan dài hạn với mục tiêu rõ ràng"""
        try:
            # 1. ƯU TIÊN NHẶT VẬT PHẨM QUAN TRỌNG
            important_items = self._find_important_items(current_cell)
            if important_items:
                best_item = self._find_best_item_to_collect(important_items, current_cell, current_time)
                if best_item and best_item != current_cell:
                    return {
                        "type": "collect_item",
                        "goal_cell": best_item,
                        "action": "move",
                        "reason": "Nhặt vật phẩm quan trọng"
                    }
            
            # 2. TÌM VỊ TRÍ ĐẶT BOM GẦN RƯƠNG
            bomb_position = self._find_bomb_position_near_chest(current_cell, current_time)
            if bomb_position:
                # Tính escape path cho plan bomb_chest
                escape_info = self._calculate_escape_plan(bomb_position, current_cell)
                
                return {
                    "type": "bomb_chest", 
                    "goal_cell": bomb_position,
                    "action": "bomb" if bomb_position == current_cell else "move",
                    "reason": "Đặt bom nổ rương",
                    "escape_cell": escape_info.get("escape_cell"),
                    "escape_path": escape_info.get("escape_path", []),
                    "escape_time": escape_info.get("escape_time", 0)
                }
            
            # 3. CHIẾN LƯỢC DÀI HẠN
            strategic_goal = self._get_strategic_goal(current_cell)
            if strategic_goal and strategic_goal != current_cell:
                return {
                    "type": "explore",
                    "goal_cell": strategic_goal, 
                    "action": "move",
                    "reason": "Khám phá khu vực mới"
                }
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi tạo plan dài hạn: {e}")
            return None
    
    def _has_dangerous_bombs_nearby(self, cell: Tuple[int, int], current_time: float) -> bool:
        """Kiểm tra có bom nguy hiểm gần đó không (trong vòng 3 ô)"""
        try:
            from .game_state import game_state
            bombs = game_state.get("bombs", [])
            for bomb in bombs:
                bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
                distance = abs(bomb_cell[0] - cell[0]) + abs(bomb_cell[1] - cell[1])
                
                # Kiểm tra bom trong vòng 3 ô
                if distance <= 3:
                    # Kiểm tra bom có sắp nổ không (còn ít hơn 3 giây)
                    life_time = bomb.get("lifeTime", 5.0)
                    created_at = bomb.get("createdAt", current_time / 1000)
                    elapsed = (current_time / 1000) - created_at
                    remaining = life_time - elapsed
                    
                    if remaining <= 3.0:  # Bom sắp nổ trong 3 giây
                        logger.info(f"⚠️ BOM NGUY HIỂM: tại {bomb_cell}, còn {remaining:.1f}s")
                        return True
        except Exception as e:
            logger.error(f"Lỗi kiểm tra bom nguy hiểm: {e}")
        return False

# Instance toàn cục
survival_ai = SimpleSurvivalAI()

def choose_next_action() -> Optional[Dict[str, Any]]:
    """Điểm vào chính cho quyết định AI"""
    return survival_ai.choose_next_action()

def reset_ai_state():
    """Reset AI state toàn cục"""
    try:
        # Reset global AI instance nếu có
        global survival_ai
        if survival_ai:
            survival_ai.reset_state()
        logger.info(f"✅ GLOBAL AI RESET: Hoàn thành")
    except Exception as e:
        logger.error(f"❌ Lỗi reset global AI: {e}")