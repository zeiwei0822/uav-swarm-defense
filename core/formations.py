# -*- coding: utf-8 -*-
"""
要點 1：機群陣型庫與陣型品質分析
=================================
陣型以「領機機體座標系」定義槽位（slot）：
  +x = 領機航向、+y = 航向左側、z = 高度差
slots[0] 永遠是領機槽位 (0,0,0)，其餘槽位由 assign_slots() 指派給從機/中繼機。

中繼機槽位選擇：將非領機槽位做 k-means 分群，取「最接近各群中心」的槽位
—— 中繼機天然位於子群中心，最適合轉發領機訊號（也成為防方 AI 可學習的幾何特徵）。
"""
import numpy as np

FORMATIONS = ["vee", "wedge", "column", "grid", "ring"]
FORMATION_NAMES = {"vee": "V字", "wedge": "楔形", "column": "縱隊",
                   "grid": "方陣", "ring": "環形"}

# 要點1：陣形戰術取捨（都是 trade-off，讓陣形選擇有真實後果）
#   stealth  : 防方接戰距離倍率（<1 = 被咬得晚/近、暴露時間短；>1 = 早被發現）
#   comm     : 通訊半徑倍率（>1 = 連線率高→預警/協調強；<1 = 通訊吃緊）
#   note     : 戰術定位（報告用）
FORMATION_TRAITS = {
    # name      stealth  comm   note
    "vee":     (1.00,   1.05, "增程巡航、左右翼預警均衡"),
    "wedge":   (0.85,   1.15, "集中突穿、低可偵測、通訊緊密"),
    "column":  (0.78,   0.85, "正面最隱蔽、單列突防，但指揮鏈拉長"),
    "grid":    (1.00,   1.10, "均衡方陣、通訊韌性高"),
    "ring":    (1.20,   0.80, "領機居中藏匿(反斬首)，但footprint大、通訊吃緊"),
}


def formation_traits(name):
    """回傳 (stealth, comm_mult, note)"""
    s, c, note = FORMATION_TRAITS.get(name, (1.0, 1.0, ""))
    return s, c, note


# 陣形戰略說明（要點1）——特別點出「領機位置/暴露」這個核心取捨，
# 直接回答「為何這樣排、領機在前是不是送頭」
FORMATION_DOC = {
    "vee": "V字（雁行）：兩翼後掠，可借尾流省油增程；領機在頂端領航、"
           "前方視野最佳。取捨：領機暴露於最前緣，是最容易被優先擊殺的"
           "節點──想保護領機就改用環形。",
    "wedge": "楔形：實心三角集中兵力突穿一點，正面投影小、不易清點識別；"
             "通訊緊密、協調強。領機在前端，仍偏暴露。",
    "column": "縱隊：單列魚貫，正面雷達截面最小、最隱蔽，適合低空滲透。"
              "取捨：指揮鏈被拉成一線、通訊最脆弱，且首機（領機）暴露。",
    "grid": "方陣：均勻散佈、通訊韌性高，能稀釋防空火力（一枚彈殺不到幾架）；"
            "領機在前排中央。中庸而穩健。",
    "ring": "環形護衛：領機居中受外圈層層保護（可反制指揮節點打擊），"
            "各機互為掩護；取捨：footprint 大、暴露面廣、通訊吃緊、轉向較慢。",
}


def formation_doc(name):
    return FORMATION_DOC.get(name, "")


# ---------------------------------------------------------------- 陣型模板
def make_formation(name: str, n: int, spacing: float) -> np.ndarray:
    """產生 n 個槽位（含領機槽位 slots[0]=(0,0,0)），回傳 (n,3)"""
    s = spacing
    slots = [np.zeros(3)]
    k = n - 1  # 非領機槽位數

    if name == "vee":  # V 字：左右兩翼，後掠 30 度
        for i in range(k):
            side = 1 if i % 2 == 0 else -1
            rank = i // 2 + 1
            slots.append(np.array([-rank * s * 0.87, side * rank * s * 0.5, 0.0]))

    elif name == "wedge":  # 楔形：實心三角，逐排填滿
        row, placed = 1, 0
        while placed < k:
            m = row + 1  # 此排機數
            for j in range(m):
                if placed >= k:
                    break
                y = (j - (m - 1) / 2) * s
                slots.append(np.array([-row * s * 0.9, y, 0.0]))
                placed += 1
            row += 1

    elif name == "column":  # 縱隊：n>12 採雙縱隊
        files = 2 if n > 12 else 1
        for i in range(k):
            f = i % files
            rank = i // files + 1
            y = (f - (files - 1) / 2) * s * 1.2
            slots.append(np.array([-rank * s * 0.8, y, 0.0]))

    elif name == "grid":  # 方陣：領機在最前排中央
        cols = int(np.ceil(np.sqrt(n)))
        placed = 0
        idx = 0
        while placed < k:
            row = idx // cols
            col = idx % cols
            idx += 1
            if row == 0 and col == cols // 2:   # 此格保留給領機
                continue
            x = -row * s
            y = (col - (cols - 1) / 2) * s
            slots.append(np.array([x, y, 0.0]))
            placed += 1

    elif name == "ring":  # 環形護衛：領機在圓心（正面性失效 → 凸顯 ML 價值）
        n1 = min(k, 10)               # 內圈最多 10 架
        n2 = k - n1
        for i in range(n1):
            th = 2 * np.pi * i / n1
            slots.append(np.array([np.cos(th), np.sin(th), 0.0]) * s * 1.7)
        for i in range(n2):
            th = 2 * np.pi * (i + 0.5) / max(n2, 1)
            slots.append(np.array([np.cos(th), np.sin(th), 0.0]) * s * 2.9)
    else:
        raise ValueError(f"未知陣型: {name}")

    return np.array(slots)


