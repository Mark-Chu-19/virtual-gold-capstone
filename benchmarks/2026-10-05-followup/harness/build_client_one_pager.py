"""
Client One-Pager Generator for Virtual Gold Privacy Redaction Benchmark.
Generates:
1. CLIENT_ONE_PAGER.docx (using python-docx)
2. CLIENT_ONE_PAGER.pdf (using HTML/CSS + Prince with automated 1-page verification)

Strictly adheres to:
- Exactly 1 US Letter page
- ~400-500 words total
- Plain client-facing language
- Explicit definitions of data leakage and over-redaction
- Clear distinction between local on-device inference vs. remote hosted API latency
- Prominent limitations and actionable next steps
- No claims of zero risk or declaring an absolute winning model
"""

import json
from pathlib import Path
import subprocess
import fitz  # PyMuPDF

WORKSPACE = Path("/Users/anmolsahu2k/Stuff/CMU/Acad/Sem3/Capstone")
BENCH_2026_10_05 = WORKSPACE / "virtual-gold-capstone/benchmarks/2026-10-05"
BENCH_FOLLOWUP = WORKSPACE / "virtual-gold-capstone/benchmarks/2026-10-05-followup"

def load_metrics():
    hist_path = BENCH_2026_10_05 / "results/corrected_summary_metrics.json"
    with open(hist_path) as f:
        hist_metrics = json.load(f)

    followup_path = BENCH_FOLLOWUP / "results/summary_metrics.json"
    followup_metrics = []
    if followup_path.exists():
        with open(followup_path) as f:
            followup_metrics = json.load(f)

    return hist_metrics, followup_metrics

def format_row(m):
    model = m["model"]
    stage = m["stage"]
    leak_rate = m["char_leak_rate"] * 100
    over_redact = m["char_over_redaction_rate"] * 100
    req_leak = m["request_leak_rate"] * 100
    
    if "baseline" in model:
        lat_str = "N/A*"
    else:
        lat = m["latency"]["median_s"]
        lat_str = f"{lat:.2f}s"

    return {
        "model": model,
        "stage": stage,
        "leak_rate": f"{leak_rate:.1f}%",
        "over_redact": f"{over_redact:.1f}%",
        "req_leak": f"{req_leak:.0f}%",
        "latency": lat_str
    }

