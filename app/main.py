#!/usr/bin/env python3
"""
Bot Bomberman - Zinza Hackathon 2025
Bot AI đơn giản với chiến lược sinh tồn
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

# Hệ thống log di chuyển đơn giản
class MovementLogger:
    def __init__(self):
        self.current_direction = None
        self.last_logged_cell = None  # Track ô đã log
        
    def log_movement(self, direction: str):
        """Log di chuyển - chỉ log khi thay đổi hướng"""
        if not LOG_MOVEMENT:
            return
        if self.current_direction != direction:
            self.current_direction = direction
            me = get_my_bomber()
            if me:
                px, py = me.get("x", 0), me.get("y", 0)
                current_cell = pos_to_cell(px, py)
                logger.info(f"🚶 DI CHUYỂN: pixel({px:.1f},{py:.1f}) tile{current_cell} → {direction}")
            else:
                logger.info(f"🚶 DI CHUYỂN: {direction}")
    
    def check_and_log_cell_arrival(self):
        """Kiểm tra và log khi bot vào ô mới"""
        if not LOG_MOVEMENT:
            return
        me = get_my_bomber()
        if not me:
            return
        
        px, py = me.get("x", 0), me.get("y", 0)
        current_cell = pos_to_cell(px, py)
        
        # Chỉ log khi vào ô MỚI
        if current_cell != self.last_logged_cell:
            logger.info(f"📍 VÀO Ô: pixel({px:.1f},{py:.1f}) → tile{current_cell}")
            self.last_logged_cell = current_cell
    
    def flush(self):
        pass

movement_logger = MovementLogger()

def log_map_state(force: bool = False):
    """Log trạng thái bản đồ trước khi phân tích plan"""
    if not LOG_MAP and not force:
        return
        
    try:
        # Lấy thông tin map
        map_data = game_state.get("map", [])
        if isinstance(map_data, dict):
            tiles = map_data.get("tiles", [])
        else:
            tiles = map_data if isinstance(map_data, list) else []
        
        # DEBUG: Log cấu trúc dữ liệu map (chỉ khi cần debug)
        if LOG_GAME_EVENTS:  # Tắt debug log
            logger.info(f"🗺️ DEBUG MAP: type={type(map_data)}, tiles_type={type(tiles)}")
            if tiles and len(tiles) > 0:
                logger.info(f"🗺️ DEBUG TILES: len={len(tiles)}")
        
        bombs = game_state.get("bombs", [])
        items = game_state.get("items", [])
        chests = game_state.get("chests", [])
        
        # Lấy vị trí bot
        me = get_my_bomber()
        bot_cell = None
        if me:
            bot_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        
        # Tạo map 14x14 (bỏ hàng/cột biên - chỉ hiển thị khu vực bên trong)
        map_lines = []
        
        for y in range(1, 15):  # Hàng 1-14 (bỏ hàng 0 và 15)
            line = ""
            for x in range(1, 15):  # Cột 1-14 (bỏ cột 0 và 15)
                # Kiểm tra bot
                if bot_cell and bot_cell == (x, y):
                    line += "X"  # Bot
                    continue
                
                # Kiểm tra bomb
                has_bomb = False
                for bomb in bombs:
                    bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
                    if bomb_cell == (x, y):
                        line += "b"  # Bomb
                        has_bomb = True
                        break
                
                if has_bomb:
                    continue
                
                # Kiểm tra rương
                has_chest = False
                for chest in chests:
                    chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                    if chest_cell == (x, y):
                        line += "r"  # Rương
                        has_chest = True
                        break
                
                if has_chest:
                    continue
                
                # Kiểm tra item
                has_item = False
                for item in items:
                    item_cell = pos_to_cell(item.get("x", 0), item.get("y", 0))
                    if item_cell == (x, y):
                        item_type = item.get("type", "")
                        if item_type == "SPEED":
                            line += "g"  # Giày
                        elif item_type == "BOMB_COUNT":
                            line += "c"  # Item bom
                        elif item_type == "EXPLOSION_RANGE":
                            line += "l"  # Lửa
                        else:
                            line += "i"  # Item khác
                        has_item = True
                        break
                
                if has_item:
                    continue
                
                # Kiểm tra tường - LOGIC SỬA LẠI
                try:
                    # Kiểm tra bounds trước
                    if y < len(tiles) and x < len(tiles[y]):
                        # Kiểm tra tile có phải tường không - SỬA: tiles[y][x]
                        tile_value = tiles[y][x]
                        if tile_value == 'W' or tile_value == 1:  # Hỗ trợ cả string 'W' và số 1
                            line += "x"  # Tường
                        else:
                            line += "-"  # Trống
                    else:
                        # Ngoài bounds = tường
                        line += "x"  # Tường
                except Exception as e:
                    # Lỗi = coi như tường
                    line += "x"  # Tường
            
            map_lines.append(line)
        
        # Log map
        logger.info("🗺️ BẢN ĐỒ HIỆN TẠI (khu vực bên trong):")
        for i, line in enumerate(map_lines):
            logger.info(f"🗺️ {i+1:2d}|{line}")
        
        # Log chú thích
        logger.info("🗺️ CHÚ THÍCH: x=tường, r=rương, X=bot, b=bomb, g=giày, c=item bom, l=lửa, -=trống")
        
    except Exception as e:
        logger.error(f"🗺️ Lỗi log map: {e}")

# Import các module cần thiết
from aiolimiter import AsyncLimiter
from fastapi import FastAPI
import socketio

# Import config và modules
from .config import (
    SOCKET_SERVER, TOKEN, TICK_HZ, MAX_CMDS_PER_SEC, CELL_SIZE, LOG_LEVEL, BOT_NAME,
    ARRIVAL_TOLERANCE_PX, REVERSE_LOCK_SECONDS, PREALIGN_MARGIN_PX, BOT_SIZE,
    LOG_MOVEMENT, LOG_ITEMS, LOG_BOMBS, LOG_CHESTS, LOG_MAP, LOG_AI,
    LOG_SOCKET, LOG_GAME_EVENTS, LOG_ITEM_COLLECTION, LOG_BOMB_EVENTS,
    DIRECTIONS
)
from .game_state import (
    game_state, can_send_command, get_my_bomber, pos_to_cell, cell_to_pos, 
    cell_top_left_pos, pos_to_cell_bot, is_passable
)
from .survival_ai import choose_next_action
from .socket_handlers import (
    handle_connect, handle_disconnect, handle_user, handle_start, 
    handle_finish, handle_player_move, handle_new_bomb, 
    handle_bomb_explode, handle_map_update, handle_item_collected,
    handle_chest_destroyed, handle_new_enemy, handle_user_die_update,
    handle_user_disconnect, handle_new_life
)

# Giới hạn tốc độ gửi lệnh
cmd_limiter = AsyncLimiter(max_rate=MAX_CMDS_PER_SEC, time_period=1)
logger = logging.getLogger("bot")

# Khởi tạo Socket.IO client
sio = socketio.AsyncClient(
    reconnection=True, 
    reconnection_attempts=0, 
    logger=False, 
    engineio_logger=False
)

# ---------- Ack logging helpers ----------
def _ack_logger(event_name: str):
    def _cb(res=None):
        try:
            logger.info(f"ACK {event_name}: {res}")
        except Exception:
            pass
    return _cb

# ---------- Move pacing (evenly spread per second) ----------
_last_move_emit_time: float = 0.0
_recent_orient: str | None = None
_reverse_block_until: float = 0.0
_arrival_block_until: float = 0.0
_last_pos: tuple = (0.0, 0.0)
_stuck_count: int = 0
_oscillation_detector: list = []  # Lưu lịch sử hướng di chuyển để phát hiện oscillation

def _detect_oscillation(direction: str) -> bool:
    """Phát hiện oscillation"""
    global _oscillation_detector
    _oscillation_detector.append(direction)
    
    if len(_oscillation_detector) > 10:
        _oscillation_detector = _oscillation_detector[-10:]
    
    if len(_oscillation_detector) < 4:
        return False
    
    # Kiểm tra pattern A-B-A-B
    if len(_oscillation_detector) >= 4:
        last_4 = _oscillation_detector[-4:]
        if (last_4[0] == last_4[2] and last_4[1] == last_4[3] and 
            last_4[0] != last_4[1]):
            return True
    
    return False

def _can_emit_move_now() -> bool:
    global _last_move_emit_time
    min_interval = 1.0 / max(1.0, MAX_CMDS_PER_SEC)
    now = time.monotonic()
    return (now - _last_move_emit_time) >= min_interval


async def _maybe_emit_move(orient: str):
    global _last_move_emit_time
    if not _can_emit_move_now():
        return
    await send_move(orient)
    _last_move_emit_time = time.monotonic()
    # Ghi nhận hướng vừa gửi để chống đảo chiều ngay lập tức
    global _recent_orient
    _recent_orient = orient

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời FastAPI"""
    # Cấu hình mức log theo LOG_LEVEL
    try:
        level = getattr(logging, LOG_LEVEL, logging.INFO)
        logging.basicConfig(level=level)
        logger.setLevel(level)
    except Exception:
        pass
    logger.info("🚀 Khởi động bot...")
    try:
        # Tạm thời tắt AI đa luồng
        # multithread_ai.start()
        await startup()
        logger.info("🚀 Bot đã sẵn sàng")
    except Exception as e:
        logger.error(f"🚀 Lỗi khởi động: {e}")
    yield
    # Dừng AI đa luồng
    # multithread_ai.stop()
    logger.info("🚀 Bot đã dừng")

