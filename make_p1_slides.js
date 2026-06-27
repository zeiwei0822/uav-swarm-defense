// make_p1_slides.js — 要點1 影片投影片 × 2
// run: node make_p1_slides.js (from npm global dir, or set NODE_PATH)
"use strict";
const pptxgen = require("pptxgenjs");
const path = require("path");

const BASE = String.raw`C:\Users\User\Desktop\UAV\slides_p1`;
const OUT  = String.raw`C:\Users\User\Desktop\UAV\UAV_要點1_影片.pptx`;

const BG      = "0A0E14";   // 深黑（和模擬地圖同色）
const GOLD    = "FFD700";   // 金色（領機色）
const FG      = "E6EDF3";   // 主文字白
const MUTED   = "8AA0B5";   // 次要文字藍灰

const SLIDES = [
  {
    num : "1",
    title  : "向心多弧包圍（Encircle）",
    sub    : "三弧前排率先犧牲　×　傳統防空顧此失彼",
    video  : path.join(BASE, "p1_1_encircle_v2.mp4"),
  },
  {
    num : "2",
    title  : "重疊錐形＋誘餌（Arrowhead + Decoys）",
    sub    : "6 架誘餌全速衝前　×　傳統彈藥耗在誘餌上",
    video  : path.join(BASE, "p1_2_decoys_v2.mp4"),
  },
];

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";   // 10 × 5.625 inch
  pres.title  = "要點1 陣型突防影片";

  for (const s of SLIDES) {
    const slide = pres.addSlide();
    slide.background = { color: BG };

    // ── 編號圓圈 ──────────────────────────────────────────
    slide.addShape(pres.shapes.OVAL, {
      x: 0.25, y: 0.12, w: 0.48, h: 0.48,
      fill: { color: GOLD },
      line: { color: GOLD },
    });
    slide.addText(s.num, {
      x: 0.25, y: 0.12, w: 0.48, h: 0.48,
      align: "center", valign: "middle",
      fontSize: 20, bold: true,
      color: "0A0E14", margin: 0,
    });

    // ── 標題 ─────────────────────────────────────────────
    slide.addText(s.title, {
      x: 0.84, y: 0.13, w: 8.7, h: 0.45,
      fontSize: 22, bold: true, color: FG,
      fontFace: "Calibri", valign: "middle", margin: 0,
    });

    // ── 副標題 ───────────────────────────────────────────
    slide.addText(s.sub, {
      x: 0.84, y: 0.56, w: 8.7, h: 0.28,
      fontSize: 13, color: MUTED,
      fontFace: "Calibri", valign: "top", margin: 0,
    });

    // ── 影片（佔下方大部份空間）─────────────────────────
    // 影片寬高比 ≈ 15:8.5 ≈ 1.765；在 9.5" 寬下高 ≈ 5.38" → 壓到 4.6"
    slide.addMedia({
      type : "video",
      path : s.video,
      x    : 0.25,
      y    : 0.9,
      w    : 9.5,
      h    : 4.65,
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
}

main().catch(e => { console.error(e); process.exit(1); });
