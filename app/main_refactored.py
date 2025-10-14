#!/usr/bin/env python3
"""
Bot Bomberman - Zinza Hackathon 2025 (Refactored)
Bot AI với chiến lược sinh tồn - Version refactored với cấu trúc tốt hơn
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

# Import các module đã refactor
from .utils.logger import MovementLogger, log_map_state
from .utils.movement import MovementPlanner, movement_plan
from .strategies.survival import survival_ai

# Import các module cần thiết
from aiolimiter import AsyncLimiter
from fastapi import FastAPI
import socketio

# Import config và game state
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
from .socket_handlers import (
    handle_connect, handle_disconnect, handle_user, handle_start, 
    handle_finish, handle_player_move, handle_new_bomb, 
    handle_bomb_explode, handle_map_update, handle_item_collected,
    handle_chest_destroyed, handle_new_enemy, handle_user_die_update,
    handle_user_disconnect, handle_new_life
)

# Setup logging
logger = logging.getLogger("bot")

# Giới hạn tốc độ gửi lệnh
cmd_limiter = AsyncLimiter(max_rate=MAX_CMDS_PER_SEC, time_period=1)

# Movement logger instance
movement_logger = MovementLogger()

# Khởi tạo Socket.IO client
sio = socketio.AsyncClient(
    reconnection=True, 
    reconnection_attempts=0, 
    logger=False, 
    engineio_logger=False
)

# ---------- Global variables cho movement ----------
_last_move_emit_time: float = 0.0
_recent_orient: str | None = None
_reverse_block_until: float = 0.0
_arrival_block_until: float = 0.0
_last_pos: tuple = (0.0, 0.0)
_stuck_count: int = 0
_oscillation_detector: list = []


def _ack_logger(event_name: str):
    """Helper để log acknowledgements"""
    def _cb(res=None):
        try:
            logger.info(f"ACK {event_name}: {res}")
        except Exception:
            pass
    return _cb


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
    """Kiểm tra có thể gửi lệnh move không"""
    global _last_move_emit_time
    min_interval = 1.0 / max(1.0, MAX_CMDS_PER_SEC)
    now = time.monotonic()
    return (now - _last_move_emit_time) >= min_interval


async def _maybe_emit_move(orient: str):
    """Gửi lệnh move nếu đủ điều kiện"""
    global _last_move_emit_time, _recent_orient
    if not _can_emit_move_now():
        return
    await send_move(orient)
    _last_move_emit_time = time.monotonic()
    _recent_orient = orient


def reset_global_state() -> None:
    """Reset toàn bộ global state"""
    global _last_move_emit_time, _recent_orient, _reverse_block_until, _arrival_block_until
    global _last_pos, _stuck_count, _oscillation_detector
    
    _last_move_emit_time = 0.0
    _recent_orient = None
    _reverse_block_until = 0.0
    _arrival_block_until = 0.0
    _last_pos = (0.0, 0.0)
    _stuck_count = 0
    _oscillation_detector = []
    
    MovementPlanner.reset()
    movement_logger.current_direction = None
    
    logger.info("🔄 GLOBAL RESET: Đã reset toàn bộ global state")


# Expose _reset_movement_plan cho backward compatibility
def _reset_movement_plan():
    """Reset movement plan (backward compatibility)"""
    MovementPlanner.reset()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời FastAPI"""
    try:
        level = getattr(logging, LOG_LEVEL, logging.INFO)
        logging.basicConfig(level=level)
        logger.setLevel(level)
    except Exception:
        pass
    
    logger.info("🚀 Khởi động bot...")
    try:
        await startup()
        logger.info("🚀 Bot đã sẵn sàng")
    except Exception as e:
        logger.error(f"🚀 Lỗi khởi động: {e}")
    
    yield
    
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
    """Gửi lệnh di chuyển"""
    if orient not in DIRECTIONS:
        return
    if not can_send_command():
        logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Quá giới hạn tốc độ")
        return
    
    if not game_state.get("game_started", False):
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            pass  # Dev mode
        else:
            logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Game chưa bắt đầu")
            return
    
    try:
        async with cmd_limiter:
            await sio.emit("move", {"orient": orient}, callback=_ack_logger("move"))
        movement_logger.log_movement(orient, LOG_MOVEMENT)
    except Exception as e:
        logger.error(f"❌ Lỗi di chuyển: {e}")


async def send_bomb():
    """Gửi lệnh đặt bom"""
    if not can_send_command():
        logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Quá giới hạn tốc độ")
        return
    
    me = get_my_bomber()
    if me and not me.get("movable", True):
        logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Bot không thể di chuyển")
        return
    
    if not game_state.get("game_started", False):
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            logger.info(f"💣 CHẾ ĐỘ DEV: Cho phép đặt bom")
        else:
            logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Game chưa bắt đầu")
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