app = FastAPI(lifespan=lifespan)

# ---------- API Endpoints ----------
@app.get("/healthz")
async def health_check():
    """Kiểm tra trạng thái bot"""
    return {
        "status": "ok", 
        "connected": game_state["connected"], 
        "started": game_state["game_started"]
    }

@app.get("/state")
async def get_state():
    """Lấy trạng thái game hiện tại"""
    me = get_my_bomber()
    return {
        "connected": game_state["connected"],
        "started": game_state["game_started"],
        "my_uid": game_state["my_uid"],
        "me": me,
        "bombs": len(game_state.get("bombs", [])),
        "items": len(game_state.get("items", [])),
        "chests": len(game_state.get("chests", [])),
    }


# ---------- Socket Event Handlers ----------
@sio.event
async def connect():
    """Xử lý kết nối socket"""
    handle_connect()
    
    # Gửi yêu cầu tham gia ngay sau khi kết nối
    try:
        await sio.emit("join", {})
    except Exception as e:
        logger.error(f"Lỗi gửi join: {e}")

@sio.event
async def connect_error(data):
    """Xử lý lỗi kết nối"""
    logger.error(f"Lỗi kết nối: {data}")

@sio.event
async def disconnect():
    """Xử lý ngắt kết nối"""
    handle_disconnect()

