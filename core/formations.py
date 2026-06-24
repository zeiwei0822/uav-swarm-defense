# -*- coding: utf-8 -*-
"""
要點 1：機群陣型庫（依真實無人機群作戰準則）
==============================================
兩大通訊／戰術流派（trade-off 真實化）：

  🛰️ 無線大群 (wireless)  ── 數十～數百架、靠無線電組網。
      有明確指揮鏈(C2) → 可被「斬首」癱瘓；常帶電子干擾(EW)壓制防空。
      ├ echelon      寬幅梯次橫隊：2-3 條平行橫列、飽和正面
      ├ arrowhead    重疊錐形    ：尖端反輻射機破口、兩翼斜散、失效動態遞補
      └ encircle     向心多弧包圍：多方位向心、同時到達(ToT)

  🔗 光纖精準群 (fiber)  ── 3～8 架、實體光纖鏈路。
      免疫電子干擾、且「領機被打掉、後機照航線續突」→ AI 斬首的剋星。
      ├ snake        一字蛇形    ：單列、後機複製前機數秒前航跡
      ├ vstack       垂直梯次階梯：高度分層(5/30/60m)→2D 以水平錯位呈現
      ├ relay_island 母子跳島    ：母機前出變中繼、子機接力、射程加倍
      └ fan          扇形向心    ：各機固定夾角直線進襲、互不交叉

陣型以「領機機體座標系」定義槽位（slot）：
  +x = 領機航向、+y = 航向左側、z = 高度差（本 2D 模型多取 0）
slots[0] 永遠是領機槽位 (0,0,0)。
"""
import numpy as np

# ---------------------------------------------------------------- 陣型清單與分流派
FORMATIONS = ["echelon", "arrowhead", "encircle",        # 無線大群
              "snake", "vstack", "relay_island", "fan"]   # 光纖精準群

FORMATION_NAMES = {
    "echelon": "寬幅梯次橫隊", "arrowhead": "重疊錐形", "encircle": "向心多弧包圍",
    "snake": "一字蛇形", "vstack": "垂直梯次階梯",
    "relay_island": "母子跳島", "fan": "扇形向心",
}

PARADIGM = {
    "echelon": "wireless", "arrowhead": "wireless", "encircle": "wireless",
    "snake": "fiber", "vstack": "fiber", "relay_island": "fiber", "fan": "fiber",
}
PARADIGM_NAMES = {"wireless": "無線大群", "fiber": "光纖精準群"}

# 各流派的合理規模（app/demo 取用；無線大群、光纖少量）
FORMATION_NDEFAULT = {
    "echelon": 22, "arrowhead": 20, "encircle": 24,
    "snake": 6, "vstack": 5, "relay_island": 7, "fan": 6,
}
FORMATION_RELAYS = {           # 預設中繼機數
    "echelon": 3, "arrowhead": 3, "encircle": 4,
    "snake": 1, "vstack": 1, "relay_island": 2, "fan": 1,
}


def formation_paradigm(name):
    return PARADIGM.get(name, "wireless")


def is_fiber(name):
    """光纖精準群：免疫電子干擾、且抗斬首（領機亡、後機照航線續突）。"""
    return PARADIGM.get(name) == "fiber"


# ---------------------------------------------------------------- 戰術取捨
#   stealth : 防方接戰距離倍率（<1 = 被咬得晚/近、暴露短；>1 = 早被發現）
#   comm    : 通訊半徑倍率（>1 = 連線率高→預警/協調強；<1 = 通訊吃緊）
#   ew      : 電子干擾對防空接戰距離的壓制倍率（<1 = 防空更晚才能接戰）
#   note    : 戰術定位（報告用）
FORMATION_TRAITS = {
    # name           stealth comm   note
    "echelon":      (1.05,  0.90, "寬正面飽和、以量取勝；電戰層壓制防空"),
    "arrowhead":    (0.82,  1.15, "尖端反輻射破口、集中突穿、失效動態遞補"),
    "encircle":     (1.10,  0.80, "多方位向心、同時到達(ToT)逼防空分身乏術"),
    "snake":        (0.68,  1.30, "單列最小正面、後機沿前機航跡、抗斬首"),
    "vstack":       (0.82,  1.30, "多角度同時打擊、無正面縱深、抗干擾"),
    "relay_island": (0.74,  1.30, "光纖接力跳島、射程加倍、低空隱蔽"),
    "fan":          (0.98,  1.30, "固定夾角直線進襲、逼防空大角度甩轉"),
}
# 電子干擾壓制（僅無線大群帶 EW 載荷；光纖群不帶 EW，但免疫被干擾）
# 取輕度壓制：足以敘事(−8~12%)，又不至於讓防空太晚接戰而抹平 AI 斬首的價值。
FORMATION_EW = {
    "echelon": 0.88, "arrowhead": 0.92, "encircle": 0.92,
    "snake": 1.0, "vstack": 1.0, "relay_island": 1.0, "fan": 1.0,
}


def formation_traits(name):
    """回傳 (stealth, comm_mult, note)"""
    s, c, note = FORMATION_TRAITS.get(name, (1.0, 1.0, ""))
    return s, c, note


def formation_ew(name):
    """電子干擾對防空接戰距離的壓制倍率（<1 = 防空更晚接戰）"""
    return FORMATION_EW.get(name, 1.0)