async def bot_loop():
    """Vòng lặp quyết định chính của bot"""
    logger.info(f"🤖 Bắt đầu vòng lặp bot với TICK_HZ={TICK_HZ}")
    await asyncio.sleep(0.2)
    
    period = 1.0 / max(TICK_HZ, 1.0)
    
    while True:
        start_time = time.time()
        try:
            # Kiểm tra trạng thái bot
            me = get_my_bomber()
            if not me:
                available_bombers = [b.get('name') for b in game_state.get('bombers', [])]
                logger.warning(f"🤖 Không tìm thấy bot! Có sẵn: {available_bombers}")
                
                if available_bombers:
                    logger.info("🔄 Thử tìm lại bot...")
                    game_state["my_uid"] = None
                    mine = next((b for b in game_state.get("bombers", [])
                                if isinstance(b.get("name"), str) and b["name"].lower() == BOT_NAME.lower()), None)
                    if mine:
                        game_state["my_uid"] = mine.get("uid")
                        logger.info(f"🤖 CHỌN LẠI BOT: {mine.get('name')}")
                    else:
                        uids = [b.get("uid") for b in game_state.get("bombers", [])]
                        if uids:
                            game_state["my_uid"] = game_state["bombers"][0].get("uid")
                    me = get_my_bomber()
            
            # Kiểm tra game active
            game_active = game_state["connected"] and (game_state["game_started"] or os.getenv("ENVIRONMENT", "prod") == "dev")
            map_ready = game_state.get("map") and len(game_state.get("map", [])) > 0
            
            if not map_ready and game_active:
                logger.info(f"🗺️ CHỜ MAP: Map chưa sẵn sàng")
            
            if game_active and me and map_ready:
                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                if not (1 <= current_cell[0] <= 14 and 1 <= current_cell[1] <= 14):
                    logger.warning(f"🚫 BOT Ở VỊ TRÍ KHÔNG HỢP LỆ: {current_cell}")
                    await asyncio.sleep(period)
                    continue
                
                global _arrival_block_until
                if time.monotonic() < _arrival_block_until:
                    await asyncio.sleep(period)
                    continue
                
                did_progress = False
                
                # Ưu tiên plan hiện tại
                if movement_plan["path_valid"] and movement_plan["path"]:
                    if movement_plan.get("skip_once"):
                        movement_plan["skip_once"] = False
                    else:
                        current_orient = MovementPlanner.advance_move_plan()
                        if current_orient and current_orient in DIRECTIONS:
                            await _maybe_emit_move(current_orient)
                    did_progress = True
                else:
                    # Không có plan: hỏi AI
                    action = survival_ai.choose_next_action()
                    
                    if action:
                        if action["type"] == "move":
                            me = get_my_bomber()
                            if me:
                                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                                logger.info(f"🤖 VỊ TRÍ BOT: ({me.get('x', 0):.1f}, {me.get('y', 0):.1f}) → ô {current_cell}")
                            
                            log_map_state()
                            
                            goal_cell = action.get("goal_cell")
                            if goal_cell:
                                MovementPlanner.plan_long_term_path(goal_cell)
                                direction = MovementPlanner.get_next_direction()
                                if direction:
                                    await _maybe_emit_move(direction)
                            movement_plan["skip_once"] = True
                            did_progress = True
                        elif action["type"] == "bomb":
                            await send_bomb()
                            did_progress = True
                        else:
                            direction = action.get("orient")
                            if direction and direction in DIRECTIONS:
                                await _maybe_emit_move(direction)
                            did_progress = True
                    else:
                        if movement_plan["path"]:
                            MovementPlanner.reset()
                        did_progress = False
                
                # Fallback
                if not did_progress:
                    try:
                        for orient in ["UP", "DOWN", "LEFT", "RIGHT"]:
                            await _maybe_emit_move(orient)
                            break
                    except Exception as e:
                        logger.error(f"🤖 FALLBACK ERROR: {e}")
            
            movement_logger.flush()
            await asyncio.sleep(period)
            
        except asyncio.CancelledError:
            logger.info(f"🤖 Vòng lặp bot bị hủy")
            break
        except Exception as e:
            logger.exception(f"Lỗi vòng lặp bot: {e}")
            await asyncio.sleep(0.1)


async def startup():
    """Khởi tạo kết nối bot"""
    asyncio.create_task(connect_and_start_bot())


async def connect_and_start_bot():
    """Kết nối và bắt đầu bot"""
    await asyncio.sleep(2)
    
    while True:
        try:
            await sio.connect(SOCKET_SERVER, transports=["websocket"], auth={"token": TOKEN})
            break
        except Exception as e:
            logger.error(f"Kết nối thất bại: {e}; thử lại sau 3s")
            await asyncio.sleep(3)
    
    bot_task = asyncio.create_task(bot_loop())