@sio.on("user")
async def on_user(data=None):
    """Xử lý sự kiện user"""
    handle_user(data or {})

@sio.on("start")
async def on_start(data=None):
    """Xử lý sự kiện bắt đầu game"""
    logger.info(f"🎮 GAME BẮT ĐẦU")
    handle_start(data or {})

@sio.on("finish")
async def on_finish(data=None):
    """Xử lý sự kiện kết thúc game"""
    logger.info(f"🏁 GAME KẾT THÚC")
    handle_finish(data or {})

@sio.on("player_move")
async def on_player_move(data=None):
    """Xử lý sự kiện di chuyển player"""
    handle_player_move(data or {})

@sio.on("new_bomb")
async def on_new_bomb(data=None):
    """Xử lý sự kiện bom mới"""
    handle_new_bomb(data or {})

@sio.on("bomb_explode")
async def on_bomb_explode(data=None):
    """Xử lý sự kiện bom nổ"""
    handle_bomb_explode(data or {})

@sio.on("map_update")
async def on_map_update(data=None):
    """Xử lý sự kiện cập nhật map"""
    handle_map_update(data or {})

@sio.on("item_collected")
async def on_item_collected(data=None):
    """Xử lý sự kiện nhặt item"""
    handle_item_collected(data or {})

@sio.on("chest_destroyed")
async def on_chest_destroyed(data=None):
    """Xử lý sự kiện rương bị phá"""
    handle_chest_destroyed(data or {})

@sio.on("new_enemy")
async def on_new_enemy(data=None):
    """Xử lý sự kiện bot mới tham gia"""
    handle_new_enemy(data or {})

@sio.on("user_die_update")
async def on_user_die_update(data=None):
    """Xử lý sự kiện bot bị hạ gục"""
    handle_user_die_update(data or {})

@sio.on("user_disconnect")
async def on_user_disconnect(data=None):
    """Xử lý sự kiện bot thoát khỏi phòng"""
    handle_user_disconnect(data or {})

@sio.on("new_life")
async def on_new_life(data=None):
    """Xử lý sự kiện bot hồi sinh"""
    handle_new_life(data or {})

