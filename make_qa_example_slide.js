// make_qa_example_slide.js — 實際問答示範（2 組對話，聊天氣泡格式）
const pptxgen = require("pptxgenjs");
const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_qa_example_slide.pptx`;

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";

  const BG    = "0A0E14";
  const PANEL = "111820";
  const PNL2  = "0d1a28";
  const FG    = "E6EDF3";
  const MUTED = "8AA0B5";
  const GOLD  = "FFD700";
  const CYAN  = "00E5FF";
  const GREEN = "39D353";
  const ORANGE= "FF9900";

  const s = pres.addSlide();
  s.background = { color: BG };

  // Header
  s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
    fill:{color:GOLD}, line:{color:GOLD} });
  s.addText("AI", { x:0.25,y:0.12,w:0.48,h:0.48,
    fontSize:14, bold:true, color:BG,
    fontFace:"Calibri", align:"center", valign:"middle", margin:0 });
  s.addText("實際問答示範 | 我問了什麼？AI 回答了什麼？", {
    x:0.84, y:0.10, w:8.92, h:0.52,
    fontSize:22, bold:true, color:FG, fontFace:"Calibri", valign:"middle", margin:0 });
  s.addText("以本專題兩個關鍵開發節點為例，展示人與 Claude 的實際互動過程", {
    x:0.84, y:0.60, w:8.92, h:0.26,
    fontSize:11, color:MUTED, fontFace:"Calibri", valign:"top", margin:0 });

  // ── 對話列 (col: 左=你問, 右=AI答) ─────────────────────────
  //  row 0: 場景標籤
  //  row 1: 對話氣泡

  const convos = [
    {
      scene: "場景一：模擬系統架構設計",
      sceneColor: CYAN,
      q: {
        label: "你問：",
        text:
          "我要做一個無人機機群攻防模擬，攻擊方 24 架飛機要用 Boids 行為引擎（凝聚、分離、對齊），並支援陣型切換（環形、箭頭、散佈）。防守方能發射攔截彈，碰到則爆炸。用 Python 物件導向實作，每幀更新一次，幫我設計主要的類別架構。",
      },
      a: {
        label: "Claude 回答：",
        text:
          "好的，以下是建議的主類別架構：\n\n• Drone（單架飛機）：pos, vel, role, neighbors → boids_force() + pid_update()\n• Swarm（機群）：List[Drone] → set_formation() + step()\n• Interceptor（攔截彈）：追蹤目標，碰撞偵測\n• Radar（防空）：tracks[] → predict_path() + fire()\n• Simulator（主迴圈）：swarm + radar → step() × T 幀\n\n已依你的需求生成完整骨架，需要我補全 boids_force() 實作嗎？",
        resultLabel: "→ 結果",
        result: "一個下午完成可執行的模擬主框架",
      },
    },
    {
      scene: "場景二：AI 模型除錯",
      sceneColor: ORANGE,
      q: {
        label: "你問：",
        text:
          "GNN 離線測試 Top-1 準確率是 87.1%，但放到線上模擬跑，斬首攔阻率只有 40%，為什麼差這麼多？還有辦法提升嗎？",
      },
      a: {
        label: "Claude 回答：",
        text:
          "離線與線上差距通常來自兩個原因：\n\n① 分布偏移：測試集是靜態快照，線上時機群持續移動、拓樸圖秒秒在變，模型看到的圖結構可能從未出現在訓練集。\n\n② 決策延遲：GNN 每幀推理 → 選出領機 → 防空下令 → 攔截彈才發射，有 3–5 幀延遲，領機可能已機動規避。\n\n建議：加入時序平滑（連 3 幀都預測同一架才斬首），並在訓練時加入動態圖序列。",
        resultLabel: "→ 結果",
        result: "定位到根因，引導後續實驗方向",
      },
    },
  ];

  const ROW_Y   = [0.94, 3.10];   // 兩組對話的起始 Y
  const ROW_H   = 1.95;
  const Q_X     = 0.28,  Q_W = 4.20;
  const A_X     = 4.68,  A_W = 5.04;

  convos.forEach((c, i) => {
    const y0 = ROW_Y[i];

    // 場景標題列
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:y0, w:9.44, h:0.30,
      fill:{color:c.sceneColor, transparency:85}, line:{color:c.sceneColor, pt:0.75}, rectRadius:0.04
    });
    s.addText(c.scene, {
      x:0.38, y:y0+0.01, w:9.24, h:0.28,
      fontSize:11, bold:true, color:c.sceneColor, fontFace:"Calibri", valign:"middle", margin:0
    });

    const by = y0 + 0.36;

    // 你問（左）
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:Q_X, y:by, w:Q_W, h:ROW_H-0.38,
      fill:{color:PANEL}, line:{color:c.sceneColor, pt:1}, rectRadius:0.07
    });
    s.addText(c.q.label, {
      x:Q_X+0.10, y:by+0.08, w:Q_W-0.16, h:0.22,
      fontSize:9.5, bold:true, color:c.sceneColor, fontFace:"Calibri", margin:0
    });
    s.addText(c.q.text, {
      x:Q_X+0.10, y:by+0.30, w:Q_W-0.18, h:ROW_H-0.72,
      fontSize:9, color:FG, fontFace:"Calibri", lineSpacingMultiple:1.4, valign:"top", margin:0
    });

    // AI答（右）
    const aH = ROW_H - 0.38 - 0.30;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:A_X, y:by, w:A_W, h:ROW_H-0.38,
      fill:{color:PNL2}, line:{color:GREEN, pt:1}, rectRadius:0.07
    });
    s.addText(c.a.label, {
      x:A_X+0.10, y:by+0.08, w:A_W-0.16, h:0.22,
      fontSize:9.5, bold:true, color:GREEN, fontFace:"Calibri", margin:0
    });
    s.addText(c.a.text, {
      x:A_X+0.10, y:by+0.30, w:A_W-0.18, h:aH,
      fontSize:8.8, color:FG, fontFace:"Calibri", lineSpacingMultiple:1.35, valign:"top", margin:0
    });

    // 結果標籤（右下角）
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:A_X+0.10, y:by+ROW_H-0.65, w:A_W-0.20, h:0.28,
      fill:{color:GREEN, transparency:85}, line:{color:GREEN, pt:0}, rectRadius:0.04
    });
    s.addText(`${c.a.resultLabel}  ${c.a.result}`, {
      x:A_X+0.14, y:by+ROW_H-0.65, w:A_W-0.28, h:0.28,
      fontSize:9, bold:true, color:GREEN, fontFace:"Calibri", valign:"middle", margin:0
    });
  });

  // 底部小結
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:0.28, y:5.08, w:9.44, h:0.38,
    fill:{color:"0d1520"}, line:{color:GOLD, pt:0.75}, rectRadius:0.05
  });
  s.addText("關鍵心得：描述清楚「架構需求 + 限制條件」，Claude 能直接生成可執行框架；描述「數據現象 + 預期行為差距」，Claude 能給出根因分析與改進方向", {
    x:0.34, y:5.10, w:9.32, h:0.34,
    fontSize:9.5, color:GOLD, fontFace:"Calibri", align:"center", valign:"middle", margin:0
  });

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
})();
