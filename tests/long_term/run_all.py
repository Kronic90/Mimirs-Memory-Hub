#!/usr/bin/env python3
"""
Mimir Year-Long Simulation — Test Runner & Report Generator
=============================================================
Runs all test suites (unit, integration, year-long scenarios)
and generates an HTML report + JSON results.

Usage:
    cd Mimir
    python -m tests.long_term.run_all                  # All tests
    python -m tests.long_term.run_all --quick           # Unit tests only
    python -m tests.long_term.run_all --scenarios       # Year scenarios only
    python -m tests.long_term.run_all --json results.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from html import escape

# Force UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ═══════════════════════════════════════════════════════════════
#  Import all test suites
# ═══════════════════════════════════════════════════════════════

from tests.long_term.test_memory_lifecycle import ALL_MEMORY_TESTS
from tests.long_term.test_neurochemistry import ALL_CHEMISTRY_TESTS
from tests.long_term.test_tags import ALL_TAG_TESTS
from tests.long_term.test_presets import ALL_PRESET_TESTS
from tests.long_term.test_conversation_quality import ALL_CONVERSATION_TESTS
from tests.long_term.test_year_simulation import ALL_YEAR_TESTS

try:
    from tests.long_term.test_api_endpoints import ALL_API_TESTS
except Exception:
    ALL_API_TESTS = []


# ═══════════════════════════════════════════════════════════════
#  Suite Definitions
# ═══════════════════════════════════════════════════════════════

UNIT_SUITES = [
    ("Memory Lifecycle", ALL_MEMORY_TESTS),
    ("Neurochemistry", ALL_CHEMISTRY_TESTS),
    ("Tag Parsing", ALL_TAG_TESTS),
    ("Presets", ALL_PRESET_TESTS),
]

INTEGRATION_SUITES = [
    ("Conversation Quality", ALL_CONVERSATION_TESTS),
    ("API Endpoints", ALL_API_TESTS),
]

SCENARIO_SUITES = [
    ("Year Simulations", ALL_YEAR_TESTS),
]


# ═══════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════

class TestRunner:
    """Executes tests and collects results."""

    def __init__(self):
        self.results: list[dict] = []
        self.start_time = time.time()
        self.suite_summaries: list[dict] = []

    def run_suite(self, suite_name: str, tests: list):
        """Run a named suite of (test_name, test_fn) pairs."""
        suite_start = time.time()
        suite_pass = 0
        suite_fail = 0
        suite_error = 0
        suite_results = []

        print(f"{'=' * 60}")
        print(f"  {suite_name}")
        print(f"{'=' * 60}")

        for test_name, test_fn in tests:
            t0 = time.time()
            try:
                metrics = test_fn()
                elapsed = time.time() - t0
                passed = metrics.pass_count if metrics else 0
                failed = metrics.fail_count if metrics else 0
                total = metrics.total if metrics else 0
                status = "PASS" if failed == 0 and total > 0 else (
                    "FAIL" if failed > 0 else "EMPTY"
                )
                icon = "[OK]" if status == "PASS" else ("[X]" if status == "FAIL" else "[-]")
                suite_pass += passed
                suite_fail += failed
                print(f"  {icon} {test_name:<40} {passed}/{total} "
                      f"({elapsed:.2f}s)")

                suite_results.append({
                    "test_name": test_name,
                    "status": status,
                    "passed": passed,
                    "failed": failed,
                    "total": total,
                    "elapsed": round(elapsed, 3),
                    "details": metrics.to_dict() if metrics else {},
                    "recall_rate": metrics.recall_rate if metrics else 0,
                    "errors": metrics.errors if metrics else [],
                })
            except Exception as e:
                elapsed = time.time() - t0
                suite_error += 1
                print(f"  ✗ {test_name:<40} ERROR ({elapsed:.2f}s)")
                print(f"    → {e}")
                suite_results.append({
                    "test_name": test_name,
                    "status": "ERROR",
                    "passed": 0,
                    "failed": 0,
                    "total": 0,
                    "elapsed": round(elapsed, 3),
                    "details": {},
                    "recall_rate": 0,
                    "errors": [f"{e}\n{traceback.format_exc()}"],
                })

        suite_elapsed = time.time() - suite_start
        print(f"  {'-' * 56}")
        print(f"  Suite: {suite_pass} passed, {suite_fail} failed, "
              f"{suite_error} errors ({suite_elapsed:.1f}s)")

        suite_summary = {
            "suite_name": suite_name,
            "tests": suite_results,
            "passed": suite_pass,
            "failed": suite_fail,
            "errors": suite_error,
            "elapsed": round(suite_elapsed, 2),
        }
        self.suite_summaries.append(suite_summary)
        self.results.extend(suite_results)

    def grand_summary(self) -> dict:
        total_elapsed = time.time() - self.start_time
        total_pass = sum(r["passed"] for r in self.results)
        total_fail = sum(r["failed"] for r in self.results)
        total_tests = len(self.results)
        total_error = sum(1 for r in self.results if r["status"] == "ERROR")

        # Recall accuracy across all tests
        recall_data = []
        for r in self.results:
            rd = r.get("details", {}).get("recall_accuracy", [])
            recall_data.extend(rd)
        recall_found = sum(1 for d in recall_data if d.get("found"))
        recall_total = len(recall_data)

        return {
            "timestamp": datetime.now().isoformat(),
            "total_test_functions": total_tests,
            "total_assertions_passed": total_pass,
            "total_assertions_failed": total_fail,
            "total_errors": total_error,
            "overall_pass_rate": f"{total_pass / (total_pass + total_fail) * 100:.1f}%"
                if (total_pass + total_fail) > 0 else "N/A",
            "recall_tests": recall_total,
            "recall_accuracy": f"{recall_found / recall_total * 100:.1f}%"
                if recall_total > 0 else "N/A",
            "total_elapsed_seconds": round(total_elapsed, 2),
            "suites": self.suite_summaries,
        }


# ═══════════════════════════════════════════════════════════════
#  HTML Report Generator
# ═══════════════════════════════════════════════════════════════

def generate_html_report(summary: dict, output_path: str):
    """Generate a rich HTML report from the test summary."""

    total_pass = summary["total_assertions_passed"]
    total_fail = summary["total_assertions_failed"]
    total_err = summary["total_errors"]
    overall = summary["overall_pass_rate"]
    recall_acc = summary["recall_accuracy"]

    # Color coding
    if total_fail == 0 and total_err == 0:
        status_color = "#22c55e"
        status_text = "ALL PASSING"
    elif total_fail + total_err < 5:
        status_color = "#f59e0b"
        status_text = "MOSTLY PASSING"
    else:
        status_color = "#ef4444"
        status_text = "NEEDS ATTENTION"

    rows_html = ""
    for suite in summary.get("suites", []):
        suite_name = escape(suite["suite_name"])
        rows_html += f"""
        <tr class="suite-header">
            <td colspan="6"><strong>{suite_name}</strong>
                <span class="badge">{suite['passed']}P / {suite['failed']}F / {suite['errors']}E
                ({suite['elapsed']}s)</span>
            </td>
        </tr>"""
        for test in suite.get("tests", []):
            status = test["status"]
            cls = "pass" if status == "PASS" else ("fail" if status in ("FAIL", "ERROR") else "empty")
            icon = "✓" if status == "PASS" else ("✗" if status in ("FAIL", "ERROR") else "○")
            name = escape(test["test_name"])
            recall = f"{test['recall_rate'] * 100:.0f}%" if test['recall_rate'] > 0 else "—"
            errors_html = ""
            if test.get("errors"):
                errors_html = f'<div class="error-detail">{escape(test["errors"][0][:300])}</div>'

            # Gather individual assertion details
            detail_items = test.get("details", {}).get("results", [])
            assertions_html = ""
            if detail_items:
                assertions_html = '<div class="assertions">'
                for item in detail_items:
                    acls = "a-pass" if item.get("passed") else "a-fail"
                    aicon = "✓" if item.get("passed") else "✗"
                    assertions_html += (
                        f'<div class="{acls}">{aicon} '
                        f'{escape(item.get("name", ""))}: '
                        f'{escape(str(item.get("message", ""))[:120])}</div>'
                    )
                assertions_html += "</div>"

            rows_html += f"""
        <tr class="{cls}">
            <td class="icon">{icon}</td>
            <td>{name}</td>
            <td class="num">{test['passed']}</td>
            <td class="num">{test['failed']}</td>
            <td class="num">{recall}</td>
            <td class="num">{test['elapsed']}s</td>
        </tr>"""
            if assertions_html or errors_html:
                rows_html += f"""
        <tr class="detail-row">
            <td></td>
            <td colspan="5">{assertions_html}{errors_html}</td>
        </tr>"""

    # Memory growth chart data
    growth_data = []
    for suite in summary.get("suites", []):
        for test in suite.get("tests", []):
            mg = test.get("details", {}).get("memory_growth", [])
            if mg:
                growth_data.extend(mg)

    # Chemistry history data
    chem_data = []
    for suite in summary.get("suites", []):
        for test in suite.get("tests", []):
            ch = test.get("details", {}).get("chemistry_history", [])
            if ch:
                chem_data.extend(ch)

    growth_json = json.dumps(growth_data[:100])
    chem_json = json.dumps(chem_data[:100])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mimir Year-Long Test Report</title>
<style>
:root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --border: #334155;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --pass: #22c55e;
    --fail: #ef4444;
    --warn: #f59e0b;
    --accent: #8b5cf6;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
}}
h1 {{ color: var(--accent); margin-bottom: 0.5rem; }}
h2 {{ color: var(--text); margin: 2rem 0 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
.timestamp {{ color: var(--muted); font-size: 0.85rem; }}
.summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}}
.card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
}}
.card .label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
.card .value {{ font-size: 2rem; font-weight: 700; margin: 0.5rem 0; }}
.card .value.green {{ color: var(--pass); }}
.card .value.red {{ color: var(--fail); }}
.card .value.yellow {{ color: var(--warn); }}
.card .value.purple {{ color: var(--accent); }}
.status-banner {{
    background: {status_color}22;
    border: 2px solid {status_color};
    border-radius: 12px;
    padding: 1rem 2rem;
    text-align: center;
    font-size: 1.3rem;
    font-weight: 700;
    color: {status_color};
    margin: 1.5rem 0;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.9rem;
}}
th {{
    background: var(--surface);
    color: var(--muted);
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 2px solid var(--border);
}}
td {{
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--border);
}}
.num {{ text-align: center; }}
.icon {{ width: 30px; text-align: center; font-size: 1.1rem; }}
tr.pass .icon {{ color: var(--pass); }}
tr.fail .icon, tr.error .icon {{ color: var(--fail); }}
tr.empty .icon {{ color: var(--muted); }}
tr.suite-header {{
    background: var(--surface);
}}
tr.suite-header td {{
    padding: 0.75rem 1rem;
    border-bottom: 2px solid var(--accent);
}}
.badge {{
    background: var(--accent)33;
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    margin-left: 8px;
}}
.detail-row td {{
    padding: 0.25rem 1rem 0.75rem;
    border-bottom: 1px solid var(--border);
}}
.assertions {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    font-size: 0.78rem;
}}
.a-pass {{
    color: var(--pass);
    background: #22c55e11;
    padding: 2px 6px;
    border-radius: 4px;
}}
.a-fail {{
    color: var(--fail);
    background: #ef444411;
    padding: 2px 6px;
    border-radius: 4px;
}}
.error-detail {{
    color: var(--fail);
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.75rem;
    white-space: pre-wrap;
    margin-top: 4px;
    padding: 8px;
    background: #ef444411;
    border-radius: 6px;
}}
canvas {{
    max-width: 100%;
    margin: 1rem 0;
    background: var(--surface);
    border-radius: 12px;
    border: 1px solid var(--border);
}}
.chart-container {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    margin: 1rem 0;
}}
@media (max-width: 768px) {{
    .chart-container {{ grid-template-columns: 1fr; }}
    .summary {{ grid-template-columns: 1fr 1fr; }}
}}
footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.8rem;
    text-align: center;
}}
</style>
</head>
<body>

<h1>🧠 Mimir's Memory Hub — Year-Long Test Report</h1>
<p class="timestamp">Generated: {summary['timestamp']} &nbsp;|&nbsp;
Runtime: {summary['total_elapsed_seconds']}s</p>

<div class="status-banner">{status_text}</div>

<div class="summary">
    <div class="card">
        <div class="label">Test Functions</div>
        <div class="value purple">{summary['total_test_functions']}</div>
    </div>
    <div class="card">
        <div class="label">Assertions Passed</div>
        <div class="value green">{total_pass}</div>
    </div>
    <div class="card">
        <div class="label">Assertions Failed</div>
        <div class="value {'red' if total_fail > 0 else 'green'}">{total_fail}</div>
    </div>
    <div class="card">
        <div class="label">Pass Rate</div>
        <div class="value {'green' if total_fail == 0 else 'yellow'}">{overall}</div>
    </div>
    <div class="card">
        <div class="label">Recall Accuracy</div>
        <div class="value purple">{recall_acc}</div>
    </div>
    <div class="card">
        <div class="label">Errors</div>
        <div class="value {'red' if total_err > 0 else 'green'}">{total_err}</div>
    </div>
</div>

<h2>Detailed Results</h2>
<table>
<thead>
<tr>
    <th></th>
    <th>Test</th>
    <th>Pass</th>
    <th>Fail</th>
    <th>Recall</th>
    <th>Time</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

<h2>Memory Growth &amp; Chemistry</h2>
<div class="chart-container">
    <div>
        <h3 style="color: var(--muted); font-size: 0.85rem; margin-bottom: 0.5rem;">Memory Growth Over Time</h3>
        <canvas id="memoryChart" width="500" height="300"></canvas>
    </div>
    <div>
        <h3 style="color: var(--muted); font-size: 0.85rem; margin-bottom: 0.5rem;">Chemistry Levels</h3>
        <canvas id="chemChart" width="500" height="300"></canvas>
    </div>
</div>

<script>
// Simple canvas charts (no external deps)
const growthData = {growth_json};
const chemData = {chem_json};

function drawLineChart(canvasId, data, xKey, yKeys, colors) {{
    const canvas = document.getElementById(canvasId);
    if (!canvas || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const pad = {{top: 20, right: 20, bottom: 40, left: 50}};
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    // Clear
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, W, H);

    // Axes
    ctx.strokeStyle = '#334155';
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, H - pad.bottom);
    ctx.lineTo(W - pad.right, H - pad.bottom);
    ctx.stroke();

    if (data.length < 2) return;

    const xVals = data.map(d => d[xKey] || 0);
    const xMin = Math.min(...xVals), xMax = Math.max(...xVals) || 1;

    let allY = [];
    yKeys.forEach(k => data.forEach(d => {{
        const v = d[k];
        if (v !== undefined && v !== null) allY.push(v);
    }}));
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(1, ...allY);

    const sx = v => pad.left + ((v - xMin) / (xMax - xMin)) * plotW;
    const sy = v => pad.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

    yKeys.forEach((key, i) => {{
        ctx.strokeStyle = colors[i % colors.length];
        ctx.lineWidth = 2;
        ctx.beginPath();
        let started = false;
        data.forEach(d => {{
            const v = d[key];
            if (v === undefined || v === null) return;
            const x = sx(d[xKey] || 0), y = sy(v);
            if (!started) {{ ctx.moveTo(x, y); started = true; }}
            else ctx.lineTo(x, y);
        }});
        ctx.stroke();
    }});

    // Legend
    ctx.font = '11px sans-serif';
    yKeys.forEach((key, i) => {{
        ctx.fillStyle = colors[i % colors.length];
        const lx = pad.left + 10 + i * 100;
        ctx.fillRect(lx, H - 18, 12, 12);
        ctx.fillText(key, lx + 16, H - 8);
    }});

    // X label
    ctx.fillStyle = '#94a3b8';
    ctx.font = '11px sans-serif';
    ctx.fillText(xKey, W / 2 - 10, H - 2);
}}

drawLineChart('memoryChart', growthData, 'day',
    ['total', 'cherished', 'anchored'],
    ['#8b5cf6', '#22c55e', '#f59e0b']);

drawLineChart('chemChart', chemData, 'day',
    ['dopamine', 'serotonin', 'oxytocin', 'norepinephrine', 'endorphin'],
    ['#ef4444', '#22c55e', '#ec4899', '#f59e0b', '#06b6d4']);
</script>

<footer>
    Mimir's Memory Hub — Year-Long Simulation Report<br>
    Generated by tests/long_term/run_all.py
</footer>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n=> HTML report: {output_path}")


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Mimir Year-Long Simulation Test Runner"
    )
    parser.add_argument("--quick", action="store_true",
                        help="Run only unit tests (fast)")
    parser.add_argument("--scenarios", action="store_true",
                        help="Run only year-long scenarios")
    parser.add_argument("--integration", action="store_true",
                        help="Run only integration tests")
    parser.add_argument("--json", type=str, default=None,
                        help="Output JSON results to this file")
    parser.add_argument("--html", type=str, default=None,
                        help="Output HTML report to this file")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip HTML report generation")
    args = parser.parse_args()

    runner = TestRunner()

    print("\n" + "=" * 60)
    print("  Mimir's Memory Hub -- Year-Long Simulation Test Suite")
    print("=" * 60)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Determine which suites to run
    if args.quick:
        suites = UNIT_SUITES
    elif args.scenarios:
        suites = SCENARIO_SUITES
    elif args.integration:
        suites = INTEGRATION_SUITES
    else:
        suites = UNIT_SUITES + INTEGRATION_SUITES + SCENARIO_SUITES

    for suite_name, tests in suites:
        if tests:
            runner.run_suite(suite_name, tests)

    # Final summary
    summary = runner.grand_summary()

    print(f"\n{'=' * 60}")
    print(f"  GRAND TOTAL")
    print(f"{'=' * 60}")
    print(f"  Test Functions: {summary['total_test_functions']}")
    print(f"  Assertions Passed: {summary['total_assertions_passed']}")
    print(f"  Assertions Failed: {summary['total_assertions_failed']}")
    print(f"  Pass Rate: {summary['overall_pass_rate']}")
    print(f"  Recall Accuracy: {summary['recall_accuracy']}")
    print(f"  Errors: {summary['total_errors']}")
    print(f"  Total Time: {summary['total_elapsed_seconds']}s")
    print(f"{'=' * 60}")

    # Output JSON if requested
    json_path = args.json or os.path.join(
        str(_REPO), "tests", "long_term", "results.json"
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"=> JSON results: {json_path}")

    # Generate HTML report
    if not args.no_report:
        html_path = args.html or os.path.join(
            str(_REPO), "tests", "long_term", "report.html"
        )
        generate_html_report(summary, html_path)

    # Exit code
    if summary["total_assertions_failed"] > 0 or summary["total_errors"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