# ---------- Bot Actions ----------
async def send_move(orient: str):
    """Gửi lệnh di chuyển với giới hạn tốc độ"""
    if orient not in DIRECTIONS:
        return
    if not can_send_command():
        logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Quá giới hạn tốc độ")
        return

    # Không chặn theo movable để tránh tự khóa khi server tạm thời set movable=False
    # Server sẽ quyết định hợp lệ và phản hồi qua player_move
    
    # Kiểm tra game đã bắt đầu chưa
    if not game_state.get("game_started", False):
        # Trong môi trường dev, cho phép di chuyển mà không cần start event
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            pass  # Bỏ log - không cần log di chuyển
        else:
            logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Game chưa bắt đầu - chờ start event - {orient}")
            return
    
    try:
        async with cmd_limiter:
            await sio.emit("move", {"orient": orient}, callback=_ack_logger("move"))
        movement_logger.log_movement(orient)
    except Exception as e:
        logger.error(f"❌ Lỗi di chuyển: {e}")

async def send_bomb():
    """Gửi lệnh đặt bom"""
    if not can_send_command():
        logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Quá giới hạn tốc độ")
        return
    
    # Kiểm tra bot có thể di chuyển không
    me = get_my_bomber()
    if me and not me.get("movable", True):
        logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Bot không thể di chuyển")
        return
    
    # Kiểm tra game đã bắt đầu chưa
    if not game_state.get("game_started", False):
        # Trong môi trường dev, cho phép đặt bom mà không cần start event
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            logger.info(f"💣 CHẾ ĐỘ DEV: Cho phép đặt bom mà không cần start event")
        else:
            logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Game chưa bắt đầu - chờ start event")
            return
    
    try:
        async with cmd_limiter:
            await sio.emit("place_bomb", {}, callback=_ack_logger("place_bomb"))
        logger.info(f"💣 ĐẶT BOM")
        
        # Cập nhật số bom local
        my_uid = game_state.get("my_uid")
        if my_uid:
            for bomber in game_state["bombers"]:
                if bomber.get("uid") == my_uid:
                    bomber["bombCount"] = max(0, bomber.get("bombCount", 1) - 1)
                    break
    except Exception as e:
        logger.error(f"Lỗi đặt bom: {e}")

# ---------- Bot Logic ----------
# Kế hoạch di chuyển dài hạn với đường đi thẳng
movement_plan = {
    "path": [],                # Danh sách các ô cần đi qua [(x1,y1), (x2,y2), ...]
    "current_target_index": 0, # Chỉ số ô hiện tại đang nhắm tới
    "orient": None,            # "UP"|"DOWN"|"LEFT"|"RIGHT" hiện tại
    "target_cell": None,       # (cx, cy) ô hiện tại đang nhắm tới
    "remaining_px": 0.0,       # số pixel còn lại để tới ô mục tiêu
    "skip_once": False,        # bỏ qua một lần gửi sau khi action để tránh double-send
    "long_term_goal": None,    # Mục tiêu dài hạn (x, y)
    "path_valid": False,       # Đường đi có còn hợp lệ không
}

def _reset_movement_plan() -> None:
    """Reset movement plan to initial state."""
    global movement_plan, _oscillation_detector
    movement_plan["path"] = []
    movement_plan["current_target_index"] = 0
    movement_plan["orient"] = None
    movement_plan["target_cell"] = None
    movement_plan["remaining_px"] = 0.0
    movement_plan["skip_once"] = False
    movement_plan["long_term_goal"] = None
    movement_plan["path_valid"] = False
    # Reset oscillation detector
    _oscillation_detector = []

def reset_global_state() -> None:
    """Reset toàn bộ global state khi game kết thúc"""
    global _last_move_emit_time, _recent_orient, _reverse_block_until, _arrival_block_until, _last_pos, _stuck_count, _oscillation_detector
    
    # Reset movement variables
    _last_move_emit_time = 0.0
    _recent_orient = None
    _reverse_block_until = 0.0
    _arrival_block_until = 0.0
    _last_pos = (0.0, 0.0)
    _stuck_count = 0
    _oscillation_detector = []
    
    # Reset movement plan
    _reset_movement_plan()
    
    # Reset movement logger
    global movement_logger
    movement_logger.current_direction = None
    
    logger.info("🔄 GLOBAL RESET: Đã reset toàn bộ global state")

