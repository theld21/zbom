# PROMPT CHO AI BOMBERMAN — **V4 (Tile-First 16×16, Survival-Only, Socket/DEAP-Friendly)**

> **Mục tiêu tuyệt đối:** SỐNG SÓT. Không ưu tiên giết hay nhặt đồ. Ưu tiên **đứng im** nếu di chuyển làm tăng rủi ro.  
> **Khác biệt so với V3:** Toàn bộ **tìm đường & hazard** chạy **trên lưới 16×16** (tile 40 px), không làm việc ở toạ độ 640×640 ngoại trừ bước xuất lệnh vi mô (px). Hỗ trợ chuẩn hoá log như ví dụ bạn cung cấp (toạ độ bội số 40).

---

## 0) Sự thật nền & đơn vị
- **Map:** 640×640 px; **tile:** 40×40 px ⇒ **lưới 16×16** (chỉ số 0..15).  
- **Thực thể:** Bom 40×40; Tường (W) 40×40 (không phá/không xuyên nổ); Rương (C) 40×40 (phá được, sinh item); Item: `SPEED`, `EXPLOSION_RANGE`, `BOMB_COUNT`.  
- **Bot:** hitbox 35×35; di chuyển **mỗi lệnh = speed px** (1/2/3).  
- **Bom:** nổ sau 5s; **tầm nổ = 2 ô** mặc định (4 hướng), +1/“Liệt hoả”.  
- **Event/socket:** `move{orient}`, `place_bomb{}`; trạng thái cung cấp `map[16][16]` ký hiệu `W/C/B/R/S/null` + danh sách bomb/item.

---

## 1) Chuẩn hoá toạ độ PX → TILE (16×16)
**Mục tiêu:** Mọi quyết định **tìm đường/hazard** đều ở **đơn vị tile**. Chỉ lúc phát lệnh mới quy đổi sang **px**.

### 1.1. Quy ước log
- Log bạn cung cấp có toạ độ (ví dụ `(480, 560)`, `(280, 240)`, v.v.) đều là **bội số của 40** ⇒ rất nhiều khả năng là **gốc trên-trái tile** *(top-left anchor)*.
- **Quy tắc mặc định (an toàn & đơn giản):**
  ```py
  tile_x = clamp(int(x // 40), 0, 15)
  tile_y = clamp(int(y // 40), 0, 15)
  ```
  Dùng cho **bom, rương, item** trong log.  
- Nếu server dùng **tâm tile** (20 + 40*k) cho bot: hãy **cộng offset 20** trước khi chia:
  ```py
  # Khi x,y là tâm (center) của thực thể:
  tile_x = clamp(int((x) // 40), 0, 15)           # nếu center đã là bội 40
  # hoặc tiêu chuẩn hoá tổng quát:
  tile_x = clamp(int((x + 20) // 40), 0, 15)      # nếu x là top-left → +20 để về tâm
  ```

### 1.2. Lệch ô (off-grid) — hiếm nhưng phải chịu được
- **Mặc định**: bom/item **snapped** vào **1 tile**:  
  `anchor_tile = (round((x + 20)/40), round((y + 20)/40))`  *(x,y top-left → +20 về tâm rồi round)*.
- **Fallback an toàn** (nếu bom/item đặt **lệch > 8 px** so với ranh 40 px):
  - Xét **AABB** của bom/item (40×40) chồng lên **1–4 tiles**.
  - **Vật cản/chiếm chỗ**: đánh dấu **mọi tile bị chồng lấn**.  
  - **Nguồn nổ (origin)**: chọn tile có **diện tích chồng lấn lớn nhất**; nếu hoà, chọn tile có tâm **gần (x+20,y+20)** nhất.
- Lý do chọn ngưỡng ~**8 px**: đủ rộng để tránh rung số, vẫn giữ tính nhất quán với lưới 40 px.

---

