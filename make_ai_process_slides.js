// make_ai_process_slides.js
// 「如何使用 Claude」三張：做了什麼 / 工作流程 / 提示詞示範與心得
const pptxgen = require("pptxgenjs");
const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_ai_process_slides.pptx`;

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
  const ORANGE= "FF9900";
  const GREEN = "39D353";
  const BLUE  = "4488FF";
  const RED   = "FF5555";

  function hdr(s, label, c, title, sub) {
    s.background = { color: BG };
    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48, fill:{color:c}, line:{color:c} });
    s.addText(label, { x:0.25,y:0.12,w:0.48,h:0.48, fontSize:14, bold:true, color:BG,
      fontFace:"Calibri", align:"center", valign:"middle", margin:0 });
    s.addText(title, { x:0.84,y:0.10,w:8.92,h:0.52, fontSize:22, bold:true, color:FG,
      fontFace:"Calibri", valign:"middle", margin:0 });
    s.addText(sub, { x:0.84,y:0.60,w:8.92,h:0.26, fontSize:11, color:MUTED,
      fontFace:"Calibri", valign:"top", margin:0 });
  }

  // ════════════════════════════════════════════════════════════
  // Slide 1：使用 Claude 做了哪些事
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, "AI", GOLD,
      "AI 輔助研發 | 使用 Claude 做了哪些事",
      "本專題全程使用 Claude Code 作為開發夥伴，涵蓋從架構設計到成果輸出的每個環節");

    const cats = [
      { c:CYAN,   title:"模擬系統架構",   items:["Boids 行為引擎（凝聚/分離/對齊）","PID 位置控制器設計","7 種陣型幾何座標計算","攻防主迴圈時序整合"]},
      { c:GREEN,  title:"AI 模型開發",    items:["LSTM 網路架構與訓練 pipeline","GNN（GraphSAGE）建圖與訓練","多模型橫向評估框架","線上推理整合至防空迴圈"]},
      { c:ORANGE, title:"數據分析",       items:["headless 批次模擬驗證","多場景多 seed 攔阻率統計","ADE / FDE 誤差分析","Matplotlib 圖表自動輸出"]},
      { c:BLUE,   title:"視覺化輸出",     items:["Tactical2D 戰術地圖動畫","旁白字幕與慢動作效果","FFmpeg 影片剪輯合併","GitHub Pages 線上 Demo"]},
      { c:GOLD,   title:"簡報自動化",     items:["pptxgenjs 全自動建立投影片","影片嵌入與版面設計","文字內容校稿潤飾","ZIP 層級 PPTX 合併腳本"]},
      { c:MUTED,  title:"除錯與迭代",     items:["錯誤診斷與根因分析","邊緣情境處理（陣亡/耗彈）","參數調整建議（學習率/閾值）","架構重構與效能優化"]},
    ];

    const COL = 3, W = 3.06, H = 1.92, GAP_X = 0.17, GAP_Y = 0.18;
    const START_X = 0.28, START_Y = 0.94;

    cats.forEach((cat, idx) => {
      const col = idx % COL, row = Math.floor(idx / COL);
      const x = START_X + col * (W + GAP_X);
      const y = START_Y + row * (H + GAP_Y);

      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y, w:W, h:H, fill:{color:PANEL}, line:{color:cat.c, pt:1.2}, rectRadius:0.06
      });
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:x+0.08, y:y+0.08, w:W-0.16, h:0.30,
        fill:{color:cat.c, transparency:80}, line:{color:cat.c, pt:0}, rectRadius:0.04
      });
      s.addText(cat.title, {
        x:x+0.08, y:y+0.08, w:W-0.16, h:0.30,
        fontSize:10.5, bold:true, color:cat.c, fontFace:"Calibri",
        align:"center", valign:"middle", margin:0
      });
      cat.items.forEach((item, j) => {
        s.addText("· " + item, {
          x:x+0.14, y:y+0.44+j*0.34, w:W-0.22, h:0.30,
          fontSize:9.5, color:FG, fontFace:"Calibri", valign:"middle", margin:0
        });
      });
    });
  }

  // ════════════════════════════════════════════════════════════
  // Slide 2：人機協作工作流程
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, "AI", GOLD,
      "人機協作工作流程",
      "以對話驅動迭代開發——每次對話都是一次「需求明確化 → 產出 → 驗證 → 回饋」的循環");

    // 5-step flow
    const steps = [
      { n:"1", label:"需求描述",  sub:"用自然語言說明\n目標與限制條件",  c:CYAN   },
      { n:"2", label:"程式生成",  sub:"Claude 輸出可執行\n程式碼與說明",  c:GREEN  },
      { n:"3", label:"執行測試",  sub:"跑模擬、看輸出\n驗證行為是否正確", c:ORANGE },
      { n:"4", label:"問題回饋",  sub:"回報錯誤訊息或\n不符期望的輸出",   c:BLUE   },
      { n:"5", label:"迭代改進",  sub:"Claude 診斷根因\n修正並優化",       c:CYAN   },
    ];

    const BW = 1.60, BH = 2.20, BY = 1.22, GAP = 0.22;
    const TOTAL_W = steps.length * BW + (steps.length - 1) * GAP;
    const START_X = (10 - TOTAL_W) / 2;

    steps.forEach((st, i) => {
      const x = START_X + i * (BW + GAP);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y:BY, w:BW, h:BH, fill:{color:PANEL}, line:{color:st.c, pt:1.5}, rectRadius:0.08
      });
      // number badge
      s.addShape(pres.shapes.OVAL, {
        x:x+BW/2-0.26, y:BY+0.16, w:0.52, h:0.52, fill:{color:st.c}, line:{color:st.c}
      });
      s.addText(st.n, {
        x:x+BW/2-0.26, y:BY+0.16, w:0.52, h:0.52,
        fontSize:14, bold:true, color:BG, fontFace:"Calibri", align:"center", valign:"middle", margin:0
      });
      s.addText(st.label, {
        x:x+0.06, y:BY+0.80, w:BW-0.12, h:0.36,
        fontSize:13, bold:true, color:FG, fontFace:"Calibri", align:"center", margin:0
      });
      s.addText(st.sub, {
        x:x+0.08, y:BY+1.20, w:BW-0.16, h:0.90,
        fontSize:9.5, color:MUTED, fontFace:"Calibri", align:"center", lineSpacingMultiple:1.3, margin:0
      });
      // arrow (not after last)
      if (i < steps.length - 1) {
        s.addText("→", {
          x:x+BW+0.01, y:BY+BY*0.5+0.30, w:GAP, h:0.40,
          fontSize:18, bold:true, color:MUTED, fontFace:"Calibri", align:"center", valign:"middle", margin:0
        });
      }
    });

    // loop indicator
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:3.56, w:9.44, h:0.58,
      fill:{color:PNL2}, line:{color:GOLD, pt:1}, rectRadius:0.06
    });
    s.addText("↻  以上循環平均重複 3–8 次才完成一個功能模組，總計超過 200 輪對話", {
      x:0.34, y:3.59, w:9.32, h:0.52,
      fontSize:11.5, color:GOLD, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
  }

  // ════════════════════════════════════════════════════════════
  // Slide 3：提示詞示範 & AI 輔助心得
  // ════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    hdr(s, "AI", GOLD,
      "提示詞示範 & AI 輔助心得",
      "有效的 prompt 要說明目標、限制與預期格式——模糊的問題會得到模糊的解答");

    // Left: prompt examples
    s.addText("Prompt 示範", {
      x:0.28, y:0.94, w:5.60, h:0.28,
      fontSize:12, bold:true, color:GOLD, fontFace:"Calibri", margin:0
    });

    const prompts = [
      {
        tag:"模擬系統",  c:CYAN,
        text:"幫我實作無人機機群 Boids 行為引擎，\n需支援凝聚、分離、對齊三種力，並整合\nPID 控制器讓每架飛機精確到達目標點，\n用 Python 實作，每架飛機是獨立物件",
      },
      {
        tag:"除錯回饋",  c:ORANGE,
        text:"GNN 離線準確率 87.1% 但線上斬首攔阻率\n只有 40%，以下是錯誤訊息 [log]，幫我\n診斷原因並改進線上推理 pipeline",
      },
    ];

    prompts.forEach((p, i) => {
      const py = 1.28 + i * 1.88;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:0.28, y:py, w:5.60, h:1.72,
        fill:{color:PANEL}, line:{color:p.c, pt:1.2}, rectRadius:0.06
      });
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:0.36, y:py+0.10, w:1.20, h:0.26,
        fill:{color:p.c, transparency:80}, line:{color:p.c, pt:0}, rectRadius:0.03
      });
      s.addText(p.tag, {
        x:0.36, y:py+0.10, w:1.20, h:0.26,
        fontSize:9, bold:true, color:p.c, fontFace:"Calibri", align:"center", valign:"middle", margin:0
      });
      s.addText(p.text, {
        x:0.36, y:py+0.44, w:5.44, h:1.22,
        fontSize:9.5, color:FG, fontFace:"Calibri", valign:"top", lineSpacingMultiple:1.4, margin:0
      });
    });

    // Right: insights
    s.addText("AI 輔助心得", {
      x:6.12, y:0.94, w:3.60, h:0.28,
      fontSize:12, bold:true, color:GOLD, fontFace:"Calibri", margin:0
    });

    const insights = [
      { icon:"⏱", title:"節省框架搭建時間",  body:"省去約 80% 的初始架構搭建，\n讓更多精力放在核心研究",      c:GREEN  },
      { icon:"🔁", title:"快速驗證想法",      body:"從概念到可執行 demo 最快\n2–4 小時完成",                   c:CYAN   },
      { icon:"🎯", title:"精確描述是關鍵",    body:"需求越具體（含限制、格式、\n範例），輸出品質越高",           c:ORANGE },
      { icon:"✅", title:"人工驗證不可省",    body:"邏輯正確性與邊緣情境仍需\n自行測試確認，不能盲目信任",      c:RED    },
    ];

    insights.forEach((ins, i) => {
      const iy = 1.28 + i * 1.00;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:6.12, y:iy, w:3.60, h:0.88,
        fill:{color:PANEL}, line:{color:ins.c, pt:1}, rectRadius:0.06
      });
      s.addText(ins.title, {
        x:6.20, y:iy+0.06, w:3.44, h:0.26,
        fontSize:10.5, bold:true, color:ins.c, fontFace:"Calibri", margin:0
      });
      s.addText(ins.body, {
        x:6.20, y:iy+0.36, w:3.44, h:0.46,
        fontSize:9.5, color:FG, fontFace:"Calibri", lineSpacingMultiple:1.3, margin:0
      });
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
})();