def _plan_long_term_path(goal_cell: tuple) -> None:
    """Lập kế hoạch đường đi dài hạn từ vị trí hiện tại đến mục tiêu"""
    me = get_my_bomber()
    if not me:
        logger.warning(f"🚫 PLAN FAILED: Không tìm thấy bot")
        return
        
    current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
    logger.info(f"🗺️ LẬP PLAN: từ {current_cell} đến {goal_cell}")
    
    # Sử dụng A* để tìm đường đi tối ưu
    from .game_state import astar_shortest_path
    path = astar_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
    
    if path and len(path) > 1:
        movement_plan["path"] = path
        movement_plan["current_target_index"] = 1  # Bắt đầu từ ô thứ 2 (ô đầu là vị trí hiện tại)
        movement_plan["long_term_goal"] = goal_cell
        movement_plan["path_valid"] = True
        logger.info(f"🗺️ PLAN DÀI HẠN: {len(path)} ô từ {current_cell} đến {goal_cell}")
        logger.info(f"🗺️ PATH CHI TIẾT: {path}")
    else:
        # KHÔNG CÓ ĐƯỜNG ĐI - A* đã fail
        # Thử BFS một lần nữa trước khi bỏ cuộc
        from .game_state import bfs_shortest_path
        path_bfs = bfs_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
        
        if path_bfs and len(path_bfs) > 1:
            movement_plan["path"] = path_bfs
            movement_plan["current_target_index"] = 1
            movement_plan["long_term_goal"] = goal_cell
            movement_plan["path_valid"] = True
            logger.info(f"🗺️ PLAN BFS: {len(path_bfs)} ô từ {current_cell} đến {goal_cell}")
            logger.info(f"🗺️ PATH CHI TIẾT: {path_bfs}")
        else:
            # THỰC SỰ KHÔNG CÓ ĐƯỜNG - target không thể đến được
            logger.warning(f"❌ KHÔNG CÓ ĐƯỜNG ĐẾN: {goal_cell} từ {current_cell}")
            movement_plan["path_valid"] = False
            # Không set path - để AI chọn target khác
            best_cell = None
            min_distance = float('inf')
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx == 0 and dy == 0:
                        continue
                    test_cell = (goal_cell[0] + dx, goal_cell[1] + dy)
                    # Tránh vị trí hiện tại và kiểm tra passable
                    if test_cell != current_cell and is_passable(test_cell[0], test_cell[1]):
                        distance = abs(dx) + abs(dy)
                        if distance < min_distance:
                            min_distance = distance
                            best_cell = test_cell
            
            if best_cell and best_cell != current_cell:
                movement_plan["path"] = [current_cell, best_cell]
                movement_plan["current_target_index"] = 1
                movement_plan["long_term_goal"] = best_cell
                movement_plan["path_valid"] = True
                logger.info(f"🗺️ PLAN THAY THẾ: từ {current_cell} đến {best_cell}")
                logger.info(f"🗺️ PATH THAY THẾ: {movement_plan['path']}")
            else:
                logger.warning(f"🚫 KHÔNG TÌM THẤY Ô THAY THẾ cho {goal_cell}")
                # Reset plan để AI tìm mục tiêu mới
                movement_plan["path"] = []
                movement_plan["current_target_index"] = 0
                movement_plan["path_valid"] = False

def _get_next_direction_from_path() -> str:
    """Lấy hướng di chuyển tiếp theo từ path hiện tại"""
    if not movement_plan["path"] or movement_plan["current_target_index"] >= len(movement_plan["path"]):
        return None
        
    me = get_my_bomber()
    if not me:
        return None
        
    current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
    target_cell = movement_plan["path"][movement_plan["current_target_index"]]
    
    # Tính hướng di chuyển
    dx = target_cell[0] - current_cell[0]
    dy = target_cell[1] - current_cell[1]
    
    if dx > 0:
        direction = "RIGHT"
    elif dx < 0:
        direction = "LEFT"
    elif dy > 0:
        direction = "DOWN"
    elif dy < 0:
        direction = "UP"
    else:
        # Đã đến ô mục tiêu, chuyển sang ô tiếp theo
        movement_plan["current_target_index"] += 1
        if movement_plan["current_target_index"] < len(movement_plan["path"]):
            return _get_next_direction_from_path()
        return None
    
    return direction

