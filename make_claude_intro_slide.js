// make_claude_intro_slide.js — 1 張 Claude 入門介紹投影片
const pptxgen = require("pptxgenjs");
const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_claude_intro_slide.pptx`;

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

  const s = pres.addSlide();
  s.background = { color: BG };

  // Header
  s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
    fill:{color:GOLD}, line:{color:GOLD} });
  s.addText("AI", { x:0.25,y:0.12,w:0.48,h:0.48,
    fontSize:14, bold:true, color:BG,
    fontFace:"Calibri", align:"center", valign:"middle", margin:0 });
  s.addText("如何使用 Claude | 安裝 · 應用 · Claude Code 開發", {
    x:0.84, y:0.10, w:8.92, h:0.52,
    fontSize:22, bold:true, color:FG, fontFace:"Calibri", valign:"middle", margin:0 });
  s.addText("從申請帳號到在專案中實際開發——本專題完整使用 Claude Code 桌面版協助開發", {
    x:0.84, y:0.60, w:8.92, h:0.26,
    fontSize:11, color:MUTED, fontFace:"Calibri", valign:"top", margin:0 });

  // ── 三欄卡片 ─────────────────────────────────────────────────
  const CARD_Y = 0.94, CARD_H = 4.50, CARD_W = 2.96, GAP = 0.20;
  const START_X = 0.28;

  const cards = [
    {
      title:"① 安裝 Claude Code",
      c: CYAN,
      items: [
        { step:"1", text:"前往 claude.ai 申請帳號\n（支援 Google / GitHub 登入）" },
        { step:"2", text:"安裝 Node.js v18+\n（nodejs.org 下載安裝包）" },
        { step:"3", text:"終端機執行：\nnpm install -g @anthropic-ai/claude-code" },
        { step:"4", text:"在專案目錄輸入 claude\n完成登入後即可使用" },
      ],
    },
    {
      title:"② 三種應用方式",
      c: ORANGE,
      items: [
        { step:"▸", text:"網頁版 claude.ai\n問答・文件分析・程式解說" },
        { step:"▸", text:"Claude Code 桌面版 / CLI\n直接在 IDE 或終端機中協助開發\n（本專題主要使用方式）" },
        { step:"▸", text:"API 整合\n透過 HTTP 呼叫，將 Claude\n嵌入自己的應用程式" },
      ],
    },
    {
      title:"③ Claude Code 開發方式",
      c: GREEN,
      items: [
        { step:"▸", text:"在專案目錄執行 claude\n自動讀取整個程式碼庫" },
        { step:"▸", text:"用自然語言描述需求\nClaude 直接生成、修改檔案" },
        { step:"▸", text:"支援多檔案協作\n除錯・重構・測試一次完成" },
        { step:"▸", text:"對話式迭代\n看到問題直接描述，AI 即時修正" },
      ],
    },
  ];

  cards.forEach((card, i) => {
    const x = START_X + i * (CARD_W + GAP);

    // 卡片底板
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y:CARD_Y, w:CARD_W, h:CARD_H,
      fill:{color:PANEL}, line:{color:card.c, pt:1.5}, rectRadius:0.07
    });

    // 標題列
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:x+0.08, y:CARD_Y+0.10, w:CARD_W-0.16, h:0.34,
      fill:{color:card.c, transparency:80}, line:{color:card.c, pt:0}, rectRadius:0.04
    });
    s.addText(card.title, {
      x:x+0.08, y:CARD_Y+0.10, w:CARD_W-0.16, h:0.34,
      fontSize:11, bold:true, color:card.c,
      fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });

    // 每個 item
    const ITEM_START_Y = CARD_Y + 0.54;
    const ITEM_H = (CARD_H - 0.64) / card.items.length;

    card.items.forEach((item, j) => {
      const iy = ITEM_START_Y + j * ITEM_H;

      // 步驟徽章
      s.addShape(pres.shapes.OVAL, {
        x:x+0.12, y:iy+0.04, w:0.28, h:0.28,
        fill:{color:card.c, transparency:75}, line:{color:card.c, pt:0}
      });
      s.addText(item.step, {
        x:x+0.12, y:iy+0.04, w:0.28, h:0.28,
        fontSize:8, bold:true, color:card.c,
        fontFace:"Calibri", align:"center", valign:"middle", margin:0
      });

      // 說明文字
      s.addText(item.text, {
        x:x+0.46, y:iy+0.02, w:CARD_W-0.58, h:ITEM_H-0.06,
        fontSize:9.5, color:FG,
        fontFace:"Calibri", valign:"top", lineSpacingMultiple:1.35, margin:0
      });

      // 分隔線（最後一條不加）
      if (j < card.items.length - 1) {
        s.addShape(pres.shapes.RECTANGLE, {
          x:x+0.10, y:iy+ITEM_H-0.05, w:CARD_W-0.20, h:0.01,
          fill:{color:MUTED, transparency:75}, line:{color:MUTED, pt:0}
        });
      }
    });
  });

  // 底部提示
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:0.28, y:5.50, w:9.44, h:0.36,
    fill:{color:PNL2}, line:{color:GOLD, pt:0.75}, rectRadius:0.05
  });
  s.addText("本專題使用環境：Windows 11 · Node.js v22 · Python 3.10 · Claude Code 桌面版（claude-sonnet-4-6）", {
    x:0.34, y:5.52, w:9.32, h:0.32,
    fontSize:10, color:GOLD, fontFace:"Calibri", align:"center", valign:"middle", margin:0
  });

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
})();
