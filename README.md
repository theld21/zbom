# Bomberman Bot - Zinza Hackathon 2025

Bot AI cho game Bomberman với chiến lược sinh tồn thông minh.

## Cấu trúc dự án (Refactored)

```
zbom/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Entry point chính (FastAPI + Socket.IO)
│   ├── main_refactored.py         # Version refactored (nên dùng)
│   ├── config.py                  # Cấu hình game và hằng số
│   ├── game_state.py              # Quản lý state game (FastGameState với bitmask)
│   ├── socket_handlers.py         # Xử lý socket events
│   ├── survival_ai.py             # AI logic cũ (legacy)
│   ├── ui_config.py               # Config hiển thị
│   │
│   ├── models/                    # Data models
│   │   ├── __init__.py
│   │   ├── action.py              # Action models (ActionType, Action)
│   │   └── position.py            # Position & Cell models
│   │
│   ├── utils/                     # Utilities
│   │   ├── __init__.py
│   │   ├── logger.py              # Logging utilities
│   │   └── movement.py            # Movement planning & execution
│   │
│   └── strategies/                # AI Strategies
│       ├── __init__.py
│       ├── base.py                # Base strategy class
│       ├── survival.py            # Survival strategy (refactored)
│       └── helpers/               # Helper modules
│           ├── __init__.py
│           ├── danger.py          # Danger detection
│           ├── navigation.py     # Navigation helpers
│           ├── bombing.py         # Bombing logic
│           └── scoring.py         # Move scoring
│
├── spec/                          # Tài liệu
│   ├── Bomberman_Tile16_Survival_Prompt_V4.md
│   └── z-bom-rules.txt
│
├── run_bot.py                     # Script chạy bot
├── requirements.txt               # Dependencies
├── Dockerfile                     # Docker config
├── docker-compose.yml             # Docker Compose
├── optimized_strategy.json        # Strategy params
└── README.md                      # File này
```

## Các module chính

### 1. Models (`app/models/`)

Data models cho bot:

- **action.py**: `Action`, `ActionType` - Models cho các hành động
- **position.py**: `Position`, `Cell` - Models cho vị trí và ô lưới

### 2. Utils (`app/utils/`)

Các utility functions:

- **logger.py**: `MovementLogger`, `log_map_state()` - Logging utilities
- **movement.py**: `MovementPlanner` - Quản lý kế hoạch di chuyển dài hạn

### 3. Strategies (`app/strategies/`)

AI strategies và helpers:

- **base.py**: `BaseStrategy` - Abstract base class
- **survival.py**: `SurvivalStrategy` - Chiến lược sinh tồn chính
- **helpers/**: Các helper modules
  - **danger.py**: `DangerDetector` - Phát hiện nguy hiểm
  - **navigation.py**: `NavigationHelper` - Navigation và pathfinding
  - **bombing.py**: `BombingHelper` - Logic đặt bom
  - **scoring.py**: `ScoringHelper` - Đánh giá nước đi

### 4. Core (`app/`)

- **main.py**: FastAPI app, Socket.IO handlers, bot loop
- **config.py**: Cấu hình game (CELL_SIZE, TICK_HZ, etc.)
- **game_state.py**: State management, FastGameState (bitmask), A\*/BFS pathfinding
- **socket_handlers.py**: Xử lý tất cả socket events
- **survival_ai.py**: AI logic cũ (legacy, để backward compatibility)

## Cải tiến sau refactoring

### ✅ Tổ chức code tốt hơn

- Tách logic thành các module nhỏ, rõ ràng theo chức năng
- Dễ tìm và sửa lỗi hơn
- Dễ mở rộng và phát triển thêm tính năng

### ✅ Separation of Concerns

- Models: Data structures
- Utils: Helper functions
- Strategies: AI logic
- Core: Infrastructure

### ✅ Reusability

- Các helper class có thể tái sử dụng
- Dễ dàng tạo strategies mới kế thừa từ `BaseStrategy`

### ✅ Maintainability

- Code ngắn gọn hơn trong mỗi file
- Comments và docstrings rõ ràng
- Dễ test từng module riêng biệt

## Cách sử dụng

### Chạy bot (Development)

```bash
python run_bot.py
```

### Chạy với Docker

```bash
docker-compose up --build
```

### Config

Tạo file `.env` từ `.env.example`:

```env
SOCKET_SERVER=http://localhost:3000
TOKEN=your_token_here
BOT_NAME=YourBotName
```

## Luồng hoạt động

1. **Startup**: `run_bot.py` → `main.py` → khởi động FastAPI + Socket.IO
2. **Connect**: Kết nối đến server game
3. **Game Loop**:
   - Nhận events từ server (map_update, new_bomb, etc.)
   - AI (SurvivalStrategy) phân tích và chọn action
   - MovementPlanner lập kế hoạch di chuyển
   - Gửi commands (move/bomb) đến server
4. **Helpers**: DangerDetector, NavigationHelper, BombingHelper hỗ trợ AI

## API Endpoints

- `GET /healthz`: Health check
- `GET /state`: Lấy trạng thái game hiện tại

## Phát triển tiếp

### Thêm strategy mới

```python
from app.strategies.base import BaseStrategy

class AggressiveStrategy(BaseStrategy):
    def choose_next_action(self):
        # Your logic here
        pass

    def reset_state(self):
        # Reset logic
        pass
```

### Thêm helper mới

```python
# app/strategies/helpers/your_helper.py
class YourHelper:
    @staticmethod
    def your_method():
        # Your logic
        pass
```

## Testing

```bash
# TODO: Thêm unit tests
pytest tests/
```

## Notes

- File `main_refactored.py` là version refactored, nên dùng thay cho `main.py` cũ
- File `survival_ai.py` vẫn giữ nguyên để backward compatibility
- Các helper classes được tối ưu cho performance và reusability

## Contributors

Zinza Hackathon Team 2025