def _advance_move_plan() -> None:
    """Thực hiện di chuyển theo plan dài hạn"""
    me = get_my_bomber()
    if not me:
        _reset_movement_plan()
        return
        
    if not movement_plan["path_valid"] or not movement_plan["path"]:
        return
        
    current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
    direction = _get_next_direction_from_path()
    if not direction:
        logger.info(f"✅ HOÀN THÀNH: đã đến {movement_plan['long_term_goal']}")
        _reset_movement_plan()
        # Set flag để skip 1 giây, cho bot cơ hội đặt bom hoặc AI tính toán
        movement_plan["just_completed"] = time.time()
        return
        
    if _detect_oscillation(direction):
        logger.warning(f"🚫 PHÁT HIỆN OSCILLATION: {_oscillation_detector[-4:]} - Reset plan!")
        _reset_movement_plan()
        _oscillation_detector = []
        return
    
    # Kiểm tra đảo chiều
    global _recent_orient, _reverse_block_until
    current_time = time.monotonic()
    if _recent_orient and current_time < _reverse_block_until:
        reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
        if direction == reverse.get(_recent_orient):
            logger.warning(f"🚫 CHỐNG ĐẢO CHIỀU: Bỏ qua hướng {direction}")
            return
    
    # KHÔNG SET ORIENT ĐẾN KHI CHECK ARRIVED!
    target_cell = movement_plan["path"][movement_plan["current_target_index"]]
    movement_plan["target_cell"] = target_cell
    
    # Tính toán arrival - kiểm tra BOT ĐÃ THỰC SỰ Ở TRONG TILE TARGET chưa
    curx, cury = me.get("x", 0.0), me.get("y", 0.0)
    actual_current_cell = pos_to_cell(curx, cury)
    
    # === LOGIC ARRIVAL ===
    # Cell được đánh số từ 0-15, mỗi cell 40x40px:
    # - Cell 0: 0-39, Cell 1: 40-79, Cell 2: 80-119, ...
    # 
    # Bot 35x35 được coi là "vào ô" khi top-left nằm trong tolerance 5px từ mép trái/trên:
    # Ví dụ Cell 1 (40-79):
    # - Top-left phải từ 40 đến 45 (vì bot 35px, 45+34=79 vẫn trong ô)
    # - Nếu top-left < 40: chưa vào ô
    # - Nếu top-left > 45: đã vào quá sâu (có thể bị overshoot)
    #
    # Arrived khi: pos_to_cell = target VÀ top-left đã vào đủ sâu
    
    cell_start_x = target_cell[0] * CELL_SIZE
    cell_start_y = target_cell[1] * CELL_SIZE
    
    # Check bot top-left nằm trong range hợp lệ của cell
    # Range: [cell_start, cell_start + 5] với tolerance nhỏ 1px cho biên
    tolerance = 1.0
    in_cell_x = (cell_start_x - tolerance) <= curx <= (cell_start_x + 5 + tolerance)
    in_cell_y = (cell_start_y - tolerance) <= cury <= (cell_start_y + 5 + tolerance)
    
    arrived = (
        actual_current_cell == target_cell and
        in_cell_x and 
        in_cell_y
    )
    
    # Tính remaining pixels đến target cell  
    goal_center_x = target_cell[0] * CELL_SIZE + CELL_SIZE // 2
    goal_center_y = target_cell[1] * CELL_SIZE + CELL_SIZE // 2
    
    if direction == "RIGHT":
        remain_px = max(0.0, goal_center_x - curx)
    elif direction == "LEFT":
        remain_px = max(0.0, curx - goal_center_x)
    elif direction == "DOWN":
        remain_px = max(0.0, goal_center_y - cury)
    else:  # UP
        remain_px = max(0.0, cury - goal_center_y)
        
    movement_plan["remaining_px"] = float(remain_px)
    
    if arrived:
        logger.info(f"✅ ĐẾN Ô: pixel({curx:.1f},{cury:.1f}) tile{actual_current_cell} = target{target_cell}")
        movement_plan["current_target_index"] += 1
        _reverse_block_until = current_time + REVERSE_LOCK_SECONDS
        _recent_orient = direction
        global _stuck_count
        _stuck_count = 0
        # QUAN TRỌNG: Clear orient để tránh gửi command cũ
        movement_plan["orient"] = None
        return  # Chờ loop tiếp
    else:
        # Chưa arrived → SET ORIENT để bot tiếp tục di chuyển
        movement_plan["orient"] = direction
        # Log trạng thái di chuyển chi tiết (chỉ khi debug cần)
        if remain_px > 0:
            logger.debug(f"🚶 ĐI: pixel({curx:.1f},{cury:.1f}) tile{actual_current_cell} → target{target_cell}, còn {remain_px:.1f}px")