## 2) Mô hình nội bộ (tile domain)
- `grid[16][16]`: `'W'|'C'|'null'` (+ trạng thái item nếu encode tại grid)  
- `bombs`: `{id → (tx,ty,owner,createdAt,lifeTime,flame,passedThrough(owner))}`  
- `items`: danh sách tile `{(tx,ty,type)}`; nếu off-grid → **snap** theo 1.2.  
- `you`: `(tx,ty,speed,flame,bombs_max,bombs_active,alive,movable)`; nếu nhận (x,y) px → `tx=floor((x)/40)`, `ty=floor((y)/40)` sau khi chuẩn hoá offset đúng như 1.1.
- **Node đi lại**: **chỉ tâm tile** `(tx,ty)` hợp lệ **không phải** `W` và **không bị bom cản** tại thời điểm đi vào.

---

## 3) Hazard theo **tile-time**
1) **Tính t_nổ** mỗi bom: `t_explode = createdAt + lifeTime`.
2) **Ray cast theo 4 hướng** từ `origin_tile` (mục 1.2), **dừng tại W**, **đi qua C** (rương sẽ vỡ).  
3) Lưu vào `hazard[ty][tx]` danh sách **khoảng thời gian** `[t_start, t_end]` (TTL nổ ~300–500 ms nếu server không cung cấp).  
4) **Dây chuyền**: nếu 2 khoảng chồng nhau, **hợp nhất** hoặc **kéo dài**.

**Quy tắc vào tile an toàn:**  
Với ô đích `(tx,ty)`, chỉ coi là an toàn nếu `ETA_to_enter < t_start - Δ` đối với **mọi khoảng** nguy hiểm của ô đó (Δ=80–150 ms).

---

## 4) Tìm đường **16×16** (A*/Dijkstra)
- **Đồ thị**: 4 hướng (UP/DOWN/LEFT/RIGHT).  
- **Chi phí thời gian**: `cost = 1 tile`; ước lượng ETA thực = `cost_tiles * (40 / speed_px_per_cmd) * tick_time`, nhưng **so hazard** theo **thứ tự tile** là đủ (giữ Δ bảo thủ).  
- **Tránh**: nodes có `W`, nodes bị **bom-cản** (bom của người khác & bom của mình sau khi đã rời AABB), nodes có **hazard** trong cửa sổ tới nơi.  
- **Chiến lược “đứng im”**: nếu **không có tile an toàn khả dụng**, **ở lại tile hiện tại** (không gửi `move`); chỉ rời khi có đích thoát **an toàn xác nhận**.

---

## 5) Bridge TILE → PX khi xuất lệnh
- **Waypoint px** của tile `(tx,ty)` = **tâm tile**: `(20 + 40*tx, 20 + 40*ty)`.  
- **Vi mô**: gửi các lệnh `move` theo 1 hướng mỗi tick, **mỗi lệnh = speed px** cho tới khi **đạt tâm tile kế tiếp**, **sau đó mới rẽ** (tránh quệt góc).  
- **Đứng im**: nếu cần idle, **đừng gửi** `move`.

---

## 6) Luật sinh tồn & trường hợp “4 phía bị rương”
- Nếu tile hiện tại bị **bao quanh bởi C/W/bom-cản** ở cả 4 phía và **không** có kế hoạch mở lối **an toàn ngay** sau một hành động (ví dụ đặt bom rồi chắc chắn thoát được) → **đứng im**.  
- **Chỉ đặt bom** khi **đã có** đường thoát **theo tile** tới một **tile an toàn** với `ETA < t_nổ - Δ`.  
- **Không ham item**; **không truy đuổi**.  

---

## 7) Dự báo đối thủ (tile-level)
- Theo dõi `(tx,ty,orient,speed)` của từng đối thủ.  
- **Giả lập 1–2 bước tile** theo `orient` và luật “rẽ tại tâm tile”.  
- **Shadow**: đánh dấu tiles mà đối thủ **có thể đặt bom** để **cắt lối** bạn trong ≤2s; **tránh** đường đi cắt qua shadow nếu tile hiện tại an toàn.  
- Nếu shadow bao trùm các lối, **ưu tiên đứng im** cho đến khi hazard hoặc đối thủ thay đổi.