def pick_relay_slots(slots: np.ndarray, n_relays: int, rng=None) -> list:
    """k-means 分群挑中繼機槽位（回傳槽位索引，不含 0 號領機槽）"""
    rng = rng or np.random.default_rng(0)
    pts = slots[1:]                     # 排除領機
    if len(pts) <= n_relays:
        return list(range(1, len(slots)))
    # 簡易 k-means（n 小，10 次迭代足夠；以最遠點初始化避免退化）
    centers = [pts[np.argmax(np.linalg.norm(pts, axis=1))]]
    for _ in range(n_relays - 1):
        d = np.min([np.linalg.norm(pts - c, axis=1) for c in centers], axis=0)
        centers.append(pts[np.argmax(d)])
    centers = np.array(centers)
    for _ in range(10):
        lab = np.argmin([np.linalg.norm(pts - c, axis=1) for c in centers], axis=0)
        for j in range(n_relays):
            if np.any(lab == j):
                centers[j] = pts[lab == j].mean(axis=0)
    # 每群取最接近群中心的槽位
    chosen = []
    for j in range(n_relays):
        d = np.linalg.norm(pts - centers[j], axis=1)
        order = np.argsort(d)
        for o in order:
            if o + 1 not in chosen:
                chosen.append(o + 1)
                break
    return chosen


# ---------------------------------------------------------------- 座標轉換
def rotation_xy(heading_xy: np.ndarray) -> np.ndarray:
    """由水平航向單位向量建立 3x3 旋轉矩陣（+x 轉到航向）"""
    c, s = heading_xy[0], heading_xy[1]
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def slot_world_positions(leader_pos, heading_xy, slots) -> np.ndarray:
    """槽位轉世界座標 (n,3)"""
    R = rotation_xy(heading_xy)
    return leader_pos[None, :] + slots @ R.T


# ---------------------------------------------------------------- 槽位指派
def assign_slots(drone_pos: np.ndarray, slot_pos: np.ndarray) -> np.ndarray:
    """貪婪最小距離指派：回傳 assignment[i] = 第 i 架無人機的槽位索引。
    drone_pos (m,3) 與 slot_pos (m,3) 數量需相同。
    每次取全域最近的 (機, 槽) 配對 —— 失效重組時可最小化總移動量。"""
    m = len(drone_pos)
    D = np.linalg.norm(drone_pos[:, None, :] - slot_pos[None, :, :], axis=2)
    assignment = np.full(m, -1, dtype=int)
    used_d = np.zeros(m, dtype=bool)
    used_s = np.zeros(m, dtype=bool)
    for _ in range(m):
        Dm = D.copy()
        Dm[used_d, :] = np.inf
        Dm[:, used_s] = np.inf
        i, j = np.unravel_index(np.argmin(Dm), Dm.shape)
        assignment[i] = j
        used_d[i] = True
        used_s[j] = True
    return assignment


# ---------------------------------------------------------------- 陣型品質指標（要點 1 分析用）
def formation_error(drone_pos: np.ndarray, target_pos: np.ndarray) -> float:
    """陣型保持誤差：各機與其指派槽位距離的 RMS (m)"""
    d = np.linalg.norm(drone_pos - target_pos, axis=1)
    return float(np.sqrt(np.mean(d ** 2)))


def spacing_stats(drone_pos: np.ndarray):
    """機間距統計：(最小間距, 平均最近鄰距離)"""
    n = len(drone_pos)
    if n < 2:
        return np.nan, np.nan
    D = np.linalg.norm(drone_pos[:, None, :] - drone_pos[None, :, :], axis=2)
    np.fill_diagonal(D, np.inf)
    nn = D.min(axis=1)
    return float(nn.min()), float(nn.mean())