async def bot_loop():
    """Vòng lặp quyết định chính của bot"""
    logger.info(f"🤖 Bắt đầu vòng lặp bot với TICK_HZ={TICK_HZ}")
    await asyncio.sleep(0.2)  # Để state ổn định
    
    period = 1.0 / max(TICK_HZ, 1.0)
    
    while True:
        start_time = time.time()
        try:
            # Kiểm tra trạng thái bot
            me = get_my_bomber()
            if not me:
                available_bombers = [b.get('name') for b in game_state.get('bombers', [])]
                logger.warning(f"🤖 Không tìm thấy bot! Có sẵn: {available_bombers}")
                
                # Thử tìm lại bot nếu có bombers
                if available_bombers:
                    logger.info("🔄 Thử tìm lại bot...")
                    # Reset my_uid và tìm lại
                    game_state["my_uid"] = None
                    # Ưu tiên chọn theo BOT_NAME
                    mine = next((b for b in game_state.get("bombers", [])
                                 if isinstance(b.get("name"), str) and b["name"].lower() == BOT_NAME.lower()), None)
                    if mine:
                        game_state["my_uid"] = mine.get("uid")
                        logger.info(f"🤖 CHỌN LẠI BOT THEO TÊN: {mine.get('name')} ({game_state['my_uid']})")
                    else:
                        uids = [b.get("uid") for b in game_state.get("bombers", [])]
                        if uids:
                            game_state["my_uid"] = game_state["bombers"][0].get("uid")
                            logger.info(f"🤖 CHỌN LẠI BOT (FALLBACK): {game_state['bombers'][0].get('name')} ({game_state['my_uid']})")
                    me = get_my_bomber()  # Thử lấy lại
            
            # Kiểm tra game có hoạt động không
            game_active = game_state["connected"] and (game_state["game_started"] or os.getenv("ENVIRONMENT", "prod") == "dev")
            
            # Kiểm tra map có sẵn sàng không (tránh lỗi sau khi hồi sinh)
            map_ready = game_state.get("map") and len(game_state.get("map", [])) > 0
            
            if not map_ready and game_active:
                logger.info(f"🗺️ CHỜ MAP: Map chưa sẵn sàng sau khi hồi sinh, tạm dừng AI")
            
            if game_active and me and map_ready:
                # Kiểm tra vị trí bot có hợp lệ không
                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                if not (1 <= current_cell[0] <= 14 and 1 <= current_cell[1] <= 14):
                    logger.warning(f"🚫 BOT Ở VỊ TRÍ KHÔNG HỢP LỆ: {current_cell} - Tạm dừng AI")
                    await asyncio.sleep(period)
                    continue
                
                # Khai báo tất cả biến global cần thiết
                global _arrival_block_until, _last_pos, _stuck_count, _recent_orient, _reverse_block_until
                
                # Nếu vừa tới nơi, tạm không nhận action/fallback để tránh đảo chiều (dwell)
                if time.monotonic() < _arrival_block_until:
                    await asyncio.sleep(period)
                    continue
                
                # BỎ QUA stuck detection để bot luôn có thể di chuyển
                # cur_pos = (me.get("x", 0.0), me.get("y", 0.0))
                # if abs(cur_pos[0] - _last_pos[0]) < 0.1 and abs(cur_pos[1] - _last_pos[1]) < 0.1:
                #     _stuck_count += 1
                #     if _stuck_count >= 20:  
                #         logger.info(f"🚫 STUCK: Bot không di chuyển trong {_stuck_count} tick, tạm dừng movement")
                #         _reset_movement_plan()
                #         _arrival_block_until = time.monotonic() + 0.1
                #         await asyncio.sleep(period)
                #         continue
                # else:
                #     _stuck_count = 0
                # _last_pos = cur_pos
                
                # Check và log khi bot vào ô mới
                movement_logger.check_and_log_cell_arrival()
                
                # Tạm thời loại bỏ border detection vì quá nghiêm ngặt
                # Bot cần được phép di chuyển ra khỏi vùng biên giới
                did_progress = False
                # CHECK DELAY TRƯỚC - Ưu tiên cao nhất!
                if movement_plan.get("just_completed"):
                    completed_time = movement_plan["just_completed"]
                    if time.time() - completed_time < 1.0:  # Skip 1 giây để AI xử lý
                        await asyncio.sleep(period)
                        continue
                    else:
                        # Đã đủ thời gian chờ, xóa flag
                        movement_plan.pop("just_completed", None)
                
                # Ưu tiên tiếp tục plan dài hạn hiện tại
                if movement_plan["path_valid"] and movement_plan["path"]:
                    if movement_plan.get("skip_once"):
                        movement_plan["skip_once"] = False
                    else:
                        _advance_move_plan()
                        current_orient = movement_plan["orient"]
                        if current_orient and current_orient in DIRECTIONS:
                            await _maybe_emit_move(current_orient)
                            # Reset stuck counter khi có movement command
                            _stuck_count = 0
                            did_progress = True
                else:
                    
                    # Không có plan: hỏi AI và lập plan mới
                    action = choose_next_action()
                    
                    # Nếu AI quyết định đứng im quá lâu, thử fallback để thoát khỏi tình trạng bị kẹt
                    if action is None:
                        global _last_ai_idle_time
                        current_time = time.time() * 1000
                        if '_last_ai_idle_time' not in globals():
                            _last_ai_idle_time = current_time
                        
                        idle_duration = current_time - _last_ai_idle_time
                        if idle_duration > 10000:  # 10 giây
                            logger.warning(f"🚨 AI ĐỨNG IM QUÁ LÂU: {idle_duration:.0f}ms")
                            # Bỏ qua việc đánh dấu did_progress để cho phép fallback
                            did_progress = False
                            _last_ai_idle_time = current_time
                        else:
                            _last_ai_idle_time = current_time
                    if action:
                        if action["type"] == "move":
                            # Log vị trí bot hiện tại
                            me = get_my_bomber()
                            if me:
                                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                                logger.info(f"🤖 VỊ TRÍ BOT: ({me.get('x', 0):.1f}, {me.get('y', 0):.1f}) → ô {current_cell}")
                            
                            # Log bản đồ trước khi phân tích plan
                            log_map_state()
                            
                            # Lập plan dài hạn đến mục tiêu
                            goal_cell = action.get("goal_cell")
                            if goal_cell:
                                _plan_long_term_path(goal_cell)
                                # Lấy hướng đầu tiên và gửi ngay
                                direction = _get_next_direction_from_path()
                                if direction:
                                    await _maybe_emit_move(direction)
                            movement_plan["skip_once"] = True
                            _stuck_count = 0
                            did_progress = True
                        elif action["type"] == "bomb":
                            await send_bomb()
                            did_progress = True
                        else:
                            # Fallback: di chuyển 1 ô
                            direction = action["orient"]
                            # Chống đảo chiều
                            if _recent_orient and time.monotonic() < _reverse_block_until:
                                reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                                if direction == reverse.get(_recent_orient):
                                    direction = None
                            if direction:
                                await _maybe_emit_move(direction)
                            _stuck_count = 0
                            did_progress = True
                    else:
                        # Reset plan cũ khi AI quyết định đứng im
                        if movement_plan["path"]:
                            _reset_movement_plan()
                        # KHÔNG đánh dấu did_progress để cho phép fallback
                        did_progress = False
                        
                # FALLBACK LUÔN HOẠT ĐỘNG: Đảm bảo bot luôn có hành động
                if not did_progress:
                    try:
                        # LUÔN thử di chuyển bất kỳ hướng nào để tránh bị kẹt
                        for orient in ["UP", "DOWN", "LEFT", "RIGHT"]:
                            await _maybe_emit_move(orient)
                            # Reset stuck counter khi có fallback movement
                            _stuck_count = 0
                            break
                                
                    except Exception as e:
                        logger.error(f"🤖 FALLBACK ERROR: {e}")
            
            # Flush log di chuyển định kỳ
            movement_logger.flush()
            
            await asyncio.sleep(period)
            
        except asyncio.CancelledError:
            logger.info(f"🤖 Vòng lặp bot bị hủy")
            break
        except Exception as e:
            logger.exception(f"Lỗi vòng lặp bot: {e}")
            await asyncio.sleep(0.1)

# ---------- Startup ----------
async def startup():
    """Khởi tạo kết nối bot và bắt đầu vòng lặp quyết định"""
    # Bắt đầu kết nối trong background
    asyncio.create_task(connect_and_start_bot())

async def connect_and_start_bot():
    """Tác vụ background để xử lý kết nối và vòng lặp bot"""
    # Chờ một chút để event loop sẵn sàng
    await asyncio.sleep(2)
    
    while True:
        try:
            await sio.connect(SOCKET_SERVER, transports=["websocket"], auth={"token": TOKEN})
            break
        except Exception as e:
            logger.error(f"Kết nối thất bại: {e}; thử lại sau 3s")
            await asyncio.sleep(3)
    
    # Bắt đầu vòng lặp bot
    bot_task = asyncio.create_task(bot_loop())
