// make_chapter_slides.js
// 章節切換大標 × 5 + 感謝聆聽 × 1
const pptxgen = require("pptxgenjs");
const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_chapter_slides.pptx`;

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";

  const BG    = "0A0E14";
  const FG    = "E6EDF3";
  const MUTED = "8AA0B5";
  const GOLD  = "FFD700";
  const CYAN  = "00E5FF";
  const ORANGE= "FF9900";
  const GREEN = "39D353";
  const BLUE  = "4488FF";
  const RED   = "FF5555";

  const chapters = [
    { n:"01", title:"攻擊陣型 × 防空弱點",   sub:"兩種陣型各針對傳統防空的一個根本弱點",        c:CYAN   },
    { n:"02", title:"指揮繼承鏈遞補",         sub:"領機陣亡後的自動選舉與隊形重組協議",            c:ORANGE },
    { n:"03", title:"LSTM 軌跡預測防空",      sub:"深度學習預測機動路徑，FDE 改善 45%",            c:GREEN  },
    { n:"04", title:"GNN 領機識別斬首",       sub:"圖神經網路識別通訊拓樸中的領機，準確率 87.1%",  c:BLUE   },
    { n:"05", title:"AI 整合 vs 傳統防空",    sub:"同場景對比 · 突防 16 → 0 架 · AI 全面優勝",     c:RED    },
  ];

  // ── 5 張章節大標 ─────────────────────────────────────────────
  for (const ch of chapters) {
    const s = pres.addSlide();
    s.background = { color: BG };

    // 水平裝飾線（居中偏下）
    s.addShape(pres.shapes.RECTANGLE, {
      x:1.0, y:3.40, w:8.0, h:0.03,
      fill:{ color:ch.c, transparency:60 }, line:{ color:ch.c, pt:0 }
    });

    // 數字徽章
    s.addShape(pres.shapes.OVAL, {
      x:4.56, y:0.60, w:0.88, h:0.88,
      fill:{ color:ch.c }, line:{ color:ch.c }
    });
    s.addText(ch.n, {
      x:4.56, y:0.60, w:0.88, h:0.88,
      fontSize:20, bold:true, color:BG,
      fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });

    // 大標題
    s.addText(ch.title, {
      x:0.5, y:1.60, w:9.0, h:1.10,
      fontSize:40, bold:true, color:FG,
      fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });

    // 副標
    s.addText(ch.sub, {
      x:0.5, y:2.82, w:9.0, h:0.46,
      fontSize:14, color:MUTED,
      fontFace:"Calibri", align:"center", margin:0
    });
  }

  // ── 感謝聆聽 ────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addText("感謝聆聽", {
      x:0.5, y:1.40, w:9.0, h:1.30,
      fontSize:60, bold:true, color:GOLD,
      fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });

    s.addText("Thanks for Listening", {
      x:0.5, y:2.80, w:9.0, h:0.52,
      fontSize:22, color:MUTED,
      fontFace:"Calibri", align:"center", margin:0
    });

    // 分隔線
    s.addShape(pres.shapes.RECTANGLE, {
      x:3.5, y:3.44, w:3.0, h:0.03,
      fill:{ color:GOLD }, line:{ color:GOLD, pt:0 }
    });

    s.addText("無人機機群攻防模擬系統", {
      x:0.5, y:3.62, w:9.0, h:0.38,
      fontSize:13, color:MUTED,
      fontFace:"Calibri", align:"center", margin:0
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
})();
