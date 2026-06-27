// make_explanation_slides.js
// 8 張講解投影片（2×要點1 + 2×要點2 + 2×要點3 + 2×要點4）
"use strict";
const pptxgen = require("pptxgenjs");

const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_講解投影片.pptx`;

const BG     = "0A0E14";
const PANEL  = "111820";
const PANEL2 = "0d1a28";
const GOLD   = "FFD700";
const FG     = "E6EDF3";
const MUTED  = "8AA0B5";
const RED    = "FF5555";
const GREEN  = "39D353";
const BLUE   = "4488FF";
const CYAN   = "00E5FF";
const ORANGE = "FF9900";

function hdr(s, pres, num, nc, title, sub) {
  s.background = { color: BG };
  s.addShape(pres.shapes.OVAL, {
    x:0.25, y:0.12, w:0.52, h:0.52,
    fill:{color:nc}, line:{color:nc}
  });
  s.addText(String(num), {
    x:0.25, y:0.12, w:0.52, h:0.52,
    align:"center", valign:"middle", fontSize:18, bold:true, color:BG, margin:0
  });
  s.addText(title, {
    x:0.88, y:0.13, w:8.7, h:0.44,
    fontSize:19, bold:true, color:FG, fontFace:"Calibri", valign:"middle", margin:0
  });
  if (sub) s.addText(sub, {
    x:0.88, y:0.58, w:8.7, h:0.24,
    fontSize:10.5, color:MUTED, fontFace:"Calibri", valign:"top", margin:0
  });
}

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";   // 10" × 5.625"

  // ════════════════════════════════════════════════════════════
  // 要點1 — Slide A: 本研究採用的兩種攻擊陣型
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "1", CYAN,
      "要點1 | 攻擊陣型 × 防空弱點對應",
      "傳統防空有兩個根本弱點：注意力上限 × 彈藥上限 · 兩種陣型分別針對其中一個設計");

    const fmts = [
      {
        name:"向心多弧包圍", eng:"Concentric Multi-Arc Encircle", color:CYAN, tag:"注意力上限",
        label:"陣型 1 / 2",
        pills:["三方向同時壓制", "追蹤資源稀釋", "覆蓋上限突破"],
        strategy:[
          "三條弧線同時從不同方向向目標收縮逼近",
          "防空需同時追蹤多方向，注意力與資源被稀釋",
          "前排犧牲引火，後排趁空間覆蓋失效突防",
        ],
        effect:"傳統防空「顧此失彼」，空間覆蓋上限被突破",
        stat:"16 / 24 架突防",
        video:"p1_1_encircle_v2.mp4",
      },
      {
        name:"重疊錐形＋誘餌", eng:"Arrowhead + Decoy Drones", color:ORANGE, tag:"彈藥上限",
        label:"陣型 2 / 2",
        pills:["誘餌引爆攔截彈", "彈藥耗盡無法攔", "主群空防滲透"],
        strategy:[
          "6 架誘餌機全速衝前，引誘防空系統集中開火",
          "攔截彈有限，誘餌將其全數引爆消耗殆盡",
          "彈藥耗盡後，主攻陣型面對空虛防線大量突防",
        ],
        effect:"防空彈藥資源耗盡，物理上無法再繼續攔截",
        stat:"防空彈藥耗盡率 100%",
        video:"p1_2_decoys_v2.mp4",
      },
    ];

    fmts.forEach((f, i) => {
      const x = i === 0 ? 0.28 : 5.20;
      const w = 4.52;

      // Card background
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y:0.88, w, h:4.62,
        fill:{color:PANEL}, line:{color:f.color, pt:1.5}, rectRadius:0.07
      });

      // Label (陣型 N/2)
      s.addText(f.label, {
        x:x+0.14, y:0.95, w:0.90, h:0.26,
        fontSize:9, color:MUTED, fontFace:"Calibri", align:"left", valign:"middle", margin:0
      });

      // Tag badge (top right)
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:x+w-1.14, y:0.95, w:1.00, h:0.26,
        fill:{color:f.color, transparency:82}, line:{color:f.color, pt:1}, rectRadius:0.04
      });
      s.addText(f.tag, {
        x:x+w-1.14, y:0.95, w:1.00, h:0.26,
        fontSize:9, bold:true, color:f.color, fontFace:"Calibri", align:"center", valign:"middle", margin:0
      });

      // Formation name
      s.addText(f.name, {
        x:x+0.14, y:1.26, w:w-0.28, h:0.52,
        fontSize:20, bold:true, color:FG, fontFace:"Calibri", align:"left", valign:"middle", margin:0
      });

      // English name
      s.addText(f.eng, {
        x:x+0.14, y:1.78, w:w-0.28, h:0.22,
        fontSize:10, color:MUTED, fontFace:"Calibri", align:"left", margin:0
      });

      // Feature pills (3 equal-width)
      const pillW = (w - 0.40) / 3;
      f.pills.forEach((p, j) => {
        const px = x + 0.14 + j * (pillW + 0.06);
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
          x:px, y:2.08, w:pillW, h:0.28,
          fill:{color:f.color, transparency:88}, line:{color:f.color, pt:0.75}, rectRadius:0.03
        });
        s.addText(p, {
          x:px, y:2.08, w:pillW, h:0.28,
          fontSize:9, color:FG, fontFace:"Calibri", align:"center", valign:"middle", margin:0
        });
      });

      // Divider
      s.addShape(pres.shapes.RECTANGLE, {
        x:x+0.14, y:2.44, w:w-0.28, h:0.02,
        fill:{color:f.color, transparency:70}, line:{color:f.color, transparency:70, pt:0.5}
      });

      // Strategy section heading
      s.addText("戰術策略", {
        x:x+0.14, y:2.50, w:1.10, h:0.24,
        fontSize:9.5, bold:true, color:f.color, fontFace:"Calibri", valign:"middle", margin:0
      });

      // Strategy bullet lines
      f.strategy.forEach((line, j) => {
        s.addText("· " + line, {
          x:x+0.18, y:2.77+j*0.34, w:w-0.32, h:0.30,
          fontSize:10, color:FG, fontFace:"Calibri", valign:"middle", margin:0
        });
      });

      // Anti-defense effect highlight
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:x+0.14, y:3.82, w:w-0.28, h:0.44,
        fill:{color:f.color, transparency:92}, line:{color:f.color, pt:1}, rectRadius:0.04
      });
      s.addText(f.effect, {
        x:x+0.20, y:3.82, w:w-0.40, h:0.44,
        fontSize:9.5, bold:true, color:f.color, fontFace:"Calibri", valign:"middle", margin:0
      });

      // Key stat
      s.addText(f.stat, {
        x:x+0.14, y:4.34, w:w-0.28, h:0.44,
        fontSize:18, bold:true, color:f.color, fontFace:"Calibri", align:"center", valign:"middle", margin:0
      });

      // Video reference
      s.addText(f.video, {
        x:x+0.14, y:4.82, w:w-0.28, h:0.22,
        fontSize:8, color:MUTED, fontFace:"Calibri", align:"center", margin:0
      });
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點1 — Slide B: 容錯量化指標
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "1", CYAN,
      "要點1 | 容錯量化指標與陣型效能對比",
      "向心多弧陣型穩態飛行實測 · 24架 + 4中繼");

    // 3 big stats
    const kpis = [
      {v:"< 4 m",   l:"平均定位誤差",  s:"Mean Displacement Error",  c:CYAN},
      {v:"< 24 m",  l:"P95 定位誤差",  s:"95th Percentile Error",     c:ORANGE},
      {v:"100 %",   l:"任意時刻連線率", s:"Connectivity at Any Time",  c:GREEN},
    ];
    kpis.forEach((k, i) => {
      const x = 0.38 + i * 3.1;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y:0.88, w:2.82, h:1.55,
        fill:{color:PANEL}, line:{color:k.c, pt:1.5}, rectRadius:0.08
      });
      s.addText(k.v, {x,y:1.02,w:2.82,h:0.72, fontSize:30,bold:true,color:k.c,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(k.l, {x,y:1.74,w:2.82,h:0.28, fontSize:11.5,bold:true,color:FG,fontFace:"Calibri",align:"center",margin:0});
      s.addText(k.s, {x,y:2.02,w:2.82,h:0.24, fontSize:8.5,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
    });

    // Table header
    s.addText("各陣型突防效能對比（24架攻擊，卡爾曼 CV 防守）", {
      x:0.3, y:2.55, w:9.4, h:0.28,
      fontSize:11.5, bold:true, color:GOLD, fontFace:"Calibri", margin:0
    });

    const CH = ["陣型","特性","突防架數","被斬首影響","通訊韌性"];
    const CX = [0.30, 1.62, 3.20, 5.00, 7.00];
    const CW = [1.26, 1.50, 1.70, 1.90, 2.55];

    CH.forEach((h, c) => {
      s.addShape(pres.shapes.RECTANGLE, {
        x:CX[c], y:2.88, w:CW[c]-0.04, h:0.30,
        fill:{color:"1a2535"}, line:{color:CYAN, pt:0.5}
      });
      s.addText(h, {x:CX[c],y:2.88,w:CW[c]-0.04,h:0.30, fontSize:9.5,bold:true,color:CYAN,fontFace:"Calibri",align:"center",valign:"middle",margin:1});
    });

    const rows = [
      ["向心多弧", "高包圍",  "16 / 24 架", "中等",          "Mesh冗餘，高韌"],
      ["箭頭陣",   "高突防",  "19 / 24 架", "嚴重（前端領機）","集中鏈路，脆弱"],
      ["梯形側翼", "側翼展開","14 / 24 架", "低（後方指揮）",  "側翼鏈路分散，強"],
      ["方陣",     "均衡基準","15 / 24 架", "中等",           "均等冗餘，中等"],
    ];
    rows.forEach((row, r) => {
      const by = 3.22 + r * 0.46;
      const bg = r % 2 === 0 ? PANEL : PANEL2;
      row.forEach((cell, c) => {
        s.addShape(pres.shapes.RECTANGLE, {
          x:CX[c], y:by, w:CW[c]-0.04, h:0.40,
          fill:{color:bg}, line:{color:"1a2a3a",pt:0.5}
        });
        const tc = c===0 ? CYAN : (c===2 ? GREEN : FG);
        s.addText(cell, {x:CX[c],y:by,w:CW[c]-0.04,h:0.40, fontSize:9.5,color:tc,fontFace:"Calibri",align:c===0?"center":"left",valign:"middle",margin:3});
      });
    });

    // Bottom note
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.30, y:5.10, w:9.40, h:0.40,
      fill:{color:"0d1e2e"}, line:{color:CYAN, pt:0.75}, rectRadius:0.05
    });
    s.addText("通訊拓樸：Mesh 網格 — 每機維持 ≥ 2 條冗餘鏈路，任一節點斷線不影響整體連通性", {
      x:0.35, y:5.12, w:9.30, h:0.36,
      fontSize:10.5, color:CYAN, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點2 — Slide A: 指揮繼承鏈協議
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "2", ORANGE,
      "要點2 | 指揮繼承鏈協議（無線機群）",
      "領機陣亡後的自動恢復流程 · fail_strategy = chain · 四步驟完成重組");

    const steps = [
      {t:"T = 0 s",    icon:"✕", ic:RED,    title:"領機陣亡",       body:"心跳封包\n停止廣播\n僚機啟動等待"},
      {t:"T + 1.2 s",  icon:"!", ic:ORANGE, title:"超時偵測",        body:"follower_timeout\n= 1.2 s\n觸發選舉程序"},
      {t:"T + 1.8 s",  icon:"★", ic:GOLD,   title:"繼承人選舉",      body:"election_time\n= 0.6 s\n按優先順序決出"},
      {t:"T + 13 s",   icon:"✓", ic:GREEN,  title:"編隊重組完成",    body:"新領機廣播位置\n隊形誤差恢復\n< 4 m"},
    ];

    steps.forEach((st, i) => {
      const x = 0.28 + i * 2.38;
      const w = 2.18;
      // Time badge
      s.addText(st.t, {x,y:0.90,w,h:0.26, fontSize:9.5,bold:true,color:st.ic,fontFace:"Calibri",align:"center",margin:0});
      // Card
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y:1.20, w, h:2.68,
        fill:{color:PANEL}, line:{color:st.ic, pt:2}, rectRadius:0.08
      });
      // Icon circle
      s.addShape(pres.shapes.OVAL, {
        x:x+0.69, y:1.34, w:0.72, h:0.72,
        fill:{color:st.ic, transparency:81}, line:{color:st.ic, pt:2}
      });
      s.addText(st.icon, {x:x+0.69,y:1.34,w:0.72,h:0.72, fontSize:18,bold:true,color:st.ic,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(st.title, {x:x+0.06,y:2.15,w:w-0.12,h:0.42, fontSize:13,bold:true,color:FG,fontFace:"Calibri",align:"center",margin:0});
      s.addText(st.body, {x:x+0.08,y:2.60,w:w-0.16,h:1.22, fontSize:10,color:FG,fontFace:"Calibri",align:"center",valign:"top",margin:3,lineSpacingMultiple:1.45});
      // Arrow
      if (i < 3) {
        s.addShape(pres.shapes.RIGHT_ARROW, {
          x:x+w+0.04, y:2.35, w:0.26, h:0.32,
          fill:{color:MUTED}, line:{color:MUTED}
        });
      }
    });

    // Priority list
    s.addText("繼承優先順序：", {x:0.30,y:4.05,w:2.5,h:0.30, fontSize:11.5,bold:true,color:GOLD,fontFace:"Calibri",margin:0});
    const pri = [
      "① 存活時間最長的僚機（資深代理權優先）",
      "② 距離原領機位置最近的僚機（空間連續性）",
      "③ 剩餘電量最充足的僚機（任務延續保障）",
    ];
    pri.forEach((p, i) => {
      s.addText(p, {x:0.30,y:4.40+i*0.36,w:9.40,h:0.32, fontSize:10.5,color:FG,fontFace:"Calibri",margin:0});
    });

    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.30, y:5.15, w:9.40, h:0.38,
      fill:{color:"0d1e2e"}, line:{color:ORANGE, pt:0.75}, rectRadius:0.05
    });
    s.addText("心跳逾時 1.2s → 選舉 0.6s → 重組 ~11.2s，總計約 13s 恢復完整編隊能力", {
      x:0.35, y:5.17, w:9.30, h:0.34,
      fontSize:10.5, color:ORANGE, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點2 — Slide B: 無線機群 vs 光纖精準群
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "2", ORANGE,
      "要點2 | 兩種機群架構對比",
      "依通訊基礎設施分類 · 影響AI斬首漏洞與殘存突防能力");

    const cols = [
      {
        title:"無線大群", eng:"Wireless Swarm", color:RED, x:0.28,
        tag:"[ 可斬首 ]  [ 指揮藏中心 ]  [ 大規模 ]",
        rows:[
          ["通訊方式", "Wi-Fi / 900 MHz 射頻"],
          ["指揮位置", "隱藏於機群幾何中心"],
          ["規模",     "大型（24 架以上）"],
          ["斬首弱點", "識別並擊落領機 → 全群癱瘓"],
          ["AI 識別率","GNN 87.1% — 高度可斬首"],
          ["殘存能力", "低，依賴繼承鏈約 13s 恢復"],
        ],
        sum:"領機雖藏中心，但 GNN 可透過\n拓樸圖學習結構特徵精準識別，\n斬首後整群指揮中斷",
        sumc: RED,
      },
      {
        title:"光纖精準群", eng:"Fiber-Linked Precision Swarm", color:GREEN, x:5.22,
        tag:"[ 抗斬首 ]  [ 後機續突 ]  [ 高容錯 ]",
        rows:[
          ["通訊方式", "物理光纖連結（硬接線）"],
          ["指揮位置", "後方遠端地面站"],
          ["規模",     "精準小組（4–8 架）"],
          ["斬首弱點", "無前線領機 → AI斬首策略失效"],
          ["AI 識別率","N/A — 無可識別領機"],
          ["殘存能力", "高，後機按預設路線直接續突"],
        ],
        sum:"光纖連結使所有機皆為「同等節點」，\nGNN 無法找到領機目標，\nAI 斬首策略完全失效",
        sumc: GREEN,
      },
    ];

    cols.forEach(col => {
      const w = 4.56;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:col.x, y:0.88, w, h:4.60,
        fill:{color:PANEL}, line:{color:col.color, pt:2}, rectRadius:0.08
      });
      // Title bar
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:col.x, y:0.88, w, h:0.58,
        fill:{color:col.color, transparency:84}, line:{color:col.color, pt:2}, rectRadius:0.08
      });
      s.addText(col.title, {x:col.x,y:0.90,w,h:0.30, fontSize:15,bold:true,color:col.color,fontFace:"Calibri",align:"center",margin:0});
      s.addText(col.eng,   {x:col.x,y:1.18,w,h:0.22, fontSize:9,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
      // Tag
      s.addText(col.tag, {x:col.x+0.10,y:1.52,w:w-0.20,h:0.26, fontSize:9.5,bold:true,color:col.color,fontFace:"Calibri",align:"center",margin:0});
      // Rows
      col.rows.forEach((r, i) => {
        const ry = 1.84 + i * 0.40;
        const rbg = i%2===0 ? PANEL : PANEL2;
        s.addShape(pres.shapes.RECTANGLE, {x:col.x+0.08,y:ry,w:w-0.16,h:0.36, fill:{color:rbg},line:{color:"1a2a3a",pt:0}});
        s.addText(r[0]+"：", {x:col.x+0.12,y:ry,w:1.35,h:0.36, fontSize:9,bold:true,color:MUTED,fontFace:"Calibri",valign:"middle",margin:2});
        s.addText(r[1],       {x:col.x+1.50,y:ry,w:w-1.62,h:0.36, fontSize:9,color:FG,fontFace:"Calibri",valign:"middle",margin:2});
      });
      // Summary
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:col.x+0.08, y:4.28, w:w-0.16, h:1.08,
        fill:{color:col.color, transparency:92}, line:{color:col.color,pt:1}, rectRadius:0.05
      });
      s.addText(col.sum, {x:col.x+0.14,y:4.32,w:w-0.28,h:1.00, fontSize:9.5,color:col.sumc,fontFace:"Calibri",valign:"top",margin:3,lineSpacingMultiple:1.42});
    });

    // VS
    s.addText("VS", {x:4.60,y:2.5,w:0.60,h:0.52, fontSize:20,bold:true,color:GOLD,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
  }

  // ════════════════════════════════════════════════════════════
  // 要點3 — Slide A: LSTM 架構原理
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "3", GREEN,
      "要點3 | LSTM 軌跡預測網路架構",
      "長短期記憶網路捕捉非線性機動 · 對比卡爾曼 CV（等速模型）的結構性差異");

    // Architecture boxes
    const boxes = [
      {l:"輸入序列", sub:"過去 10 幀\n(x,y,vx,vy)\n× 10 步\n= 40 特徵", c:GREEN,  x:0.28, w:2.05},
      {l:"LSTM Layer 1", sub:"128 units\n遺忘門 ft\n輸入門 it\n輸出門 ot", c:GREEN,  x:2.50, w:2.05},
      {l:"LSTM Layer 2", sub:"128 units\n長期依賴\n隱藏狀態 ht\n捕捉加速度", c:GREEN,  x:4.72, w:2.05},
      {l:"Dense Output", sub:"未來 5 步\n(x,y) × 5\n= 10 輸出值", c:CYAN,   x:6.94, w:2.05},
      {l:"攔截座標", sub:"防空單位\n接收預測位置\n計算攔截點", c:ORANGE, x:9.16, w:0.60},
    ];

    boxes.forEach((b, i) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:b.x, y:0.88, w:b.w, h:2.00,
        fill:{color:"0d1520"}, line:{color:b.c, pt:1.5}, rectRadius:0.06
      });
      s.addText(b.l, {x:b.x,y:0.88,w:b.w,h:0.36, fontSize:10.5,bold:true,color:b.c,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(b.sub, {x:b.x+0.06,y:1.24,w:b.w-0.12,h:1.56, fontSize:9.5,color:FG,fontFace:"Calibri",align:"center",valign:"top",margin:3,lineSpacingMultiple:1.4});
      if (i < 4) {
        s.addShape(pres.shapes.RIGHT_ARROW, {
          x:b.x+b.w+0.02, y:1.65, w:0.24, h:0.28,
          fill:{color:MUTED}, line:{color:MUTED}
        });
      }
    });

    // Training note
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:3.02, w:9.50, h:0.50,
      fill:{color:PANEL2}, line:{color:GREEN, pt:0.75}, rectRadius:0.05
    });
    s.addText("訓練：模擬軌跡 50,000 條  ·  Loss = MSE(預測位置, 真實位置)  ·  Optimizer = Adam  ·  Epochs = 100", {
      x:0.33, y:3.04, w:9.40, h:0.46,
      fontSize:10.5, color:GREEN, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });

    // CV comparison
    s.addText("相比卡爾曼 CV（卡爾曼濾波・等速模型）", {x:0.28,y:3.62,w:9.5,h:0.28, fontSize:12,bold:true,color:RED,fontFace:"Calibri",margin:0});
    const cv = [
      {k:"CV 公式",  v:"x(t+k) = x(t) + k·vₓ   |   y(t+k) = y(t) + k·vᵧ   （假設速度永恆不變）"},
      {k:"CV 缺點",  v:"無法預測急轉彎、機動閃避、突然加減速等非線性行為"},
      {k:"LSTM 優勢",v:"記憶過去 10 幀的速度變化趨勢，在機動場景 FDE 低達 −45%"},
    ];
    cv.forEach((r, i) => {
      s.addText(r.k+"：", {x:0.28,y:3.96+i*0.40,w:1.45,h:0.36, fontSize:10.5,bold:true,color:MUTED,fontFace:"Calibri",valign:"middle",margin:0});
      s.addText(r.v,      {x:1.70,y:3.96+i*0.40,w:8.05,h:0.36, fontSize:10.5,color:FG,fontFace:"Calibri",valign:"middle",margin:0});
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點3 — Slide B: 預測精度量化比較
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "3", GREEN,
      "要點3 | 軌跡預測精度量化比較",
      "ADE / FDE 指標 · 三種預測方法 × 三種飛行場景 · 同一 seed 測試集");

    // Left: metric definitions
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:0.88, w:3.15, h:2.05,
      fill:{color:PANEL}, line:{color:GREEN,pt:1.5}, rectRadius:0.06
    });
    s.addText("評估指標定義", {x:0.28,y:0.88,w:3.15,h:0.36, fontSize:12,bold:true,color:GREEN,fontFace:"Calibri",align:"center",margin:0});
    s.addText("ADE（Average Displacement Error）\n所有預測步驟的平均位移誤差\n越小越準確", {x:0.36,y:1.26,w:2.99,h:0.70, fontSize:10,color:FG,fontFace:"Calibri",valign:"top",margin:3,lineSpacingMultiple:1.35});
    s.addShape(pres.shapes.LINE, {x:0.48,y:1.98,w:2.75,h:0, line:{color:MUTED,pt:0.5}});
    s.addText("FDE（Final Displacement Error）\n第 t+5 步（最終位置）的位移誤差\n最能反映實際攔截能力", {x:0.36,y:2.02,w:2.99,h:0.80, fontSize:10,color:FG,fontFace:"Calibri",valign:"top",margin:3,lineSpacingMultiple:1.35});

    // Right: FDE horizontal bars
    const maxFDE = 19.45;
    const bx = 3.68;
    const bmx = 5.80;
    const methods = [
      {n:"卡爾曼 CV",     fde:19.45, ade:8.32,  c:RED},
      {n:"卡爾曼濾波 KF", fde:16.23, ade:6.87,  c:ORANGE},
      {n:"LSTM（本文）",  fde:10.61, ade:4.51,  c:GREEN},
    ];
    s.addText("FDE 整體比較（公尺，越小越準）", {x:bx,y:0.88,w:bmx,h:0.28, fontSize:11.5,bold:true,color:GOLD,fontFace:"Calibri",margin:0});
    methods.forEach((m, i) => {
      const by = 1.24 + i * 0.88;
      const bw = (m.fde / maxFDE) * bmx;
      s.addText(m.n, {x:bx,y:by,w:bmx,h:0.26, fontSize:10,bold:i===2,color:i===2?GREEN:FG,fontFace:"Calibri",margin:0});
      s.addShape(pres.shapes.RECTANGLE, {x:bx,y:by+0.28,w:bw,h:0.38, fill:{color:m.c, transparency:60},line:{color:m.c,pt:1}});
      s.addText(`FDE: ${m.fde} m`, {x:bx+bw+0.10,y:by+0.28,w:2.4,h:0.38, fontSize:10.5,color:m.c,fontFace:"Calibri",valign:"middle",margin:0});
      if (i===2) s.addText("−45.4%", {x:bx+4.2,y:by+0.28,w:1.0,h:0.38, fontSize:10.5,bold:true,color:GREEN,fontFace:"Calibri",valign:"middle",margin:0});
    });

    // Scenario table
    s.addText("場景分解：機動閃避場景 LSTM 優勢最顯著", {x:0.28,y:3.56,w:9.50,h:0.28, fontSize:11.5,bold:true,color:CYAN,fontFace:"Calibri",margin:0});
    const sHdr = ["場景","CV FDE","KF FDE","LSTM FDE","改善幅度（vs CV）"];
    const sX   = [0.28, 2.35, 4.00, 5.65, 7.30];
    const sW   = [2.00, 1.56, 1.56, 1.56, 2.15];
    sHdr.forEach((h, c) => {
      s.addShape(pres.shapes.RECTANGLE, {x:sX[c],y:3.88,w:sW[c]-0.04,h:0.30, fill:{color:"1a2535"},line:{color:CYAN, pt:0.5}});
      s.addText(h, {x:sX[c],y:3.88,w:sW[c]-0.04,h:0.30, fontSize:9.5,bold:true,color:CYAN,fontFace:"Calibri",align:"center",valign:"middle",margin:1});
    });
    const sRows = [
      ["直線巡航",     "8.2 m",  "6.8 m",  "6.7 m",  "−18%"],
      ["漸速機動",     "14.6 m", "11.4 m", "9.8 m",  "−33%"],
      ["急轉機動閃避", "22.1 m", "18.5 m", "10.5 m", "−52%"],
    ];
    sRows.forEach((row, r) => {
      const ry = 4.22 + r * 0.40;
      const rbg = r%2===0 ? PANEL : PANEL2;
      row.forEach((cell, c) => {
        s.addShape(pres.shapes.RECTANGLE, {x:sX[c],y:ry,w:sW[c]-0.04,h:0.36, fill:{color:rbg},line:{color:"1a2a3a",pt:0.5}});
        const tc = c===0 ? FG : (c===3 ? GREEN : (c===4 ? (r===2?GREEN:r===1?ORANGE:MUTED) : MUTED));
        s.addText(cell, {x:sX[c],y:ry,w:sW[c]-0.04,h:0.36, fontSize:9.5,color:tc,fontFace:"Calibri",align:"center",valign:"middle",margin:2});
      });
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點4 — Slide A: GNN 圖神經網路原理
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "4", BLUE,
      "要點4 | GNN 圖神經網路原理",
      "以機群通訊拓樸圖識別「領機」· 節點特徵聚合 → 角色分類 → 精準斬首");

    // Left: Graph definition
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:0.88, w:4.55, h:4.60,
      fill:{color:PANEL}, line:{color:BLUE,pt:1.5}, rectRadius:0.06
    });
    s.addText("圖結構定義 G = (V, E)", {x:0.28,y:0.88,w:4.55,h:0.38, fontSize:13,bold:true,color:BLUE,fontFace:"Calibri",align:"center",margin:0});

    const gSec = [
      {t:"節點 V = 每架無人機", c:CYAN, items:[
        "位置 (x, y, z)",
        "速度 (vx, vy, vz)",
        "與前機距離 d_leader",
        "速度比例 v/v_leader",
      ]},
      {t:"邊 E = 通訊鏈路", c:ORANGE, items:[
        "相對距離 Δd",
        "方位角 θ_bearing",
        "條件：d < 通訊半徑 R",
      ]},
      {t:"標籤 Y = 角色", c:GOLD, items:[
        "0 → 僚機 (follower)",
        "1 → 領機 (leader)",
        "2 → 中繼機 (relay)",
      ]},
    ];
    let gy = 1.32;
    gSec.forEach(gs => {
      s.addText(gs.t, {x:0.36,y:gy,w:4.22,h:0.28, fontSize:11,bold:true,color:gs.c,fontFace:"Calibri",margin:0});
      gy += 0.30;
      gs.items.forEach(it => {
        s.addText("  ·  "+it, {x:0.36,y:gy,w:4.22,h:0.26, fontSize:9.5,color:FG,fontFace:"Calibri",margin:0});
        gy += 0.26;
      });
      gy += 0.14;
    });

    // Topology advantage
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.36, y:4.32, w:4.22, h:1.02,
      fill:{color:"0d1e2e"}, line:{color:BLUE, pt:0.75}, rectRadius:0.05
    });
    s.addText("拓樸優勢：通訊圖中「領機」通常是出度最高的節點（最多連線、訊息最多）→ GNN 自動學習此結構特徵，不依賴位置座標", {
      x:0.42, y:4.36, w:4.10, h:0.94,
      fontSize:9.5, color:BLUE, fontFace:"Calibri", valign:"top", margin:3, lineSpacingMultiple:1.35
    });

    // Right: GCN pipeline
    s.addText("圖卷積推理流程", {x:5.10,y:0.88,w:4.60,h:0.36, fontSize:13,bold:true,color:BLUE,fontFace:"Calibri",align:"center",margin:0});
    const pipe = [
      {l:"輸入圖  G = (V, E)",             c:BLUE,   sub:"N 個節點，各 6 維特徵"},
      {l:"GCN Layer 1  ×128 + ReLU",       c:BLUE,   sub:"聚合 1-hop 鄰居特徵"},
      {l:"GCN Layer 2  ×128 + ReLU",       c:BLUE,   sub:"聚合 2-hop 鄰居，感知距離擴大"},
      {l:"GCN Layer 3  ×64 + ReLU",        c:CYAN,   sub:"全域圖結構感知"},
      {l:"Softmax  → 各節點領機概率",       c:GREEN,  sub:"最高概率節點 → 斬首目標"},
    ];
    pipe.forEach((p, i) => {
      const py = 1.30 + i * 0.80;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:5.10, y:py, w:4.60, h:0.64,
        fill:{color:"0d1520"}, line:{color:p.c,pt:1.5}, rectRadius:0.05
      });
      s.addText(p.l,   {x:5.14,y:py+0.04,w:4.52,h:0.32, fontSize:10.5,bold:true,color:p.c,fontFace:"Calibri",align:"center",margin:0});
      s.addText(p.sub, {x:5.14,y:py+0.36,w:4.52,h:0.24, fontSize:9,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
      if (i < 4) {
        s.addText("▼", {x:7.25,y:py+0.64,w:0.22,h:0.18, fontSize:9,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
      }
    });
  }

  // ════════════════════════════════════════════════════════════
  // 要點4 — Slide B: 識別效能與線上斬首效果
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, pres, "4", BLUE,
      "要點4 | 識別效能比較與線上斬首效果",
      "Top-1 離線識別準確率 · 線上防空效能（箭頭陣型，多場景統計）");

    // Left: accuracy bars
    s.addText("Top-1 識別準確率（離線測試集）", {x:0.28,y:0.88,w:5.60,h:0.28, fontSize:12,bold:true,color:GOLD,fontFace:"Calibri",margin:0});
    const models = [
      {n:"規則法 (Rule-based)",        acc:26.8, c:RED},
      {n:"決策樹 (Decision Tree)",     acc:51.4, c:MUTED},
      {n:"隨機森林 (Random Forest)",   acc:58.2, c:ORANGE},
      {n:"圖神經網路 GNN ★",           acc:87.1, c:BLUE},
    ];
    const bMaxW = 5.5;
    models.forEach((m, i) => {
      const by = 1.24 + i * 0.74;
      const bw = (m.acc / 87.1) * bMaxW;
      const isGnn = m.acc === 87.1;
      s.addText(m.n, {x:0.28,y:by,w:5.5,h:0.24, fontSize:9.5,bold:isGnn,color:isGnn?BLUE:FG,fontFace:"Calibri",margin:0});
      s.addShape(pres.shapes.RECTANGLE, {x:0.28,y:by+0.26,w:bw,h:0.34, fill:{color:m.c, transparency:60},line:{color:m.c,pt:1}});
      s.addText(`${m.acc}%`, {x:0.28+bw+0.10,y:by+0.26,w:1.10,h:0.34, fontSize:10.5,bold:isGnn,color:m.c,fontFace:"Calibri",valign:"middle",margin:0});
    });

    // Right: online effect
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:6.08, y:0.88, w:3.62, h:4.02,
      fill:{color:PANEL}, line:{color:BLUE,pt:1.5}, rectRadius:0.06
    });
    s.addText("線上斬首防空效能\n箭頭陣型 · 24 架", {x:6.08,y:0.90,w:3.62,h:0.56, fontSize:12,bold:true,color:BLUE,fontFace:"Calibri",align:"center",margin:0});

    const onl = [
      {m:"卡爾曼 CV（不斬首）",th:16,  kill:7,  itc:"0%",   c:RED},
      {m:"RF 識別 → 斬首",  th:9.2, kill:9,  itc:"20%",  c:ORANGE},
      {m:"GNN 識別 → 斬首", th:6.2, kill:12, itc:"40%",  c:BLUE},
    ];
    onl.forEach((od, i) => {
      const oy = 1.52 + i * 1.10;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:6.16, y:oy, w:3.46, h:1.00,
        fill:{color:"0d1520"}, line:{color:od.c,pt:1.5}, rectRadius:0.05
      });
      s.addText(od.m, {x:6.16,y:oy+0.04,w:3.46,h:0.28, fontSize:10.5,bold:true,color:od.c,fontFace:"Calibri",align:"center",margin:0});
      s.addText(`突防：${od.th} 架  |  攔阻：${od.itc}`, {x:6.16,y:oy+0.36,w:3.46,h:0.26, fontSize:10,color:FG,fontFace:"Calibri",align:"center",margin:0});
      s.addText(`擊落 ${od.kill} 架`, {x:6.16,y:oy+0.66,w:3.46,h:0.26, fontSize:9.5,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
    });

    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:6.16, y:4.30, w:3.46, h:0.48,
      fill:{color:"0d1e2e"}, line:{color:BLUE, pt:0.75}, rectRadius:0.05
    });
    s.addText("攔阻率\n0% → 40%\n(+100%)", {x:6.16,y:4.32,w:3.46,h:0.44, fontSize:9.5,bold:true,color:BLUE,fontFace:"Calibri",align:"center",valign:"middle",margin:2,lineSpacingMultiple:1.2});

    // Bottom summary
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:5.10, w:9.50, h:0.42,
      fill:{color:"0d1e2e"}, line:{color:BLUE, pt:0.75}, rectRadius:0.05
    });
    s.addText("GNN 斬首使攔阻率 0%→40%，突防減少 61%；相比 RF 斬首再提升 +20pp 攔阻率（20%→40%）", {
      x:0.33, y:5.12, w:9.40, h:0.38,
      fontSize:10.5, bold:true, color:BLUE, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
  console.log("8 slides: 要點1×2 + 要點2×2 + 要點3×2 + 要點4×2");
}

main().catch(e => { console.error(e); process.exit(1); });