# ---------------------------------------------------------------- 陣型說明（要點1，作戰簡報用）
FORMATION_DOC = {
    "echelon": "寬幅梯次橫隊（無線大群）：前排是可拋棄的誘餌／反輻射機、拉出數公里寬"
               "正面癱瘓防空判讀並壓制雷達；指揮領機藏在中排、被左右護衛包住。取捨："
               "傳統打最近只能清掉前排誘餌、傷不到中央指揮——但 AI 靠網路中心性"
               "仍揪得出居中領機並斬首。",
    "arrowhead": "重疊錐形（無線大群）：尖端由可拋棄的反輻射機撕開雷達破口、兩翼斜散層層"
                 "疊進；真正的指揮領機藏在本體基點（兩臂交會處），正面最難打到。取捨："
                 "傳統打不到藏在後方的指揮核心，AI 靠中介中心性才認得出、斬首即潰。",
    "encircle": "向心多弧包圍（無線大群）：弧臂從多方位向心壓迫、以 Time-on-Target 讓各股"
                "「同一秒」到達；指揮領機居弧心、被弧臂環抱保護。取捨：協同極依賴指揮，"
                "傳統打外圍弧臂、難及弧心，AI 斬中心指揮即打亂 ToT 時序。",
    "snake": "一字蛇形（光纖精準群）：單列魚貫、20-50m 間距，僅領機規劃航線，後機自駕"
             "複製「前機數秒前的航跡」。正面雷達截面最小、光纖免疫干擾；關鍵：領機被"
             "打掉，後機仍沿既有航跡續突──這是 AI 斬首(要點4)的死穴。",
    "vstack": "垂直梯次階梯（光纖精準群）：以高度分層(5/30/60m，本 2D 以水平錯位呈現)"
              "達成多角度同時打擊、幾乎無正面縱深。光纖鏈路抗風抗干擾；少量精準、"
              "斬首單機不影響其他層。",
    "relay_island": "母子跳島／鏈條（光纖精準群）：母機帶 5-10km 光纖前出、降落屋頂林梢"
                    "化為中繼站，子機再接力前出，射程加倍。鏈式接力＋光纖 → 抗干擾、"
                    "去單點化，斬首任一節點難以全斷。",
    "fan": "扇形向心（光纖精準群）：各機以 45-90° 固定夾角、純直線向目標進襲、互不交叉，"
           "逼 CIWS／雷射在極短時間內大角度甩轉。無單一行為突出的領機、又抗斬首 → "
           "對行為式識別最棘手。",
}


def formation_doc(name):
    return FORMATION_DOC.get(name, "")


# ---------------------------------------------------------------- 陣型模板
def make_formation(name: str, n: int, spacing: float) -> np.ndarray:
    """產生 n 個槽位（含領機槽位 slots[0]=(0,0,0)），回傳 (n,3)"""
    s = spacing
    slots = [np.zeros(3)]
    k = n - 1  # 非領機槽位數

    if name == "echelon":          # 寬幅梯次橫隊：前排(+x)可拋棄誘餌、領機居中排被包
        per = int(np.ceil(k / 3))
        for i in range(k):
            r = i // per                       # 0=前排(誘餌) 1=中排(領機列) 2=後排
            c = i % per
            x = (1 - min(r, 2)) * s * 1.5       # 前 +1.5s / 中 0 / 後 -1.5s
            y = (c - (per - 1) / 2) * s * 1.3
            if r == 1 and abs(y) < s * 0.6:     # 中排空出中央給領機（被左右護衛包住）
                y += s * 1.3
            slots.append(np.array([x, y, 0.0]))

    elif name == "arrowhead":      # 重疊錐形：尖端反輻射機在前(+x,可拋棄)、領機在本體基點被包
        for i in range(k):
            side = 1 if i % 2 == 0 else -1
            rank = i // 2 + 1
            x = rank * s * 0.62                 # 朝前(+x)張成箭頭；領機在後基點(兩臂交會=高中心性)
            y = side * rank * s * 0.5
            slots.append(np.array([x, y, 0.0]))

    elif name == "encircle":       # 向心多弧包圍：弧臂在前(+x)環抱、領機居弧心被保護
        for i in range(k):
            frac = (i + 1) / (k + 1)
            ang = (frac - 0.5) * np.deg2rad(200.0)        # 寬達 ±100°
            R = s * 2.7
            x = np.cos(ang) * R * 0.5                      # 弧面朝前、領機在弧心後方被環抱
            y = np.sin(ang) * R
            slots.append(np.array([x, y, 0.0]))

    elif name == "snake":          # 一字蛇形：單列縱隊
        for i in range(k):
            slots.append(np.array([-(i + 1) * s * 1.15, 0.0, 0.0]))

    elif name == "vstack":         # 垂直梯次階梯：高度分層 → 水平階梯錯位
        for i in range(k):
            step = i + 1
            x = -step * s * 0.45                            # 幾乎無正面縱深
            y = step * s * 0.62                             # 一致對角階梯
            slots.append(np.array([x, y, 0.0]))

    elif name == "relay_island":   # 母子跳島：拉長的鏈條、微 zigzag
        for i in range(k):
            x = -(i + 1) * s * 1.4
            y = (s * 0.45 if i % 2 else -s * 0.45)
            slots.append(np.array([x, y, 0.0]))

    elif name == "fan":            # 扇形向心：寬扇面、各自直線進襲
        for i in range(k):
            frac = (i + 1) / (k + 1)
            ang = (frac - 0.5) * np.deg2rad(150.0)         # ±75°
            R = s * 2.3
            x = -np.cos(ang) * R * 0.35                     # 在領機後方扇開
            y = np.sin(ang) * R
            slots.append(np.array([x, y, 0.0]))
    else:
        raise ValueError(f"未知陣型: {name}")

    return np.array(slots)


def pick_relay_slots(slots: np.ndarray, n_relays: int, rng=None) -> list:
    """k-means 分群挑中繼機槽位（回傳槽位索引，不含 0 號領機槽）"""
    rng = rng or np.random.default_rng(0)
    n_relays = max(0, int(n_relays))
    pts = slots[1:]                     # 排除領機
    if n_relays == 0 or len(pts) == 0:
        return []
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
