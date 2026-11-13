// The kit's stylesheet. Pure data, no imports, so node tests can read it.
//
// Rules this file keeps:
//  - Colors come only from the app's theme variables (--ui-*, --dt-*, --radius-*), with
//    fallbacks that are themselves variables, keywords or color-mix() of them. No hex.
//  - Text is full contrast: every word is --hk-ink. State shows through fills, borders,
//    icons and position, never by dimming text.
//  - Tone text colors (good, warn, bad, info) are the theme's tone mixed toward the text
//    color, so they stay legible on light and dark skins (the agent-log method).
//  - Type at the app's density: 13px body, 12px small, 11px labels, 20px largest heading.
//  - Motion: 120-160ms transitions; fade-rise, pulse, shimmer and the working arc are
//    the only animations, and all of them stop under prefers-reduced-motion.

export const KIT_VERSION = '0.1.0'

export const KIT_CSS = `
.hk{
  --hk-ink:var(--ui-text-primary,currentColor);
  --hk-accent:var(--ui-accent,var(--dt-primary,currentColor));
  --hk-bg:var(--ui-bg-chrome,transparent);
  --hk-surface:var(--ui-bg-elevated,var(--dt-card,transparent));
  --hk-sunken:var(--ui-bg-tertiary,var(--ui-bg-quaternary,color-mix(in srgb,var(--hk-ink) 7%,transparent)));
  --hk-stroke:var(--ui-stroke-secondary,color-mix(in srgb,var(--hk-ink) 14%,transparent));
  --hk-stroke-strong:var(--ui-stroke-primary,color-mix(in srgb,var(--hk-ink) 26%,transparent));
  --hk-hover:var(--ui-row-hover-background,color-mix(in srgb,var(--hk-ink) 5%,transparent));
  --hk-active:var(--ui-row-active-background,color-mix(in srgb,var(--hk-accent) 14%,transparent));
  --hk-good-fill:var(--ui-success,var(--ui-green,var(--hk-accent)));
  --hk-warn-fill:var(--ui-yellow,var(--ui-orange,var(--hk-accent)));
  --hk-bad-fill:var(--dt-destructive,var(--ui-red,var(--hk-accent)));
  --hk-info-fill:var(--hk-accent);
  --hk-idle-fill:color-mix(in srgb,var(--hk-ink) 32%,transparent);
  --hk-good:color-mix(in srgb,var(--hk-good-fill) 70%,var(--hk-ink));
  --hk-warn:color-mix(in srgb,var(--hk-warn-fill) 70%,var(--hk-ink));
  --hk-bad:color-mix(in srgb,var(--hk-bad-fill) 70%,var(--hk-ink));
  --hk-info:color-mix(in srgb,var(--hk-info-fill) 76%,var(--hk-ink));
  --hk-radius:var(--radius-md,6px);
  --hk-radius-sm:var(--radius-sm,4px);
  --hk-fs-xs:11px;--hk-fs-sm:12px;--hk-fs:13px;--hk-fs-h3:13px;--hk-fs-h2:15px;--hk-fs-h1:20px;
  --hk-mono:var(--font-mono,var(--dt-font-mono,ui-monospace,Menlo,monospace));
  --hk-dur:140ms;--hk-ease:cubic-bezier(.2,.7,.2,1);
  --hk-tone-fill:var(--hk-info-fill);--hk-tone:var(--hk-info);
  color:var(--hk-ink);font-size:var(--hk-fs);line-height:1.5;
}
.hk [data-tone=good],.hk[data-tone=good]{--hk-tone-fill:var(--hk-good-fill);--hk-tone:var(--hk-good)}
.hk [data-tone=warn],.hk[data-tone=warn]{--hk-tone-fill:var(--hk-warn-fill);--hk-tone:var(--hk-warn)}
.hk [data-tone=bad],.hk[data-tone=bad]{--hk-tone-fill:var(--hk-bad-fill);--hk-tone:var(--hk-bad)}
.hk [data-tone=info],.hk[data-tone=info]{--hk-tone-fill:var(--hk-info-fill);--hk-tone:var(--hk-info)}
.hk [data-tone=idle],.hk[data-tone=idle]{--hk-tone-fill:var(--hk-idle-fill);--hk-tone:var(--hk-ink)}
.hk *,.hk *::before,.hk *::after{box-sizing:border-box}
.hk p{margin:0}

/* page */
.hk-page{height:100%;min-height:0;overflow:auto;background:var(--hk-bg);outline:none}
.hk-page-inner{margin:0 auto;padding:18px 24px 40px;display:grid;gap:14px;align-content:start;max-width:1040px}
.hk-page[data-width=narrow] .hk-page-inner{max-width:760px}
.hk-page[data-width=full] .hk-page-inner{max-width:none}
.hk-head{display:grid;gap:4px}
.hk-head-row{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.hk-h1{font-size:var(--hk-fs-h1);line-height:1.25;font-weight:600;letter-spacing:-.01em;margin:0}
.hk-h2{font-size:var(--hk-fs-h2);line-height:1.3;font-weight:600;margin:0}
.hk-h3{font-size:var(--hk-fs-h3);line-height:1.35;font-weight:600;margin:0}
.hk-lead{font-size:var(--hk-fs);max-width:72ch}
.hk-small{font-size:var(--hk-fs-sm)}
.hk-eyebrow{font-size:var(--hk-fs-xs);font-weight:600;letter-spacing:.02em;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.hk-mono{font-family:var(--hk-mono);font-size:var(--hk-fs-sm)}
.hk-ink{color:var(--hk-ink)}
.hk-grow{flex:1;min-width:0}
.hk-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hk-stack{display:grid;gap:8px;align-content:start;min-width:0}
.hk-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.hk-split{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;align-items:start}
@container (max-width:820px){.hk-split{grid-template-columns:1fr}}
.hk-page{container-type:inline-size}
.hk-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:10px}

/* section */
.hk-section{display:grid;gap:8px;min-width:0}
.hk-section-head{display:flex;align-items:center;gap:8px;min-height:24px}
.hk-count{font-size:var(--hk-fs-xs);font-weight:600;font-variant-numeric:tabular-nums;padding:0 6px;border-radius:999px;background:var(--hk-sunken);line-height:18px}

/* card */
.hk-card{background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--hk-radius);padding:12px 14px;display:grid;gap:8px;min-width:0;
  transition:border-color var(--hk-dur) var(--hk-ease),background-color var(--hk-dur) var(--hk-ease)}
.hk-card[data-tone]{border-left:3px solid var(--hk-tone-fill)}
.hk-card[data-tint]{background:color-mix(in srgb,var(--hk-tone-fill) 6%,var(--hk-surface))}
.hk-card[data-flush]{padding:0;gap:0;overflow:hidden}
.hk-card-click{cursor:pointer;text-align:left;font:inherit;color:inherit;width:100%}
.hk-card-click:hover{border-color:var(--hk-stroke-strong);background:color-mix(in srgb,var(--hk-hover) 60%,var(--hk-surface))}
.hk-card-click:focus-visible,.hk-focus:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.hk-card[data-active]{border-color:var(--hk-accent);box-shadow:inset 0 0 0 1px var(--hk-accent)}

/* stat */
.hk-stat{display:grid;gap:0;min-width:0}
.hk-stat-label{font-size:var(--hk-fs-xs);font-weight:600}
.hk-stat-value{font-size:var(--hk-fs-h1);font-weight:600;line-height:1.2;font-variant-numeric:tabular-nums}
.hk-stat-sub{font-size:var(--hk-fs-sm)}
.hk-stat[data-tone] .hk-stat-value{color:var(--hk-tone)}

/* pill */
.hk-pill{display:inline-flex;align-items:center;gap:4px;font-size:var(--hk-fs-xs);font-weight:600;line-height:16px;padding:1px 7px;border-radius:999px;white-space:nowrap;color:var(--hk-ink);
  border:1px solid color-mix(in srgb,var(--hk-tone-fill) 42%,transparent);background:color-mix(in srgb,var(--hk-tone-fill) 13%,transparent)}
.hk-pill .codicon{color:var(--hk-tone)}
.hk-pill-dot{width:6px;height:6px;border-radius:50%;background:var(--hk-tone-fill);flex:none}

/* meter */
.hk-meter{display:grid;gap:4px;min-width:0}
.hk-meter-row{display:flex;justify-content:space-between;gap:8px;font-size:var(--hk-fs-sm)}
.hk-meter-track{height:4px;border-radius:2px;background:var(--hk-sunken);overflow:hidden}
.hk-meter-fill{height:100%;border-radius:2px;background:var(--hk-tone-fill);transition:width 160ms var(--hk-ease)}

/* stepper */
.hk-stepper{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(var(--hk-n),minmax(0,1fr));gap:6px;position:relative;--hk-node:30px}
.hk-stepper[data-compact]{--hk-node:22px}
.hk-step-rail{position:absolute;left:0;right:0;top:calc(var(--hk-node) / 2 - 1px);height:2px;width:100%;overflow:visible;pointer-events:none}
.hk-step-rail line{stroke:currentColor;stroke-width:2;vector-effect:non-scaling-stroke}
.hk-step-rail .hk-rail-later{color:var(--hk-stroke)}
.hk-step-rail .hk-rail-past{color:var(--hk-good-fill)}
.hk-step{display:flex;flex-direction:column;align-items:center;text-align:center;gap:5px;position:relative;min-width:0}
.hk-step-node{position:relative;width:var(--hk-node);height:var(--hk-node);border-radius:50%;display:grid;place-items:center;background:var(--hk-surface);border:1.5px solid var(--hk-stroke-strong);color:var(--hk-ink);
  transition:background-color var(--hk-dur) var(--hk-ease),border-color var(--hk-dur) var(--hk-ease)}
.hk-step[data-state=past] .hk-step-node{border-color:var(--hk-good-fill);background:color-mix(in srgb,var(--hk-good-fill) 16%,var(--hk-surface));color:var(--hk-good)}
.hk-step[data-state=now] .hk-step-node{border-color:var(--hk-tone-fill);background:color-mix(in srgb,var(--hk-tone-fill) 18%,var(--hk-surface));color:var(--hk-tone);box-shadow:0 0 0 3px color-mix(in srgb,var(--hk-tone-fill) 16%,transparent)}
.hk-step-title{font-size:var(--hk-fs-sm);font-weight:600;line-height:1.3}
.hk-stepper[data-compact] .hk-step-title{font-size:var(--hk-fs-xs)}
.hk-step[data-state=now] .hk-step-title{color:var(--hk-tone)}
.hk-step-line{font-size:var(--hk-fs-sm);max-width:26ch}

/* ring, sparkline, heat strip */
.hk-ring{display:inline-grid;place-items:center;position:relative;flex:none}
.hk-ring svg{display:block;transform:rotate(-90deg)}
.hk-ring-track{stroke:currentColor;stroke-opacity:.16;fill:none}
.hk-ring-arc{stroke:currentColor;fill:none;stroke-linecap:round;transition:stroke-dashoffset 160ms var(--hk-ease)}
.hk-ring[data-tone]{color:var(--hk-tone-fill)}
.hk-ring-label{position:absolute;inset:0;display:grid;place-items:center;font-size:var(--hk-fs-xs);font-weight:600;color:var(--hk-ink);font-variant-numeric:tabular-nums}
.hk-spark{display:block;overflow:visible;color:var(--hk-tone-fill)}
.hk-spark path{fill:none;stroke:currentColor;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.hk-spark .hk-spark-area{fill:currentColor;fill-opacity:.12;stroke:none}
.hk-heat{display:block;overflow:visible}
.hk-heat rect{fill:currentColor;transition:stroke-width var(--hk-dur) var(--hk-ease)}
.hk-heat .hk-cell-pass{color:var(--hk-good-fill)}
.hk-heat .hk-cell-fail{color:var(--hk-bad-fill)}
.hk-heat .hk-cell-unsure{color:var(--hk-warn-fill)}
.hk-heat .hk-cell-wait{color:transparent;stroke:var(--hk-stroke-strong);stroke-dasharray:2 2}
.hk-heat .hk-cell-pick{cursor:pointer}
.hk-heat .hk-cell-pick:focus{outline:none}
.hk-heat .hk-cell-pick:focus-visible,.hk-heat .hk-cell-sel{stroke:var(--hk-ink);stroke-width:2;stroke-dasharray:none}

/* states */
.hk-skel{display:block;border-radius:var(--hk-radius-sm);background:var(--hk-sunken);min-height:10px;
  background-image:linear-gradient(90deg,transparent 0,color-mix(in srgb,var(--hk-ink) 7%,transparent) 50%,transparent 100%);background-size:200% 100%;background-repeat:no-repeat;animation:hk-shimmer 1.4s linear infinite}
.hk-skel-line{height:10px}
.hk-skel-title{height:14px;width:42%}
.hk-skel-dot{width:22px;height:22px;border-radius:50%}
.hk-skel-btn{height:26px;width:96px}
.hk-state{display:grid;gap:12px;justify-items:center;padding:24px 8px}
.hk-state-body{max-width:56ch;text-align:center;color:var(--hk-ink)}
.hk-notice{display:flex;gap:8px;align-items:flex-start;padding:8px 10px;border-radius:var(--hk-radius-sm);border-left:3px solid var(--hk-tone-fill);background:color-mix(in srgb,var(--hk-tone-fill) 9%,transparent);font-size:var(--hk-fs-sm)}
.hk-notice>.codicon{color:var(--hk-tone);margin-top:2px}
.hk-banner{display:flex;gap:12px;align-items:flex-start}
.hk-badge-icon{flex:none;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:color-mix(in srgb,var(--hk-tone-fill) 16%,transparent);color:var(--hk-tone)}

/* disclosure, fields, facts, keys */
.hk-disclose{display:inline-flex;align-items:center;gap:6px;background:none;border:0;padding:2px 0;color:var(--hk-ink);font:inherit;font-size:var(--hk-fs-sm);font-weight:600;cursor:pointer;border-radius:var(--hk-radius-sm)}
.hk-disclose:hover{color:var(--hk-accent)}
.hk-disclose:focus-visible,.hk-link:focus-visible,.hk-back:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.hk-disclose-body{padding:6px 0 0 18px;display:grid;gap:6px}
.hk-link,.hk-back{display:inline-flex;align-items:center;gap:5px;background:none;border:0;padding:0;color:var(--hk-accent);cursor:pointer;font:inherit;font-size:var(--hk-fs-sm);text-align:left;border-radius:var(--hk-radius-sm)}
.hk-link:hover{text-decoration:underline}
.hk-back{justify-self:start;color:var(--hk-ink);font-weight:500}
.hk-back:hover{color:var(--hk-accent)}
.hk-field{display:grid;gap:4px;min-width:0}
.hk-field-label{font-size:var(--hk-fs-sm);font-weight:600}
.hk-field-hint{font-size:var(--hk-fs-sm)}
.hk-check{display:flex;gap:8px;align-items:center;font-size:var(--hk-fs-sm);cursor:pointer}
.hk-facts{display:grid;grid-template-columns:minmax(90px,max-content) 1fr;gap:4px 14px;margin:0;font-size:var(--hk-fs-sm)}
.hk-facts dt{font-weight:600}
.hk-facts dd{margin:0;min-width:0;overflow-wrap:anywhere}
.hk-keys{display:inline-flex;align-items:center;gap:4px;font-size:var(--hk-fs-xs)}
.hk-list{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.hk-list-rows{gap:0}
.hk-li{border-radius:var(--hk-radius-sm)}
.hk-li[data-active]>.hk-card,.hk-li[data-active].hk-card{border-color:var(--hk-accent)}
.hk-rowbtn{display:flex;gap:10px;align-items:center;width:100%;padding:7px 8px;border:0;border-radius:var(--hk-radius-sm);background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer;
  transition:background-color var(--hk-dur) var(--hk-ease)}
.hk-rowbtn:hover{background:var(--hk-hover)}
.hk-rowbtn[data-active]{background:var(--hk-active);box-shadow:inset 2px 0 0 var(--hk-accent)}
.hk-rowbtn:focus-visible{outline:2px solid var(--hk-accent);outline-offset:-2px}
.hk-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* motion */
@keyframes hk-fade-rise{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes hk-shimmer{from{background-position:150% 0}to{background-position:-50% 0}}
@keyframes hk-pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--hk-tone-fill) 50%,transparent)}100%{box-shadow:0 0 0 8px transparent}}
@keyframes hk-spin{to{transform:rotate(360deg)}}
.hk-enter{animation:hk-fade-rise 160ms var(--hk-ease) both}
.hk-enter-list>*{animation:hk-fade-rise 160ms var(--hk-ease) both}
.hk-enter-list>*:nth-child(2){animation-delay:30ms}.hk-enter-list>*:nth-child(3){animation-delay:60ms}.hk-enter-list>*:nth-child(n+4){animation-delay:90ms}
.hk-pulse{animation:hk-pulse 700ms ease-out 2}
.hk-pulse-live{animation:hk-pulse 1.8s ease-out infinite}
.hk-arc{position:absolute;inset:-4px;border-radius:50%;pointer-events:none;
  background:conic-gradient(from 0deg,var(--hk-tone-fill) 0 22%,transparent 22% 100%);
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),black calc(100% - 1.5px));mask:radial-gradient(farthest-side,transparent calc(100% - 2px),black calc(100% - 1.5px));
  animation:hk-spin 1.1s linear infinite}
.hk-spinner{width:12px;height:12px;border-radius:50%;border:1.5px solid color-mix(in srgb,currentColor 30%,transparent);border-top-color:currentColor;animation:hk-spin .8s linear infinite;flex:none}
.hk[data-motion=off] *,.hk[data-motion=off]{animation:none !important;transition:none !important}
@media (prefers-reduced-motion:reduce){.hk *,.hk{animation:none !important;transition:none !important}}
`