def generate_pdf_html(table_rows, output_html_path: Path):
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: letter;
    margin: 0.38in 0.48in;
  }}
  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 8.4pt;
    line-height: 1.28;
    color: #1f2937;
    margin: 0;
    padding: 0;
  }}
  .header {{
    border-bottom: 2px solid #1e3a8a;
    padding-bottom: 4px;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .title-area h1 {{
    font-size: 13.5pt;
    font-weight: 700;
    color: #1e3a8a;
    margin: 0 0 2px 0;
    letter-spacing: -0.01em;
  }}
  .title-area .subtitle {{
    font-size: 8.2pt;
    color: #4b5563;
    font-weight: 500;
  }}
  .meta-area {{
    text-align: right;
    font-size: 7.5pt;
    color: #6b7280;
    line-height: 1.3;
  }}
  .meta-area strong {{
    color: #374151;
  }}
  
  .section {{
    margin-bottom: 6px;
  }}
  .section-title {{
    font-size: 9pt;
    font-weight: 700;
    color: #1e3a8a;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 1px;
    margin-bottom: 3px;
  }}
  
  p {{
    margin: 0 0 4px 0;
    text-align: justify;
  }}
  
  .highlight-box {{
    background-color: #f8fafc;
    border-left: 3px solid #3b82f6;
    padding: 4px 8px;
    margin-bottom: 6px;
    border-radius: 0 4px 4px 0;
    font-size: 8.1pt;
  }}
  .highlight-box strong {{
    color: #1e40af;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4px 0 6px 0;
    font-size: 7.8pt;
  }}
  th, td {{
    padding: 3.5px 5px;
    text-align: left;
    border-bottom: 1px solid #e5e7eb;
  }}
  th {{
    background-color: #f1f5f9;
    color: #1e293b;
    font-weight: 600;
    border-top: 1px solid #cbd5e1;
    border-bottom: 1.5px solid #94a3b8;
  }}
  td.num, th.num {{
    text-align: right;
  }}
  tr:nth-child(even) td {{
    background-color: #f8fafc;
  }}
  .tag {{
    display: inline-block;
    padding: 1px 4px;
    font-size: 6.8pt;
    font-weight: 600;
    border-radius: 3px;
  }}
  .tag-local {{ background-color: #dbeafe; color: #1e40af; }}
  .tag-hosted {{ background-color: #f3e8ff; color: #6b21a8; }}
  .tag-base {{ background-color: #f1f5f9; color: #475569; }}
  
  .grid-2 {{
    display: flex;
    gap: 10px;
    margin-bottom: 4px;
  }}
  .grid-col {{
    flex: 1;
  }}
  
  ul {{
    margin: 0 0 4px 0;
    padding-left: 14px;
  }}
  li {{
    margin-bottom: 2px;
  }}
  
  .footer-note {{
    font-size: 7.2pt;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    padding-top: 3px;
    margin-top: 4px;
  }}
</style>
</head>
<body>

  <div class="header">
    <div class="title-area">
      <h1>Virtual Gold: Privacy Redaction Findings Brief</h1>
      <div class="subtitle">Controlled Evaluation of Local & Hosted LLM Redaction Architectures</div>
    </div>
    <div class="meta-area">
      <strong>Date:</strong> October 5, 2026<br>
      <strong>Author:</strong> Model Architecture Workstream<br>
      <strong>Scope:</strong> 30 Synthetic Enterprise Documents
    </div>
  </div>

  <div class="section">
    <div class="section-title">Executive Purpose & Scope</div>
    <p>
      This brief evaluates whether local open-weight language models and privacy-preserving APIs can reliably redact sensitive enterprise data without compromising benign context. We tested candidate architectures across 30 multi-turn synthetic enterprise documents (10 development, 20 comparison) containing confidential personal identifiers, commercial secrets, and public corporate contact points.
    </p>
  </div>

  <div class="highlight-box">
    <strong>Core Architecture & Privacy Definitions:</strong><br>
    &bull; <strong>Data Leakage:</strong> Sensitive identifiers (e.g., personal cellphones, SSNs, executive targets) left unredacted and exposed downstream.<br>
    &bull; <strong>Over-Redaction:</strong> Unnecessary masking of public contact points (e.g., 1-800 support lines, official titles) needed for utility.<br>
    &bull; <strong>Two-Stage Design:</strong> Stage B uses a high-recall candidate union (Rules + Model). Stage C applies a second contextual assessment call to verify whether candidate spans are private or public, preventing over-redaction.
  </div>

  <div class="section">
    <div class="section-title">Benchmark Comparison on 20 Reused Test Documents</div>
    <table>
      <thead>
        <tr>
          <th>Model & Runtime Configuration</th>
          <th>Stage</th>
          <th class="num">Private Leakage</th>
          <th class="num">Over-Redaction</th>
          <th class="num">Leaked Reqs</th>
          <th class="num">Median Latency</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
    <div style="font-size: 7.2pt; color: #64748b; margin-top: -3px; margin-bottom: 5px;">
      *Baseline execution was deterministic local regex/Presidio with unmetered sub-millisecond latency. Hosted timings include cloud network and queue latency. Local timings reflect on-device Apple M4 execution.
    </div>
  </div>

  <div class="grid-2">
    <div class="grid-col">
      <div class="section-title">Key Empirical Findings</div>
      <ul>
        <li><strong>Recall vs. Precision Tradeoff:</strong> Stage B candidate union minimizes character leakage (24%–36%) but excessively redacts benign text (73%–87%). Stage C contextual assessment sharply curbs over-redaction (down to 3%–33%) at the cost of modest leakage increases.</li>
        <li><strong>Local Deployment Feasibility:</strong> Local Qwen 3.5 9B (Q4_K_M GGUF) runs entirely on-device with zero cloud data transmission, eliminating external egress risk while maintaining structured JSON adherence.</li>
        <li><strong>Reasoning & Prompt Dynamics:</strong> Cloud models with native reasoning require calibrated generation limits to avoid truncation. Local warm execution avoids cloud routing queues.</li>
      </ul>
    </div>
    <div class="grid-col">
      <div class="section-title">Prominent Limitations & Next Steps</div>
      <ul>
        <li><strong>Synthetic Scope:</strong> Evaluated on 30 standardized synthetic cases; production mailboxes feature greater stylistic and OCR noise.</li>
        <li><strong>Uncalibrated Confidence:</strong> Model confidence scores are raw heuristics; formal calibration (Platt scaling) is required before production gating.</li>
        <li><strong>No Zero-Risk Guarantee:</strong> No model achieved 0% leakage. High-tier identifiers require mandatory deterministic regex locks.</li>
        <li><strong>Next Steps:</strong> 1) Fit empirical calibration curves; 2) Tune tier thresholds with client compliance; 3) Test hybrid local-first routing.</li>
      </ul>
    </div>
  </div>

  <div class="footer-note">
    <strong>Confidentiality Notice:</strong> Benchmark conducted using verified synthetic documents only. No client files, meeting notes, or actual customer PII were used or transmitted.
  </div>

</body>
</html>"""
    output_html_path.write_text(html_content, encoding="utf-8")

def build_pdf(html_path: Path, pdf_path: Path):
    cmd = ["/usr/local/bin/prince", str(html_path), "-o", str(pdf_path)]
    subprocess.run(cmd, check=True)
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    doc.close()
    return page_count

def generate_docx(table_data, output_docx_path: Path):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(0.4)
        section.bottom_margin = Inches(0.4)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)
        section.page_width = Inches(8.5)
        section.page_height = Inches(11.0)

    def set_font(run, name="Calibri", size_pt=9.5, bold=False, italic=False, color_rgb=(31, 41, 55)):
        run.font.name = name
        run.font.size = Pt(size_pt)
        run.bold = bold
        run.italic = italic
        run.font.color.rgb = RGBColor(*color_rgb)

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(1)
    run_t = p_title.add_run("Virtual Gold: Privacy Redaction Findings Brief")
    set_font(run_t, name="Calibri", size_pt=14, bold=True, color_rgb=(30, 58, 138))

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(6)
    run_s = p_sub.add_run("Controlled Evaluation of Local & Hosted LLM Redaction Architectures  |  Date: October 5, 2026\nAuthor: Model Architecture Workstream  |  Scope: 30 Synthetic Enterprise Documents")
    set_font(run_s, name="Calibri", size_pt=8, italic=True, color_rgb=(75, 85, 99))

    p_p = doc.add_paragraph()
    p_p.paragraph_format.space_before = Pt(4)
    p_p.paragraph_format.space_after = Pt(4)
    run_h1 = p_p.add_run("EXECUTIVE PURPOSE & EXPERIMENT SCOPE\n")
    set_font(run_h1, size_pt=9.5, bold=True, color_rgb=(30, 58, 138))
    run_pb = p_p.add_run(
        "This brief evaluates whether local open-weight language models and privacy-preserving APIs can reliably redact sensitive enterprise data without compromising benign context. We evaluated candidate models across 30 multi-turn synthetic enterprise documents (10 development, 20 comparison) containing confidential personal identifiers, commercial secrets, and public corporate contact points."
    )
    set_font(run_pb, size_pt=8.5, color_rgb=(31, 41, 55))

    tbl_box = doc.add_table(rows=1, cols=1)
    tbl_box.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell_box = tbl_box.cell(0, 0)
    cell_box.width = Inches(7.5)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'F8FAFC')
    cell_box._tc.get_or_add_tcPr().append(shd)

    p_box = cell_box.paragraphs[0]
    p_box.paragraph_format.space_before = Pt(2)
    p_box.paragraph_format.space_after = Pt(2)
    r_bh = p_box.add_run("Core Architecture & Privacy Definitions:\n")
    set_font(r_bh, size_pt=8.5, bold=True, color_rgb=(30, 64, 175))
    r_bb = p_box.add_run(
        "• Data Leakage: Sensitive identifiers (personal phone numbers, SSNs, financial targets) left unmasked and exposed downstream.\n"
        "• Over-Redaction: Unnecessary masking of public contact channels (corporate 1-800 support lines, official titles) needed for utility.\n"
        "• Two-Stage Pipeline: Stage B applies a high-recall candidate union (Rules + Model). Stage C applies a second contextual assessment call to classify candidates as Private or Public, resolving over-redaction."
    )
    set_font(r_bb, size_pt=8, color_rgb=(55, 65, 81))

    p_th = doc.add_paragraph()
    p_th.paragraph_format.space_before = Pt(6)
    p_th.paragraph_format.space_after = Pt(2)
    r_th = p_th.add_run("BENCHMARK COMPARISON ON 20 REUSED COMPARISON DOCUMENTS")
    set_font(r_th, size_pt=9.5, bold=True, color_rgb=(30, 58, 138))

    tbl = doc.add_table(rows=len(table_data) + 1, cols=6)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Model & Runtime Configuration", "Stage", "Private Leakage", "Over-Redaction", "Leaked Reqs", "Median Latency"]
    col_widths = [Inches(2.5), Inches(0.7), Inches(1.1), Inches(1.1), Inches(1.0), Inches(1.1)]

    for col_idx, (h_text, w) in enumerate(zip(headers, col_widths)):
        cell = tbl.cell(0, col_idx)
        cell.width = w
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), 'F1F5F9')
        cell._tc.get_or_add_tcPr().append(shd)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col_idx >= 2 else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(h_text)
        set_font(r, size_pt=7.5, bold=True, color_rgb=(30, 41, 59))

    for row_idx, r_data in enumerate(table_data, start=1):
        for col_idx, (key, w) in enumerate(zip(["model", "stage", "leak_rate", "over_redact", "req_leak", "latency"], col_widths)):
            cell = tbl.cell(row_idx, col_idx)
            cell.width = w
            if row_idx % 2 == 0:
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), 'F8FAFC')
                cell._tc.get_or_add_tcPr().append(shd)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col_idx >= 2 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(1.5)
            p.paragraph_format.space_after = Pt(1.5)
            r = p.add_run(r_data[key])
            set_font(r, size_pt=7.5, color_rgb=(31, 41, 55))

    p_fn = doc.add_paragraph()
    p_fn.paragraph_format.space_before = Pt(1)
    p_fn.paragraph_format.space_after = Pt(4)
    r_fn = p_fn.add_run("*Baseline execution was deterministic local regex/Presidio with unmetered sub-millisecond latency. Hosted timings include cloud network and queue latency. Local timings reflect on-device Apple M4 execution.")
    set_font(r_fn, size_pt=7, italic=True, color_rgb=(100, 116, 139))

    tbl_cols = doc.add_table(rows=1, cols=2)
    tbl_cols.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell_left, cell_right = tbl_cols.cell(0, 0), tbl_cols.cell(0, 1)
    cell_left.width = Inches(3.7)
    cell_right.width = Inches(3.7)

    p_left = cell_left.paragraphs[0]
    p_left.paragraph_format.space_before = Pt(2)
    p_left.paragraph_format.space_after = Pt(2)
    r_lh = p_left.add_run("KEY EMPIRICAL FINDINGS\n")
    set_font(r_lh, size_pt=9, bold=True, color_rgb=(30, 58, 138))
    r_lb = p_left.add_run(
        "• Recall vs. Utility Tradeoff: Stage B candidate union minimizes character leakage (24%–36%) but causes severe over-redaction (73%–87%). Stage C contextual assessment drops over-redaction down to 3%–33%.\n"
        "• Local Inference Feasibility: Local Qwen 3.5 9B (Q4_K_M GGUF) runs entirely on-device with zero data egress, providing strict data residency and valid JSON compliance.\n"
        "• Generation Latency: On Apple M4, local warm execution delivers steady throughput without remote queue latency."
    )
    set_font(r_lb, size_pt=7.8, color_rgb=(31, 41, 55))

    p_right = cell_right.paragraphs[0]
    p_right.paragraph_format.space_before = Pt(2)
    p_right.paragraph_format.space_after = Pt(2)
    r_rh = p_right.add_run("LIMITATIONS & NEXT STEPS\n")
    set_font(r_rh, size_pt=9, bold=True, color_rgb=(30, 58, 138))
    r_rb = p_right.add_run(
        "• Synthetic Benchmark Scope: Evaluated on 30 standardized synthetic cases; production enterprise mailboxes contain greater layout and OCR variation.\n"
        "• Uncalibrated Scores: Model probabilities are raw heuristics; formal probability calibration is necessary prior to production gating.\n"
        "• No Zero-Risk Guarantee: No model achieved 0% leakage; high-tier entities require mandatory deterministic rules.\n"
        "• Next Steps: 1) Probability calibration; 2) Compliance policy alignment; 3) Hybrid local-first routing."
    )
    set_font(r_rb, size_pt=7.8, color_rgb=(31, 41, 55))

    doc.save(str(output_docx_path))
    print(f"Generated DOCX: {output_docx_path}")

def main():
    hist_metrics, followup_metrics = load_metrics()
    
    # Filter historical test runs: Baseline, Llama 3.1 8B (B, C), Qwen 2.5 7B (B, C), Grok 4.20 (B, C)
    # Filter follow-up test runs: Local Qwen 3.5 9B (B, C), Gemma 3 12B (B, C), Hosted Qwen 3.5 9B (B)
    table_data = []

    # 1. Baseline
    for m in hist_metrics:
        if m["model"] == "baseline_rules_presidio" and m["split"] == "test":
            table_data.append({
                "model": "Baseline (Rules + Presidio Pattern Recognizers)",
                "stage": "A",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": "N/A*"
            })

    # 2. Local Qwen 3.5 9B
    for m in followup_metrics:
        if m["model"] == "local_qwen3.5_9b" and m["split"] == "test" and m["stage"] == "B":
            table_data.append({
                "model": "Local Qwen 3.5 9B (Apple M4, Q4_K_M GGUF, Ollama)",
                "stage": "B",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Local)"
            })
        if m["model"] == "local_qwen3.5_9b" and m["split"] == "test" and m["stage"] == "C":
            table_data.append({
                "model": "Local Qwen 3.5 9B (Apple M4, Q4_K_M GGUF, Ollama)",
                "stage": "C",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Local)"
            })

    # 3. Hosted Gemma 3 12B
    for m in followup_metrics:
        if m["model"] == "google/gemma-3-12b-it" and m["split"] == "test" and m["stage"] == "B":
            table_data.append({
                "model": "Hosted Gemma 3 12B (Google / OpenRouter DeepInfra)",
                "stage": "B",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Hosted)"
            })
        if m["model"] == "google/gemma-3-12b-it" and m["split"] == "test" and m["stage"] == "C":
            table_data.append({
                "model": "Hosted Gemma 3 12B (Google / OpenRouter DeepInfra)",
                "stage": "C",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Hosted)"
            })

    # 4. Meta Llama 3.1 8B (Historical)
    for m in hist_metrics:
        if m["model"] == "meta-llama/llama-3.1-8b-instruct" and m["split"] == "test" and m["stage"] == "C":
            table_data.append({
                "model": "Meta Llama 3.1 8B Instruct (Hosted Reference)",
                "stage": "C",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Hosted)"
            })

    # 5. Qwen 2.5 7B (Historical)
    for m in hist_metrics:
        if m["model"] == "qwen/qwen-2.5-7b-instruct" and m["split"] == "test" and m["stage"] == "C":
            table_data.append({
                "model": "Qwen 2.5 7B Instruct (Hosted Reference)",
                "stage": "C",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Hosted)"
            })

    # 6. Grok 4.20 (Historical Reference)
    for m in hist_metrics:
        if m["model"] == "x-ai/grok-4.20" and m["split"] == "test" and m["stage"] == "C":
            table_data.append({
                "model": "x-ai / Grok 4.20 (Remote Proprietary Reference)",
                "stage": "C",
                "leak_rate": f"{m['char_leak_rate']*100:.1f}%",
                "over_redact": f"{m['char_over_redaction_rate']*100:.1f}%",
                "req_leak": f"{m['request_leak_rate']*100:.0f}%",
                "latency": f"{m['latency']['median_s']:.1f}s (Hosted)"
            })

    # Build HTML table rows
    html_rows = ""
    for r in table_data:
        m_label = r["model"]
        if "Local" in m_label:
            tag = '<span class="tag tag-local">LOCAL</span> '
        elif "Hosted" in m_label or "Reference" in m_label:
            tag = '<span class="tag tag-hosted">HOSTED</span> '
        else:
            tag = '<span class="tag tag-base">RULES</span> '
        html_rows += f"""<tr>
          <td>{tag}<strong>{m_label}</strong></td>
          <td style="text-align: center; font-weight: 600;">{r['stage']}</td>
          <td class="num">{r['leak_rate']}</td>
          <td class="num">{r['over_redact']}</td>
          <td class="num">{r['req_leak']}</td>
          <td class="num">{r['latency']}</td>
        </tr>\n"""

    # Generate PDF via HTML/Prince
    html_path = BENCH_FOLLOWUP / "CLIENT_ONE_PAGER.html"
    pdf_path = BENCH_FOLLOWUP / "CLIENT_ONE_PAGER.pdf"
    generate_pdf_html(html_rows, html_path)
    page_count = build_pdf(html_path, pdf_path)
    print(f"Generated PDF: {pdf_path} (Pages: {page_count})")
    assert page_count == 1, f"Error: PDF page count is {page_count}, expected exactly 1 page!"

    # Generate DOCX
    docx_path = BENCH_FOLLOWUP / "CLIENT_ONE_PAGER.docx"
    generate_docx(table_data, docx_path)

    # Copy to workspace root for convenient access
    import shutil
    shutil.copy(pdf_path, WORKSPACE / "CLIENT_ONE_PAGER.pdf")
    shutil.copy(docx_path, WORKSPACE / "CLIENT_ONE_PAGER.docx")
    print(f"Copied final brief to workspace root: {WORKSPACE / 'CLIENT_ONE_PAGER.pdf'}")

if __name__ == "__main__":
    main()

