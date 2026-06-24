# -*- coding: utf-8 -*-
"""
3D 實體模型與戰場地形
======================
· drone_template / missile_template：低多邊形機體模板（機體座標系 +x前 +y左 +z上）
· transform_meshes：依位置/航向/俯仰批次旋轉平移（向量化，控動畫效能）
· build_strait_terrain：台灣海峽戰場地形（海面、對岸大陸、台灣島、中央山脈、中線）
"""
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection


# ================================================================ 機體模板
def drone_template():
    """固定翼無人機低多邊形模板（單位尺度，機頭朝 +x）。
    回傳 (F,3,3) 三角面陣列。"""
    f = []
    # 主翼（後掠箭形，水平面）
    f += [[(0.25, 0, 0), (-0.55, 0.95, 0), (-0.42, 0, 0)]]   # 左翼
    f += [[(0.25, 0, 0), (-0.55, -0.95, 0), (-0.42, 0, 0)]]  # 右翼
    # 機身（細長三稜，給高度感）
    nose = (1.15, 0, 0.02)
    tail = (-0.78, 0, 0.05)
    top = (0.05, 0, 0.13)
    bl = (0.05, 0.10, -0.02)
    br = (0.05, -0.10, -0.02)
    f += [[nose, top, bl], [nose, br, top]]          # 前段上左/上右
    f += [[tail, bl, top], [tail, top, br]]          # 後段上左/上右
    f += [[nose, bl, br]]                             # 機腹前
    f += [[tail, br, bl]]                             # 機腹後
    # 垂直尾翼（xz 平面）
    f += [[(-0.45, 0, 0.04), (-0.82, 0, 0.42), (-0.82, 0, 0.04)]]
    # 水平尾翼
    f += [[(-0.55, 0, 0), (-0.85, 0.34, 0), (-0.85, -0.34, 0)]]
    return np.array(f, dtype=float)


def missile_template():
    """攔截彈模板（細長彈體 + 尾翼，彈頭朝 +x）。回傳 (F,3,3)。"""
    f = []
    nose = (1.3, 0, 0)
    r = 0.12
    # 彈體環（後段四點）
    ring = [(-0.9, r, 0), (-0.9, 0, r), (-0.9, -r, 0), (-0.9, 0, -r)]
    mid = [(0.5, r, 0), (0.5, 0, r), (0.5, -r, 0), (0.5, 0, -r)]
    for i in range(4):
        j = (i + 1) % 4
        f += [[nose, mid[i], mid[j]]]                # 頭錐
        f += [[mid[i], ring[i], ring[j]]]            # 彈體側
        f += [[mid[i], ring[j], mid[j]]]
    # 尾翼（4 片）
    for s in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        f += [[(-0.7, 0, 0), (-1.05, 0.34 * s[0], 0.34 * s[1]),
               (-1.05, 0.14 * s[0], 0.14 * s[1])]]
    return np.array(f, dtype=float)


def missile_flame_template():
    """尾焰（彈尾橙色錐）。"""
    base = [(-0.9, 0.1, 0), (-0.9, 0, 0.1), (-0.9, -0.1, 0), (-0.9, 0, -0.1)]
    tip = (-1.7, 0, 0)
    f = [[tip, base[i], base[(i + 1) % 4]] for i in range(4)]
    return np.array(f, dtype=float)


# ================================================================ 批次變換
def _rot(yaw, pitch):
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    return Rz @ Ry


def transform_meshes(template, positions, yaws, pitches, scale):
    """把模板套到多個實體上，回傳合併後的 (M*F,3,3) 世界座標面。
    template:(F,3,3)  positions:(M,3)  yaws,pitches:(M,)
    scale 可為純量或 (M,) 陣列（領機放大用）。"""
    F = len(template)
    M = len(positions)
    if M == 0:
        return np.empty((0, 3, 3))
    base = template.reshape(-1, 3)                    # (F*3,3)
    sc = (np.full(M, scale, float) if np.isscalar(scale)
          else np.asarray(scale, float))
    out = np.empty((M, F * 3, 3))
    for m in range(M):
        R = _rot(yaws[m], pitches[m])
        out[m] = (base * sc[m]) @ R.T + positions[m]
    return out.reshape(M * F, 3, 3)


def heading_angles(vel):
    """由速度向量算 (yaw, pitch)。vel:(M,3) → yaws,(M,) pitches,(M,)"""
    yaw = np.arctan2(vel[:, 1], vel[:, 0])
    horiz = np.linalg.norm(vel[:, :2], axis=1)
    pitch = np.arctan2(vel[:, 2], horiz + 1e-9)
    return yaw, pitch