---

## 8) Đầu ra (socket-friendly)
```jsonc
{
  "commands": [
    // ví dụ: đứng im (không có move)
    // {"event":"move","orient":"UP"},      // chỉ khi có tile đích an toàn
    // {"event":"place_bomb"}               // chỉ khi đã xác minh lối thoát
  ],
  "nav": {
    "tile_path": [[7,6],[7,5],[7,4]],
    "next_tile": [7,5],
    "escape_tile": [7,4]
  },
  "safety": {
    "has_escape": true,
    "hazard_margin_ms": 320
  },
  "tactics": ["idle_safe","tile_a_star","shadow_avoid"]
}
```
- **Giải thích ≤4 gạch đầu dòng**: tại sao an toàn (ví dụ: “ô hiện tại an toàn, 2 láng giềng có hazard ≤1s nên idle”).

---

## 9) Quy tắc chuyển đổi & kiểm tra nhanh (áp dụng cho log thực tế)
- **Bom/Rương/Item từ log**: hầu hết toạ độ là **bội 40** ⇒ dùng `tx=x//40, ty=y//40`.  
- **Bot từ server**: nếu toạ độ là tâm (không bội 40), dùng `tx=floor((x)/40)` **hoặc** thêm offset `+20` theo chuẩn của server trước khi chia (xác nhận 1 lần theo thực nghiệm).  
- **Off-grid hiếm**: dùng **snap theo 1.2**. Nếu `(x % 40) ∈ {0,20} ∧ (y % 40) ∈ {0,20}` ⇒ coi là hợp lệ (top-left/tâm).  
- **Kiểm chứng**: so sánh vị trí chests bị phá trong log (ví dụ `(320,200)`) với **tầm nổ tile** của bom gần nhất; nếu khớp tuyến tính theo 2/3 tiles ⇒ mapping đúng.

---

## 10) Fitness **DEAP** (Survival-only, tile domain)
- **Genome**: trọng số tile-heuristic `w = [w_idle_bias, w_hazard_margin, w_shadow_avoid, w_snap_tolerance_px, w_bomb_place_threshold, ...]`.  
- **Fitness**: `+ survival_time` + `+ avg_hazard_margin` − `self_trap` − `enter_shadow` − `bomb_without_escape`.  
- **Elitism**: giữ cá thể ít tự bẫy nhất.  
- **Replay/Memory**: cập nhật **Bomb Registry** & **Hazard Timeline** theo **tile** mỗi tick; log lại tile-path và quyết định idle để phân tích.

---

## 11) Nguyên tắc không vi phạm
- Không bước vào tile có hazard trong cửa sổ ETA.  
- Không đặt bom nếu chưa có đường thoát tile an toàn.  
- Không rẽ khi chưa tới **tâm tile**.  
- Nếu **mọi** phương án di chuyển đều rủi ro cao hơn **đứng im**, **đứng im**.

---

### Gợi ý kiểm tra một lần với log mẫu của bạn
- Ví dụ `💣 BOM MỚI tại (280, 240)` ⇒ `tx=7, ty=6`. Nếu nổ, rương `(280,200)` và `(200,240)` bị phá trong log → tương ứng tiles `(7,5)` và `(5,6)` khớp tầm nổ **2 ô** theo 4 hướng (dừng ở tường). **Mapping OK**.

**Kết luận mapping:** Với log hiện tại, **có thể & nên** quy đổi **bom/item/rương** sang **16×16** bằng `//40`. Chuẩn bị **fallback off-grid** bằng **snap** và **AABB-overlap** như trên để robust với mọi sai lệch hiếm gặp.
