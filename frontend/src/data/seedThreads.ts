import {
  ArtifactKind,
  ChatThread,
  ProjectDoc,
  StepStatus,
} from "../types/agent";

export const INITIAL_PROJECT_DOCS: ProjectDoc[] = [
  {
    id: "doc-brand-voice",
    title: "Editorial & Visual Principles",
    content:
      "Prefer calm, tactile typography (Lora headings paired with Plus Jakarta Sans prose), warm stone and clay surfaces, high-contrast espresso text, and clear quantitative reasoning without jargon.",
  },
];

const FOREST_RAIN_ARTIFACT_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Forest Rain Soundscape & Breath Timer</title>
  <style>
    :root {
      --bg: #EFE8DD;
      --surface: #F9F5EE;
      --card: #DECFC0;
      --text: #4A2B24;
      --muted: #8C7566;
      --accent: #59201A;
      --warm: #C59B7B;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .studio {
      width: 100%;
      max-width: 440px;
      background: var(--surface);
      border: 1px solid #DFD4C6;
      border-radius: 24px;
      padding: 28px;
    }
    .kicker {
      font-size: 11px;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 8px;
    }
    h1 {
      font-family: Georgia, serif;
      font-weight: 500;
      font-size: 28px;
      color: #5C2C23;
      margin-bottom: 6px;
    }
    .intention {
      font-size: 14px;
      line-height: 1.55;
      color: var(--text);
      opacity: 0.85;
      margin-bottom: 24px;
    }
    .ring-wrap {
      position: relative;
      height: 180px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(160deg, #E8DDD0 0%, #D8C5B3 100%);
      border-radius: 20px;
      margin-bottom: 20px;
      overflow: hidden;
    }
    .breath-circle {
      width: 96px;
      height: 96px;
      border-radius: 50%;
      border: 1.5px solid rgba(89, 32, 26, 0.35);
      background: rgba(249, 245, 238, 0.55);
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: Georgia, serif;
      font-size: 15px;
      color: var(--accent);
      transition: transform 4s ease-in-out;
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
    }
    .timer {
      font-variant-numeric: tabular-nums;
      font-size: 14px;
      color: var(--muted);
    }
    button.play-btn {
      background: var(--accent);
      color: #FBF7F2;
      border: none;
      border-radius: 999px;
      padding: 10px 20px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.15s ease;
    }
    button.play-btn:hover { opacity: 0.9; }
    .slider-row {
      margin-top: 12px;
    }
    .slider-head {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
      font-variant-numeric: tabular-nums;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--warm);
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="studio">
    <div class="kicker">Ambient Soundscape · Interactive Studio</div>
    <h1>Forest Rain</h1>
    <p class="intention">Let each breath return you to what is already whole. Synthesized pink-noise rainfall with a 4-4-6 cadence pacer.</p>
    <div class="ring-wrap">
      <div class="breath-circle" id="pacer">Ready</div>
    </div>
    <div class="controls">
      <span class="timer" id="clock">30:00 remaining</span>
      <button class="play-btn" id="toggleBtn">Start Session</button>
    </div>
    <div class="slider-row">
      <div class="slider-head">
        <span>Rainfall density</span>
        <span id="rainVal">65%</span>
      </div>
      <input type="range" id="rainSlider" min="10" max="100" value="65" />
    </div>
  </div>
  <script>
    let ctx = null;
    let gainNode = null;
    let filterNode = null;
    let playing = false;
    let seconds = 1800;
    let timerId = null;
    let breathTimeout = null;

    const btn = document.getElementById('toggleBtn');
    const pacer = document.getElementById('pacer');
    const clock = document.getElementById('clock');
    const slider = document.getElementById('rainSlider');
    const rainVal = document.getElementById('rainVal');

    function formatTime(sec) {
      const m = String(Math.floor(sec / 60)).padStart(2, '0');
      const s = String(sec % 60).padStart(2, '0');
      return m + ':' + s + ' remaining';
    }

    function runBreathCycle() {
      if (!playing) return;
      pacer.textContent = 'Inhale';
      pacer.style.transition = 'transform 4s ease-in-out';
      pacer.style.transform = 'scale(1.42)';
      breathTimeout = setTimeout(() => {
        if (!playing) return;
        pacer.textContent = 'Hold';
        breathTimeout = setTimeout(() => {
          if (!playing) return;
          pacer.textContent = 'Exhale';
          pacer.style.transition = 'transform 6s ease-in-out';
          pacer.style.transform = 'scale(0.92)';
          breathTimeout = setTimeout(runBreathCycle, 6000);
        }, 4000);
      }, 4000);
    }

    function startAudio() {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const bufferSize = 2 * ctx.sampleRate;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const output = noiseBuffer.getChannelData(0);
      let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
      for (let i = 0; i < bufferSize; i++) {
        const white = Math.random() * 2 - 1;
        b0 = 0.99886 * b0 + white * 0.0555179;
        b1 = 0.99332 * b1 + white * 0.0750759;
        b2 = 0.96900 * b2 + white * 0.1538520;
        b3 = 0.86650 * b3 + white * 0.3104856;
        b4 = 0.55000 * b4 + white * 0.5329522;
        b5 = -0.7616 * b5 - white * 0.0168980;
        output[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.04;
        b6 = white * 0.115926;
      }
      const whiteNoise = ctx.createBufferSource();
      whiteNoise.buffer = noiseBuffer;
      whiteNoise.loop = true;

      filterNode = ctx.createBiquadFilter();
      filterNode.type = 'lowpass';
      filterNode.frequency.value = 400 + Number(slider.value) * 14;

      gainNode = ctx.createGain();
      gainNode.gain.value = (Number(slider.value) / 100) * 0.55;

      whiteNoise.connect(filterNode);
      filterNode.connect(gainNode);
      gainNode.connect(ctx.destination);
      whiteNoise.start(0);
    }

    btn.addEventListener('click', () => {
      if (!playing) {
        playing = true;
        btn.textContent = 'Pause Session';
        startAudio();
        runBreathCycle();
        timerId = setInterval(() => {
          seconds = Math.max(0, seconds - 1);
          clock.textContent = formatTime(seconds);
        }, 1000);
      } else {
        playing = false;
        btn.textContent = 'Resume Session';
        pacer.textContent = 'Paused';
        pacer.style.transform = 'scale(1)';
        clearInterval(timerId);
        clearTimeout(breathTimeout);
        if (ctx) { ctx.close(); ctx = null; }
      }
    });

    slider.addEventListener('input', () => {
      rainVal.textContent = slider.value + '%';
      if (gainNode && filterNode) {
        gainNode.gain.value = (Number(slider.value) / 100) * 0.55;
        filterNode.frequency.value = 400 + Number(slider.value) * 14;
      }
    });
  </script>
</body>
</html>`;

const COHORT_CHART_ARTIFACT_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Net Revenue Retention Model</title>
  <style>
    body {
      background: #F9F5EE;
      color: #4A2B24;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      padding: 28px;
      margin: 0;
    }
    .header { margin-bottom: 22px; }
    .meta { font-size: 12px; color: #8C7566; margin-bottom: 6px; }
    h2 { font-family: Georgia, serif; font-weight: 500; font-size: 22px; margin: 0 0 6px; color: #5C2C23; }
    .controls {
      display: flex;
      gap: 20px;
      padding: 16px;
      background: #EFE8DD;
      border-radius: 14px;
      margin-bottom: 22px;
    }
    .field { flex: 1; }
    label { display: flex; justify-content: space-between; font-size: 12px; color: #5C2C23; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
    input[type="range"] { width: 100%; accent-color: #59201A; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
    th { text-align: left; padding: 10px 8px; border-bottom: 1px solid #CBBBA8; color: #8C7566; font-weight: 500; }
    th.num, td.num { text-align: right; }
    td { padding: 10px 8px; border-bottom: 1px solid #DFD4C6; }
    .bar-bg { width: 100%; height: 8px; background: #EAE1D5; border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; background: #C59B7B; border-radius: 4px; transition: width 0.2s ease; }
  </style>
</head>
<body>
  <div class="header">
    <div class="meta">Cohort Simulation · 12-Month Projection</div>
    <h2>Subscription Expansion vs. Churn Sensitivity</h2>
  </div>
  <div class="controls">
    <div class="field">
      <label><span>Monthly Gross Churn</span><strong id="churnOut">1.8%</strong></label>
      <input type="range" id="churn" min="0.5" max="5.0" step="0.1" value="1.8" />
    </div>
    <div class="field">
      <label><span>Monthly Seat Expansion</span><strong id="expOut">2.6%</strong></label>
      <input type="range" id="exp" min="0.5" max="6.0" step="0.1" value="2.6" />
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Quarter</th>
        <th class="num">Retained ARR</th>
        <th class="num">Net NRR</th>
        <th style="width: 34%; padding-left: 16px;">Trajectory</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <script>
    const churnEl = document.getElementById('churn');
    const expEl = document.getElementById('exp');
    const churnOut = document.getElementById('churnOut');
    const expOut = document.getElementById('expOut');
    const rowsEl = document.getElementById('rows');

    function render() {
      const c = parseFloat(churnEl.value) / 100;
      const e = parseFloat(expEl.value) / 100;
      churnOut.textContent = churnEl.value + '%';
      expOut.textContent = expEl.value + '%';

      let arr = 100000;
      const quarters = [3, 6, 9, 12];
      let html = '';
      for (let m = 1; m <= 12; m++) {
        arr = arr * (1 - c + e);
        if (quarters.includes(m)) {
          const nrr = (arr / 1000).toFixed(1);
          const pctWidth = Math.min(100, Math.max(15, (arr / 145000) * 100));
          html += '<tr>' +
            '<td>Month ' + m + ' (Q' + (m / 3) + ')</td>' +
            '<td class="num">$' + Math.round(arr).toLocaleString() + '</td>' +
            '<td class="num">' + nrr + '%</td>' +
            '<td style="padding-left:16px;"><div class="bar-bg"><div class="bar-fill" style="width:' + pctWidth + '%"></div></div></td>' +
          '</tr>';
        }
      }
      rowsEl.innerHTML = html;
    }
    churnEl.addEventListener('input', render);
    expEl.addEventListener('input', render);
    render();
  </script>
</body>
</html>`;

const SLEEP_COHERENCE_ARTIFACT_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Sleep Coherence & Cortisol Telemetry</title>
  <style>
    body {
      background: #F9F5EE;
      color: #4A2B24;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      padding: 24px;
      margin: 0;
    }
    .header { margin-bottom: 20px; }
    .kicker { font-size: 11px; letter-spacing: 0.08em; color: #8C7566; text-transform: uppercase; font-weight: 600; }
    h2 { font-family: Georgia, serif; font-size: 20px; color: #5C2C23; margin: 4px 0 16px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
    .stat-card { background: #EFE8DD; padding: 14px; border-radius: 14px; border: 1px solid #DFD4C6; }
    .stat-val { font-size: 22px; font-weight: 600; color: #59201A; font-variant-numeric: tabular-nums; }
    .stat-lbl { font-size: 11px; color: #8C7566; margin-top: 4px; }
    .chart-box { background: #FFFFFF; border: 1px solid #DFD4C6; border-radius: 16px; padding: 18px; }
    .bar-row { display: flex; align-items: center; gap: 12px; margin: 10px 0; font-size: 12px; }
    .bar-lbl { width: 140px; color: #4A2B24; font-weight: 500; }
    .bar-track { flex: 1; height: 18px; background: #EAE1D5; border-radius: 8px; overflow: hidden; display: flex; }
    .bar-fill { height: 100%; border-radius: 8px; font-size: 11px; color: #FFF; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-variant-numeric: tabular-nums; font-weight: 500; }
    .bar-pink { background: #59201A; width: 84.8%; }
    .bar-ctrl { background: #C59B7B; width: 52.1%; }
  </style>
</head>
<body>
  <div class="header">
    <div class="kicker">Polysomnography Trial III · n=142 Cohort</div>
    <h2>Neuro-Acoustic Delta Coherence vs Control</h2>
  </div>
  <div class="grid">
    <div class="stat-card">
      <div class="stat-val">-38.2%</div>
      <div class="stat-lbl">Nocturnal Cortisol Spike</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">-9.4m</div>
      <div class="stat-lbl">Parasympathetic Onset</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">+23.4</div>
      <div class="stat-lbl">Restorative Sleep Score</div>
    </div>
  </div>
  <div class="chart-box">
    <div style="font-size: 12px; font-weight: 600; color: #5C2C23; margin-bottom: 12px;">Stage 3 NREM Delta-Wave Stability Index</div>
    <div class="bar-row">
      <div class="bar-lbl">Canopy Pink Noise</div>
      <div class="bar-track"><div class="bar-fill bar-pink">84.8 / 100</div></div>
    </div>
    <div class="bar-row">
      <div class="bar-lbl">Unfiltered Ambient</div>
      <div class="bar-track"><div class="bar-fill bar-ctrl">52.1 / 100</div></div>
    </div>
  </div>
</body>
</html>`;

export const SEED_THREADS: ChatThread[] = [
  {
    id: "thread-pdf-evidence-showcase",
    title: "Clinical Trial: Neuro-Acoustics & Delta Sleep.pdf",
    updatedAt: "2026-10-23T09:40:00.000Z",
    starred: true,
    messages: [
      {
        id: "msg-pe-1",
        role: "user",
        content:
          "What does the polysomnography telemetry say about canopy pink noise, and can you provide the exact page quote as evidence?",
        attachments: [
          {
            id: "att-trial-2025-pdf",
            name: "Clinical_Neuro_Acoustics_Trial_2025.pdf",
            mimeType: "application/pdf",
            sizeBytes: 2840000,
          },
        ],
        createdAt: "2026-10-23T09:39:10.000Z",
      },
      {
        id: "msg-pe-2",
        role: "assistant",
        createdAt: "2026-10-23T09:40:00.000Z",
        steps: [
          {
            id: "step-pe-1",
            kind: "thinking",
            title: "Reasoning through document evidence",
            detail:
              "Indexing Trial Phase III (n=142) nocturnal biometrics in Clinical_Neuro_Acoustics_Trial_2025.pdf. Extracting verified passages across acoustic filtering methodology (p. 14), primary cortisol biomarkers (p. 18), and 60-day polysomnography stability (p. 29).",
            status: StepStatus.Completed,
            durationMs: 780,
          },
          {
            id: "step-pe-2",
            kind: "evidence",
            title:
              "Cited PDF evidence · Clinical_Neuro_Acoustics_Trial_2025.pdf (3 passages, pp. 14, 18, 29)",
            detail:
              "Extracted 3 verified passages substantiating acoustic filter roll-off (p. 14), 38.2% cortisol reduction (p. 18), and 60-day habituation resistance (p. 29).",
            status: StepStatus.Completed,
            durationMs: 440,
          },
          {
            id: "step-pe-3",
            kind: "artifact",
            title: "Built artifact: Sleep Coherence & Delta Wave Trajectory",
            detail: "Polysomnography comparative telemetry chart\n64 lines of html",
            status: StepStatus.Completed,
            durationMs: 890,
          },
        ],
        artifacts: [
          {
            id: "art-showcase-pdf-doc",
            title: "Clinical_Neuro_Acoustics_Trial_2025.pdf · 3 Evidence Passages",
            kind: ArtifactKind.Document,
            language: "pdf",
            summary:
              "Extracted 3 verified passages from Clinical_Neuro_Acoustics_Trial_2025.pdf spanning filter methodology (p. 14), biomarker findings (p. 18), and longitudinal safety (p. 29).",
            content: `### Excerpt 1 (Page 14 · Section 3.2 · Spectral Shaping & Acoustic Attenuation)

> "Applying a second-order Butterworth low-pass filter at 850 Hz attenuated acoustic agitation while preserving the 1/f spectral density essential for thalamocortical gating."

*Significance: Establishes the acoustic engineering rationale for filtering canopy pink noise to prevent auditory exhaustion.*

---

### Excerpt 2 (Page 18 · Section 4.3 · Parasympathetic Activation & Canopy Pink Spectrum)

> "Continuous exposure to pink-noise canopy spectra (filtered with low-pass roll-off at 800–1,200 Hz) demonstrated a statistically significant 38.2% attenuation in nocturnal cortisol spikes and accelerated parasympathetic tone onset by 9.4 minutes relative to unfiltered ambient control."

*Significance: Primary biometric finding validating the 38.2% drop in stress hormones and accelerated heart-rate variability transitions.*

---

### Excerpt 3 (Page 29 · Section 6.1 · 60-Day Polysomnography Follow-Up & Neuroplasticity)

> "At 60 days post-intervention, 92.4% of participants retained elevated Stage 3 NREM power (mean delta amplitude 78.4 µV) with no evidence of acoustic dependency or habituation decay."

*Significance: Confirms long-term safety, tolerance, and enduring neuroplastic benefits without dependency.*`,
            documentMeta: {
              filename: "Clinical_Neuro_Acoustics_Trial_2025.pdf",
              authorOrSource:
                "Vanderbilt Sleep & Neuro-Acoustic Laboratory (Dr. E. Thorne, Dr. S. K. Vance et al.)",
              totalPages: 42,
              page: "14, 18, 29",
              snippets: [
                {
                  id: "snip-meth-14",
                  page: "14",
                  totalPages: 42,
                  sectionTitle:
                    "Section 3.2 · Spectral Shaping & Acoustic Attenuation",
                  contextBefore:
                    "Prior iterations of auditory masking protocols deployed unmodified white noise, inducing measurable prefrontal fatigue after prolonged exposure.",
                  highlightedSnippet:
                    "Applying a second-order Butterworth low-pass filter at 850 Hz attenuated acoustic agitation while preserving the 1/f spectral density essential for thalamocortical gating.",
                  contextAfter:
                    "Spectral density analysis confirmed that acoustic energy concentrated below 1 kHz prevents cortical micro-arousals without impeding ambient sound awareness.",
                  relevanceExplanation:
                    "Establishes the acoustic engineering rationale for filtering canopy pink noise to prevent auditory exhaustion.",
                },
                {
                  id: "snip-bio-18",
                  page: "18",
                  totalPages: 42,
                  sectionTitle:
                    "Section 4.3 · Parasympathetic Activation & Canopy Pink Spectrum",
                  contextBefore:
                    "Previous investigations into synthetic broadband masking revealed high-frequency acoustic fatigue after 45 minutes of exposure. In Trial Phase III (n=142), acoustic low-pass filtering was configured to match natural deciduous canopy rainfall.",
                  highlightedSnippet:
                    "Continuous exposure to pink-noise canopy spectra (filtered with low-pass roll-off at 800–1,200 Hz) demonstrated a statistically significant 38.2% attenuation in nocturnal cortisol spikes and accelerated parasympathetic tone onset by 9.4 minutes relative to unfiltered ambient control.",
                  contextAfter:
                    "Participant self-reported subjective rest scores increased from 61.4 to 84.8/100 (p < 0.001), while continuous EEG monitoring indicated stabilized delta-wave coherence during Stage 3 NREM cycles with zero reported auditory habituation resistance.",
                  relevanceExplanation:
                    "Primary biometric finding validating the 38.2% drop in stress hormones and accelerated heart-rate variability transitions.",
                },
                {
                  id: "snip-long-29",
                  page: "29",
                  totalPages: 42,
                  sectionTitle:
                    "Section 6.1 · 60-Day Polysomnography Follow-Up & Neuroplasticity",
                  contextBefore:
                    "A primary concern in long-term nocturnal stimulation protocols is neurological desensitization or rebound insomnia upon cessation.",
                  highlightedSnippet:
                    "At 60 days post-intervention, 92.4% of participants retained elevated Stage 3 NREM power (mean delta amplitude 78.4 µV) with no evidence of acoustic dependency or habituation decay.",
                  contextAfter:
                    "Polysomnography epoch scoring across consecutive sleep cycles demonstrated that neural synchronization induced by pink canopy noise produces enduring sleep architecture stabilization.",
                  relevanceExplanation:
                    "Confirms long-term safety, tolerance, and enduring neuroplastic benefits without dependency.",
                },
              ],
            },
            createdAt: "2026-10-23T09:39:48.000Z",
          },
          {
            id: "art-showcase-delta-chart",
            title: "Sleep Coherence & Delta Wave Trajectory",
            kind: ArtifactKind.Html,
            language: "html",
            summary:
              "Interactive biometric chart comparing canopy pink noise against ambient control across 142 clinical subjects.",
            content: SLEEP_COHERENCE_ARTIFACT_HTML,
            createdAt: "2026-10-23T09:39:55.000Z",
          },
        ],
        content: `I reviewed \`Clinical_Neuro_Acoustics_Trial_2025.pdf\` across **3 distinct chapters** and extracted the verified text evidence:

1. **Acoustic Shaping (p. 14)**: The trial filtered pink noise using an \`850 Hz\` low-pass roll-off to retain the 1/f spectral density necessary for thalamocortical gating without causing cortical micro-arousals.
2. **Physiological Biomarkers (p. 18)**: Continuous canopy exposure achieved a **-38.2% reduction in nocturnal cortisol spikes** and accelerated parasympathetic tone onset by **9.4 minutes**.
3. **Enduring Neuroplasticity (p. 29)**: At 60 days follow-up, **92.4% of subjects** maintained elevated Stage 3 NREM delta power (\`78.4 µV\`) with zero acoustic habituation decay.

> **Multi-Snippet Evidence Workbench**: Click the **\`Clinical_Neuro_Acoustics_Trial_2025.pdf · 3 Evidence Passages\`** artifact card below to inspect all 3 verified snippets side-by-side with exact page numbers, highlighted quotes, and clinical rationale.`,
      },
    ],
  },
  {
    id: "thread-forest-rain",
    title: "Forest Rain Soundscape & Breath Pacer",
    updatedAt: "2026-10-23T08:12:00.000Z",
    starred: true,
    messages: [
      {
        id: "msg-fr-1",
        role: "user",
        content:
          "Design an interactive Forest Rain ambient soundscape & 4-4-6 mindful breathing widget styled in warm stone, travertine, and deep oxblood tones.",
        createdAt: "2026-10-23T08:11:10.000Z",
      },
      {
        id: "msg-fr-2",
        role: "assistant",
        createdAt: "2026-10-23T08:12:00.000Z",
        steps: [
          {
            id: "step-fr-1",
            kind: "thinking",
            title: "Reasoning through request",
            detail:
              "Synthesizing a zero-dependency Web Audio pink-noise generator with a low-pass filter so rainfall density feels warm rather than harsh, paired with a 4s inhale / 4s hold / 6s exhale visual pacer.",
            status: StepStatus.Completed,
            durationMs: 840,
          },
          {
            id: "step-fr-2",
            kind: "artifact",
            title: "Built artifact: Forest Rain Soundscape Studio",
            detail:
              "Interactive Web Audio pink-noise rainfall synthesizer and 4-4-6 breathing ring\n182 lines of html",
            status: StepStatus.Completed,
            durationMs: 1120,
          },
          {
            id: "step-fr-3",
            kind: "evidence",
            title: "Cited PDF evidence · Journal_Acoustic_Ecology_2025.pdf (p. 18)",
            detail:
              "Continuous exposure to pink-noise canopy spectra (filtered with low-pass roll-off at 800–1,200 Hz) demonstrated a statistically significant 38.2% attenuation in nocturnal cortisol spikes.",
            status: StepStatus.Completed,
            durationMs: 420,
          },
        ],
        artifacts: [
          {
            id: "art-forest-rain-v1",
            title: "Forest Rain Soundscape Studio",
            kind: ArtifactKind.Html,
            language: "html",
            summary:
              "Live Web Audio pink-noise rainfall generator with adjustable acoustic warmth and a 4-4-6 breath timer.",
            content: FOREST_RAIN_ARTIFACT_HTML,
            createdAt: "2026-10-23T08:11:58.000Z",
          },
          {
            id: "art-forest-rain-pdf-v1",
            title: "Journal_Acoustic_Ecology_2025.pdf · p. 18",
            kind: ArtifactKind.Document,
            language: "pdf",
            summary:
              "Peer-reviewed study confirming that canopy-filtered low-pass pink noise reduces nocturnal cortisol spikes by 38.2%.",
            content:
              "Continuous exposure to pink-noise canopy spectra (filtered with low-pass roll-off at 800–1,200 Hz) demonstrated a statistically significant 38.2% attenuation in nocturnal cortisol spikes and accelerated parasympathetic tone onset by 9.4 minutes relative to unfiltered ambient control.",
            documentMeta: {
              filename: "Journal_Acoustic_Ecology_2025.pdf",
              page: "18",
              totalPages: 42,
              authorOrSource:
                "Vanderbilt Neuro-Acoustic Laboratory (Dr. E. Thorne, Dr. S. K. Vance et al.)",
              sectionTitle:
                "Section 4.3 · Parasympathetic Activation & Canopy Pink Spectrum",
              highlightedSnippet:
                "Continuous exposure to pink-noise canopy spectra (filtered with low-pass roll-off at 800–1,200 Hz) demonstrated a statistically significant 38.2% attenuation in nocturnal cortisol spikes and accelerated parasympathetic tone onset by 9.4 minutes relative to unfiltered ambient control.",
              contextBefore:
                "Previous clinical trials investigating synthetic broadband white masking noted elevated high-frequency auditory fatigue after 45 minutes. In Trial Phase III (n=142), acoustic low-pass filtering was applied to recreate temperate canopy leaf diffusion.",
              contextAfter:
                "Participant self-reported restorative quality scores increased from 61.4 to 84.8/100, while sleep EEG demonstrated stabilized delta-wave coherence during Stage 3 NREM cycles.",
              relevanceExplanation:
                "Primary scientific evidence justifying the 400–1,800 Hz low-pass filter slope tuned into the Forest Rain soundscape engine.",
            },
            createdAt: "2026-10-23T08:12:02.000Z",
          },
        ],
        content: `I have built the **Forest Rain Soundscape Studio** in the Artifact Workbench. You can press **Start Session** directly inside the preview pane to hear live synthesized rainfall and follow the breathing cadence.

### Key Architectural Choices

- **Acoustic Warmth via Paul Kellet Pink-Noise Filtering**: Pure white noise sounds brittle at higher frequencies. Filtering pink noise through a tunable low-pass biquad node (\`400 Hz – 1,800 Hz\`) reproduces the soft acoustics of rain through canopy leaves.
- **4-4-6 Parasympathetic Cadence**: Extending the exhale phase (\`6s\`) relative to inhalation (\`4s\`) slows heart-rate variability gently without visual clutter.
- **Tactile Stone Palette**: Uses warm linen (\`#F9F5EE\`), travertine sand (\`#DECFC0\`), and deep oxblood-espresso (\`#59201A\`) for calm contrast.

> **Source Evidence**: Inspect the attached **\`Journal_Acoustic_Ecology_2025.pdf (p. 18)\`** in the Artifact Workbench for the peer-reviewed trial data validating the 38.2% cortisol reduction.`,
      },
    ],
  },
  {
    id: "thread-cohort-nrr",
    title: "Subscription NRR Sensitivity Model",
    updatedAt: "2026-10-22T17:40:00.000Z",
    starred: false,
    messages: [
      {
        id: "msg-nrr-1",
        role: "user",
        content:
          "Analyze our quarterly net revenue retention if starting ARR is $100k with 1.8% monthly gross churn and 2.6% seat expansion, and build an interactive sensitivity table.",
        createdAt: "2026-10-22T17:39:15.000Z",
      },
      {
        id: "msg-nrr-2",
        role: "assistant",
        createdAt: "2026-10-22T17:40:00.000Z",
        steps: [
          {
            id: "step-nrr-1",
            kind: "analysis",
            title: "Analyzed Quarterly ARR Trajectory · 4 rows",
            detail:
              '{\n  "label": "Quarterly ARR Trajectory",\n  "sum": 425164,\n  "mean": 106291,\n  "netChangePct": 7.42\n}',
            status: StepStatus.Completed,
            durationMs: 310,
          },
          {
            id: "step-nrr-2",
            kind: "artifact",
            title: "Built artifact: Subscription Expansion vs. Churn Sensitivity",
            detail: "Interactive 12-month NRR calculator with sliders\n96 lines of html",
            status: StepStatus.Completed,
            durationMs: 950,
          },
        ],
        artifacts: [
          {
            id: "art-cohort-nrr-v1",
            title: "Subscription Expansion vs. Churn Sensitivity",
            kind: ArtifactKind.Html,
            language: "html",
            summary:
              "Interactive 12-month ARR and Net Revenue Retention simulator with live churn and seat expansion sliders.",
            content: COHORT_CHART_ARTIFACT_HTML,
            createdAt: "2026-10-22T17:39:55.000Z",
          },
        ],
        content: `With a net monthly compound rate of **+0.8%** (\`2.6% expansion − 1.8% gross churn\`), a \`$100,000\` starting cohort reaches **\`$110,034\` ARR** (\`110.0% NRR\`) at Month 12.

| Milestone | Retained ARR | Net NRR | Monthly Net Delta |
| :--- | ---: | ---: | ---: |
| Month 3 (Q1) | $102,419 | 102.4% | +$813 / mo |
| Month 6 (Q2) | $104,897 | 104.9% | +$832 / mo |
| Month 9 (Q3) | $107,435 | 107.4% | +$853 / mo |
| Month 12 (Q4) | $110,034 | 110.0% | +$873 / mo |

Open the interactive simulator card to stress-test how a \`0.5%\` reduction in monthly churn compounds faster than equivalent top-of-funnel seat expansion.`,
      },
    ],
  },
];

export interface StarterPrompt {
  id: string;
  category: string;
  title: string;
  prompt: string;
}

export const STARTER_PROMPTS: StarterPrompt[] = [
  {
    id: "sp-interactive-ui",
    category: "Interactive Artifact",
    title: "Pomodoro & Acoustic Focus Desk",
    prompt:
      "Create an interactive Pomodoro focus timer and ambient brown-noise desk widget as an HTML artifact using our warm stone, clay, and deep oxblood palette.",
  },
  {
    id: "sp-web-research",
    category: "Live Web Research",
    title: "Frontend Bundler & Runtime Landscape",
    prompt:
      "Search the web for the latest developments in Vite, Rolldown, and modern TypeScript server runtimes, then synthesize a clear architectural comparison table with sources.",
  },
  {
    id: "sp-data-analysis",
    category: "Quantitative Analysis",
    title: "Unit Economics & Runway Stress Test",
    prompt:
      "Analyze this monthly burn vs MRR dataset: Jan $42k MRR, Feb $46.5k, Mar $51.2k, Apr $58.0k, May $63.4k, Jun $71.0k against a fixed $85k monthly burn. Compute exact growth stats and build an interactive runway chart artifact.",
  },
  {
    id: "sp-svg-architecture",
    category: "System Diagram",
    title: "Event-Driven Agent Architecture SVG",
    prompt:
      "Design a clean, publication-grade SVG architecture diagram illustrating a streaming multi-step AI agent loop with tool execution, grounding, and sandboxed artifact rendering.",
  },
  {
    id: "sp-concierge-hospitality",
    category: "Luxury Concierge",
    title: "Saint-Tropez Dining & Evening Itinerary",
    prompt:
      "Act as an ultra-luxury digital concierge for Hôtel Saint-Tropez. Prepare an intimate evening dining recommendation at La Vague d'Or with sea-view terrace reservations and a sunset private boat charter, formatted with an interactive reservation card artifact.",
  },
];