# ================================================================ 海峽地形
# 台灣島輪廓（正規化，北=+y，西岸=-x 面對海峽）
_TAIWAN = np.array([
    (0.10, 1.00), (0.35, 0.80), (0.50, 0.35), (0.48, -0.10),
    (0.38, -0.55), (0.18, -0.92), (0.00, -1.00), (-0.22, -0.78),
    (-0.45, -0.30), (-0.55, 0.15), (-0.42, 0.55), (-0.18, 0.85)])


def _fan(poly2d, z=1.0):
    """凸多邊形扇形三角化 → (F,3,3)"""
    p = np.column_stack([poly2d, np.full(len(poly2d), z)])
    return np.array([[p[0], p[i], p[i + 1]]
                     for i in range(1, len(p) - 1)])


def build_strait_terrain(target, x_range, y_range):
    """建立台灣海峽戰場地形，回傳 (artists, labels)。
    labels = [(x,y,z,文字,顏色), ...] 供 ax.text 標註。
    target 在台灣島上（東）；對岸大陸在西。"""
    artists = []
    x0, x1 = x_range
    y0, y1 = y_range
    ys = np.linspace(y0, y1, 40)

    # --- 海面（半透明深藍大平面）
    sea = np.array([[(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)]])
    sea_c = Poly3DCollection(sea, facecolor="#0a2540", alpha=0.55,
                             edgecolor="none", zsort="min")
    artists.append(("sea", sea_c))

    # --- 對岸大陸（西，含起伏海岸線）
    coast_x = -2800 + 70 * np.sin(ys / 320) + 25 * np.sin(ys / 90)
    land_pts = [(cx, y, 2) for cx, y in zip(coast_x, ys)]
    land_pts += [(x0, y1, 2), (x0, y0, 2)]
    mainland = _poly_to_tris(land_pts, z=2)
    ml_c = Poly3DCollection(mainland, facecolor="#2d3b30", alpha=0.92,
                            edgecolor="#3f5142", linewidths=0.5)
    artists.append(("mainland", ml_c))
    # 對岸山脈脊線
    ridge = Line3DCollection(
        [[(coast_x[i] - 120, ys[i], 14), (coast_x[i] - 120, ys[i] + 30, 14)]
         for i in range(0, len(ys) - 1, 3)],
        colors="#4a5d4a", linewidths=2.0, alpha=0.7)
    artists.append(("mainland_ridge", ridge))

    # --- 台灣島（東，番薯形）
    tw = _TAIWAN.copy()
    tw[:, 0] = tw[:, 0] * 260 + (target[0] + 150)
    tw[:, 1] = tw[:, 1] * 560 + target[1]
    island = _poly_to_tris([(x, y, 2) for x, y in tw], z=2)
    isl_c = Poly3DCollection(island, facecolor="#3a4a2a", alpha=0.95,
                             edgecolor="#5a7038", linewidths=0.8)
    artists.append(("taiwan", isl_c))
    # 中央山脈（南北脊線，抬高）
    spine = []
    cy = np.linspace(-0.85, 0.92, 14)
    for c in cy:
        sx = (target[0] + 150) + 30 * np.sin(c * 2)
        spine.append((sx, target[1] + c * 540, 18))
    artists.append(("spine", Line3DCollection(
        [[spine[i], spine[i + 1]] for i in range(len(spine) - 1)],
        colors="#6b7f3a", linewidths=3.0, alpha=0.85)))

    # --- 海峽中線
    midx = (-2800 + (target[0] + 7)) / 2
    artists.append(("midline", Line3DCollection(
        [[(midx, y0, 3), (midx, y1, 3)]],
        colors="#5a6b7a", linewidths=1.3, alpha=0.6, linestyles="--")))

    labels = [
        (-3000, 0, 95, "中國大陸（攻方起飛）", "#9db89d"),
        (target[0] + 170, target[1] + 640, 95, "台灣", "#9cc46a"),
        (midx, y1 - 120, 70, "海峽中線", "#8aa0b5"),
    ]
    return artists, labels


def _poly_to_tris(pts3d, z=0.0):
    """一般多邊形（可凹）→ 三角面，用質心扇形（近似，地形用足夠）。"""
    p = np.array([(x, y, zz) for x, y, zz in
                  [(a[0], a[1], a[2] if len(a) > 2 else z) for a in pts3d]])
    c = p.mean(axis=0)
    return np.array([[c, p[i], p[(i + 1) % len(p)]] for i in range(len(p))])
