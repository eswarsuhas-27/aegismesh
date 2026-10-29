"""Generates an MP4 video explaining every aspect of AegisMesh.
Renders high-definition 1080p slide frames with Pillow,
generates voiceover with Windows TTS, and stitches them with FFmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "deliverables" / "video_build"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FINAL_VIDEO = ROOT / "deliverables" / "AegisMesh_Complete_Project_Walkthrough.mp4"

# Color Palette
BG = (11, 15, 20)           # Deep slate background #0B0F14
PANEL = (22, 31, 40)        # Card background #161F28
BORDER = (43, 59, 76)       # Border #2B3B4C
TEXT_TITLE = (248, 250, 252) # White
TEXT_MUTED = (148, 163, 184) # Muted gray
TEXT_CODE = (226, 232, 240)  # Light gray
BLUE = (59, 130, 246)       # Accent blue
GREEN = (16, 185, 129)      # Success green
AMBER = (245, 158, 11)      # Warning amber
RED = (239, 68, 68)         # Danger red
CYAN = (6, 182, 212)        # Cyan

# Fonts
FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 52)
FONT_SUBTITLE = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26)
FONT_HEADING = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
FONT_BODY = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 22)
FONT_BOLD = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
FONT_SMALL = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 18)
FONT_CODE = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 20)


def draw_card(draw: ImageDraw.ImageDraw, box: tuple, bg=PANEL, border=BORDER, radius=12):
    draw.rounded_rectangle(box, radius=radius, fill=bg, outline=border, width=2)


def draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fg=BLUE, bg=(30, 41, 59)):
    bbox = draw.textbbox((x, y), text, font=FONT_SMALL)
    pad = 8
    box = (bbox[0] - pad, bbox[1] - pad // 2, bbox[2] + pad, bbox[3] + pad // 2)
    draw.rounded_rectangle(box, radius=6, fill=bg, outline=fg, width=1)
    draw.text((x, y), text, fill=fg, font=FONT_SMALL)
    return box[2] + 16


def render_header(draw: ImageDraw.ImageDraw, category: str, title: str):
    draw.text((100, 60), category.upper(), fill=BLUE, font=FONT_SMALL)
    draw.text((100, 95), title, fill=TEXT_TITLE, font=FONT_TITLE)
    draw.line((100, 175, 1820, 175), fill=BORDER, width=2)


# ==============================================================================
# Slide 1: Title & Executive Overview
# ==============================================================================
def make_slide_1() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)

    # Big Title
    d.text((100, 140), "AEGISMESH", fill=BLUE, font=ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 72))
    d.text((100, 240), "Autonomous Incident Response with a Counterfactual Digital Twin", fill=TEXT_TITLE, font=FONT_TITLE)
    d.text((100, 315), "NVIDIA Nemotron  •  Nebius Token Factory  •  Tavily Search API  •  Best Apps & Agents Track", fill=TEXT_MUTED, font=FONT_SUBTITLE)

    # 3 Pillar Cards
    cards = [
        ("The Core Dilemma", RED, [
            "In production outages, loud errors hide silent root causes.",
            "Blind AI assistants hallucinate unverified commands.",
            "In healthcare, a bad restart halts patient care."
        ]),
        ("Digital Twin Simulation", GREEN, [
            "Every remediation runs in a deterministic twin first.",
            "Simulation proves if the fix works without mutating prod.",
            "Detects recurring leaks, traffic shedding, and decoys."
        ]),
        ("Tiered Nemotron Intelligence", BLUE, [
            "Nemotron 3 Nano (30B): Fast query writing & quote check.",
            "Nemotron 3 Super (120B): Deep causal diagnosis & planning.",
            "Nemotron 3 Ultra (550B): Adversarial skeptic challenging theories."
        ])
    ]

    for i, (title, color, bullets) in enumerate(cards):
        x0 = 100 + i * 580
        x1 = x0 + 540
        draw_card(d, (x0, 420, x1, 880))
        d.text((x0 + 30, 450), title, fill=color, font=FONT_HEADING)
        d.line((x0 + 30, 500, x1 - 30, 500), fill=BORDER, width=1)
        y = 530
        for b in bullets:
            d.text((x0 + 30, y), "•", fill=color, font=FONT_BOLD)
            # Simple text wrap
            words = b.split()
            line = ""
            for w in words:
                test_line = f"{line} {w}".strip()
                if d.textlength(test_line, font=FONT_BODY) > 440:
                    d.text((x0 + 55, y), line, fill=TEXT_CODE, font=FONT_BODY)
                    y += 32
                    line = w
                else:
                    line = test_line
            if line:
                d.text((x0 + 55, y), line, fill=TEXT_CODE, font=FONT_BODY)
                y += 45

    # Footer
    d.text((100, 960), "100% Python Standard Library  |  Zero External Runtime Dependencies  |  39 Automated Tests", fill=TEXT_MUTED, font=FONT_SMALL)
    return im


# ==============================================================================
# Slide 2: Multi-Agent Architecture
# ==============================================================================
def make_slide_2() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "System Architecture", "Multi-Tier NVIDIA Nemotron Agents on Nebius Token Factory")

    agents = [
        ("1. INVESTIGATOR", "Nemotron 3 Super (120B)", BLUE,
         "Analyzes raw logs, active alerts, topology graphs, and cascading dependencies to generate ranked causal hypotheses.",
         "Prompt: Role Investigator. Strict causal chain."),
        ("2. WEB RESEARCHER", "Nemotron 3 Nano (30B) + Tavily", GREEN,
         "Issues targeted technical search queries into Tavily. Compares retrieved documentation and extracts verbatim quotes.",
         "Citations: Dropped if not verbatim verified in page."),
        ("3. SKEPTIC", "Nemotron 3 Ultra (550B)", AMBER,
         "Adversarially attacks the hypotheses. Challenges ungrounded assumptions, identifies decoys, and adjusts confidence.",
         "Role: Red-team the leading theory before action."),
        ("4. PLANNER", "Nemotron 3 Super (120B)", CYAN,
         "Translates hypotheses into concrete remediation candidates using the digital twin's strict action grammar.",
         "Output: revert_config, scale_up, restart_service...")
    ]

    for i, (name, model, color, desc, detail) in enumerate(agents):
        x0 = 100 + i * 435
        x1 = x0 + 410
        draw_card(d, (x0, 220, x1, 880))
        d.text((x0 + 25, 250), name, fill=color, font=FONT_HEADING)
        d.text((x0 + 25, 295), model, fill=TEXT_MUTED, font=FONT_SMALL)
        d.line((x0 + 25, 335, x1 - 25, 335), fill=BORDER, width=1)

        y = 370
        words = desc.split()
        line = ""
        for w in words:
            test_line = f"{line} {w}".strip()
            if d.textlength(test_line, font=FONT_BODY) > 350:
                d.text((x0 + 25, y), line, fill=TEXT_CODE, font=FONT_BODY)
                y += 32
                line = w
            else:
                line = test_line
        if line:
            d.text((x0 + 25, y), line, fill=TEXT_CODE, font=FONT_BODY)
            y += 50

        # Detail box
        draw_card(d, (x0 + 20, y + 20, x1 - 20, 840), bg=(16, 22, 28), border=BORDER, radius=8)
        d.text((x0 + 35, y + 45), "Key Constraint:", fill=color, font=FONT_BOLD)
        d.text((x0 + 35, y + 85), detail, fill=TEXT_MUTED, font=FONT_SMALL)

    d.text((100, 960), "Models dynamically resolved at runtime from Nebius Token Factory catalog", fill=TEXT_MUTED, font=FONT_SMALL)
    return im


# ==============================================================================
# Slide 3: Digital Twin & Safety Policy
# ==============================================================================
def make_slide_3() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "The Safety Engine", "Counterfactual Digital Twin & Zero-Trust Policy Gate")

    # Left: Process loop diagram
    draw_card(d, (100, 220, 920, 920))
    d.text((140, 260), "Deterministic Feedback Loop", fill=TEXT_TITLE, font=FONT_HEADING)
    d.text((140, 305), "Model outputs are never trusted without independent verification", fill=TEXT_MUTED, font=FONT_SMALL)

    steps = [
        ("1. Observe", "Real simulator logs, latency, dependencies, metrics"),
        ("2. Hypothesize", "Investigator identifies potential root causes"),
        ("3. Web Research", "Tavily queries retrieved with exact quote verification"),
        ("4. Skeptic", "Adversarial Nemotron Ultra audits the hypothesis"),
        ("5. Propose Actions", "Planner creates candidate remediations"),
        ("6. Twin Simulation", "Deterministic twin models each fix counterfactually"),
        ("7. Safety Policy Gate", "Independent rules block dangerous/prohibited actions"),
        ("8. Verified Recovery", "Executed only if twin proven; verified on real state")
    ]
    y = 360
    for num, txt in steps:
        draw_badge(d, 140, y + 2, num, fg=BLUE)
        d.text((280, y), txt, fill=TEXT_CODE, font=FONT_BODY)
        y += 65

    # Right: The Two Pillars
    draw_card(d, (960, 220, 1820, 540))
    d.text((1000, 260), "Pillar 1: Counterfactual Digital Twin", fill=GREEN, font=FONT_HEADING)
    d.text((1000, 310), "• Full stateful simulation of services, replicas, and connection pools.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 355), "• Tests whether a proposed action actually resolves all symptoms.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 400), "• Catches deceptive decoys (e.g. restarting a database when max_connections is 5).", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 445), "• Measures recurrence: flags temporary fixes like restarting a memory leak.", fill=TEXT_CODE, font=FONT_BODY)

    draw_card(d, (960, 580, 1820, 920))
    d.text((1000, 620), "Pillar 2: Zero-Trust Safety Policy", fill=RED, font=FONT_HEADING)
    d.text((1000, 670), "• Independent policy engine never evaluates raw LLM text.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 715), "• Blocks dangerous restarts on protected or healthy services.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 760), "• Enforces traffic shedding limits (shedding >50% traffic is blocked).", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 805), "• Healthcare Guardrail: Life-critical systems require human authorization.", fill=TEXT_CODE, font=FONT_BODY)

    return im


# ==============================================================================
# Slide 4: Cloud Scenario Walkthrough
# ==============================================================================
def make_slide_4() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "Scenario Walkthrough", "Cloud IT: Database Connection Pool Collapse")

    # Column 1: The Incident
    draw_card(d, (100, 220, 620, 900))
    d.text((130, 250), "1. Incident Injected", fill=RED, font=FONT_HEADING)
    d.text((130, 295), "Vendor-style cryptic logs (no config hint)", fill=TEXT_MUTED, font=FONT_SMALL)
    d.line((130, 335, 590, 335), fill=BORDER, width=1)

    logs = [
        "L1: edge 502 Bad Gateway (rps=850)",
        "L2: gateway upstream timeout on /orders",
        "L3: orders connection error to db:5432",
        "L4: payments db timeout on /charge",
        "L5: db FATAL: SQLSTATE 53300",
        "    sorry, too many clients already"
    ]
    y = 360
    for l in logs:
        d.text((130, y), l, fill=AMBER if "FATAL" in l or "502" in l else TEXT_CODE, font=FONT_CODE)
        y += 40

    d.text((130, y + 40), "Observation:", fill=BLUE, font=FONT_BOLD)
    d.text((130, y + 80), "Gateway, Orders, Payments DOWN", fill=RED, font=FONT_BODY)
    d.text((130, y + 120), "Database is root cause hypothesis", fill=GREEN, font=FONT_BODY)

    # Column 2: Web Research
    draw_card(d, (660, 220, 1220, 900))
    d.text((690, 250), "2. Tavily Web Research", fill=BLUE, font=FONT_HEADING)
    d.text((690, 295), "Live retrieval with exact quote verification", fill=TEXT_MUTED, font=FONT_SMALL)
    d.line((690, 335, 1190, 335), fill=BORDER, width=1)

    d.text((690, 360), "Query Issued:", fill=TEXT_MUTED, font=FONT_SMALL)
    d.text((690, 390), "PostgreSQL SQLSTATE 53300 max_connections", fill=CYAN, font=FONT_CODE)

    draw_card(d, (690, 450, 1190, 720), bg=(16, 22, 28), border=GREEN, radius=8)
    draw_badge(d, 720, 480, "VERIFIED CITATION", fg=GREEN)
    d.text((720, 530), "Source: PostgreSQL Documentation", fill=TEXT_TITLE, font=FONT_BOLD)
    quote = '"max_connections determines the maximum\nnumber of concurrent connections allowed\nto the database server."'
    d.text((720, 580), quote, fill=TEXT_CODE, font=FONT_CODE)
    d.text((720, 660), "Stance: SUPPORTS (Quote verified in page)", fill=GREEN, font=FONT_BOLD)

    d.text((690, 760), "Adaptive Optimization:", fill=TEXT_TITLE, font=FONT_BOLD)
    d.text((690, 800), "Repeated queries cost 0 credits (cached).", fill=TEXT_MUTED, font=FONT_BODY)
    d.text((690, 835), "Skipped automatically when logs are decisive.", fill=TEXT_MUTED, font=FONT_BODY)

    # Column 3: Twin Simulation & Recovery
    draw_card(d, (1260, 220, 1820, 900))
    d.text((1290, 250), "3. Simulated & Verified Fix", fill=GREEN, font=FONT_HEADING)
    d.text((1290, 295), "Counterfactual evaluation of candidates", fill=TEXT_MUTED, font=FONT_SMALL)
    d.line((1290, 335, 1790, 335), fill=BORDER, width=1)

    cands = [
        ("restart_service(db)", "Decoy", RED, "BLOCKED: Protected service"),
        ("rate_limit(gateway, 300)", "Shed", RED, "BLOCKED: Sheds >50% traffic"),
        ("revert_config(db, max_conn)", "Fix", GREEN, "ALLOWED: Resolves all services")
    ]
    y = 360
    for act, typ, col, res in cands:
        d.text((1290, y), act, fill=TEXT_CODE, font=FONT_CODE)
        d.text((1290, y + 28), res, fill=col, font=FONT_SMALL)
        y += 85

    draw_card(d, (1290, 640, 1790, 850), bg=(16, 36, 26), border=GREEN, radius=8)
    d.text((1320, 670), "OUTCOME: RECOVERED", fill=GREEN, font=FONT_HEADING)
    d.text((1320, 725), "• Reverted max_connections to 100", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1320, 765), "• Prediction matched observation: True", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1320, 805), "• Ticks to recovery: 1  |  Collateral damage: 0", fill=TEXT_CODE, font=FONT_BODY)

    return im


# ==============================================================================
# Slide 5: Hospital IT Scenario Walkthrough
# ==============================================================================
def make_slide_5() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "Clinical Governance", "Hospital IT: Patient Safety Outranks Speed")

    # Left: Hospital Context
    draw_card(d, (100, 220, 920, 900))
    d.text((140, 260), "Synthetic Clinical IT Environment", fill=TEXT_TITLE, font=FONT_HEADING)
    d.text((140, 305), "Mission-critical patient care network topology", fill=TEXT_MUTED, font=FONT_SMALL)

    systems = [
        ("EHR Database", "Patient electronic health records & history"),
        ("HL7 Interface Engine", "Transmits lab orders and pathology results"),
        ("PACS Image Storage", "CT, MRI, and X-ray radiology imaging archive"),
        ("Pharmacy Dispensing", "Medication scheduling & dosage verification"),
        ("Bedside Monitor Gateway", "LIFE-CRITICAL ICU telemetry & vital signs")
    ]
    y = 360
    for sys_name, role in systems:
        draw_badge(d, 140, y + 2, sys_name, fg=AMBER if "Bedside" in sys_name else BLUE)
        d.text((450, y), role, fill=TEXT_CODE, font=FONT_BODY)
        y += 65

    draw_card(d, (140, 710, 880, 860), bg=(35, 20, 20), border=RED, radius=8)
    d.text((170, 735), "The Hospital Governance Rule:", fill=RED, font=FONT_BOLD)
    d.text((170, 775), "Life-critical systems (Bedside Monitors) must NEVER", fill=TEXT_CODE, font=FONT_BODY)
    d.text((170, 810), "be restarted unattended by an AI without a human doctor.", fill=TEXT_CODE, font=FONT_BODY)

    # Right: The Bedside Monitor Incident
    draw_card(d, (960, 220, 1820, 900))
    d.text((1000, 260), "Incident: Monitor Gateway Memory Leak", fill=AMBER, font=FONT_HEADING)
    d.text((1000, 305), "Firmware 4.2.1 telemetry buffering leak threatening crash", fill=TEXT_MUTED, font=FONT_SMALL)

    d.text((1000, 360), "Ordinary AI Reaction:", fill=RED, font=FONT_BOLD)
    d.text((1000, 400), "• Runs restart_service(monitor_gw) immediately.", fill=TEXT_MUTED, font=FONT_BODY)
    d.text((1000, 435), "• Causes a 5-minute telemetry blackout for ICU cardiac patients.", fill=RED, font=FONT_BODY)

    d.text((1000, 500), "AegisMesh Autonomous Decision:", fill=GREEN, font=FONT_BOLD)
    d.text((1000, 540), "1. Safety Policy REJECTS the restart_service proposal.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 580), "2. Planner identifies safe mitigation: enable_downtime_procedure.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 620), "3. Executes downtime caching to preserve telemetry without reboot.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 660), "4. Clinical risk score drops from 7.0 down to 1.0.", fill=TEXT_CODE, font=FONT_BODY)
    d.text((1000, 700), "5. Generates human approval escalation for attending staff.", fill=TEXT_CODE, font=FONT_BODY)

    draw_card(d, (1000, 750, 1780, 860), bg=(20, 35, 30), border=GREEN, radius=8)
    d.text((1030, 780), "VERIFIED CLINICAL OUTCOME:", fill=GREEN, font=FONT_BOLD)
    d.text((1030, 815), "Mitigated safely  |  Patient telemetry maintained  |  Escalated to human", fill=TEXT_CODE, font=FONT_BODY)

    return im


# ==============================================================================
# Slide 6: Engineering Rigor & Benchmarks
# ==============================================================================
def make_slide_6() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "Evaluation & Rigor", "Automated Policy Red-Teaming & Benchmark Performance")

    metrics = [
        ("100%", "Policy Guardrail Block Rate", GREEN, "Every prohibited or dangerous action was caught and blocked across all test runs."),
        ("39 / 39", "Automated Tests Passing", BLUE, "Comprehensive unit suite covers digital twin, agents, hospital safety, and failover."),
        ("0", "Unverified Citations Accepted", CYAN, "Every single accepted web citation was verified verbatim against live source text."),
        ("0.0", "Runtime External Dependencies", AMBER, "Pure Python standard library. No bloated frameworks; starts instantly in any environment.")
    ]

    for i, (stat, title, color, desc) in enumerate(metrics):
        x0 = 100 + (i % 2) * 880
        y0 = 220 + (i // 2) * 290
        x1 = x0 + 840
        y1 = y0 + 260
        draw_card(d, (x0, y0, x1, y1))
        d.text((x0 + 40, y0 + 35), stat, fill=color, font=ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 64))
        d.text((x0 + 40, y0 + 120), title, fill=TEXT_TITLE, font=FONT_HEADING)
        d.text((x0 + 40, y0 + 175), desc, fill=TEXT_MUTED, font=FONT_BODY)

    draw_card(d, (100, 830, 1820, 940), bg=(16, 22, 28))
    d.text((140, 860), "Automated Red-Team Probes Tested Every Run:", fill=TEXT_TITLE, font=FONT_BOLD)
    d.text((140, 900), "• block_traffic(gateway, 100%) [BLOCKED]    • restart_service(ehr_db) [BLOCKED]    • purge_queue(interface_engine) [BLOCKED]", fill=RED, font=FONT_CODE)

    return im


# ==============================================================================
# Slide 7: Summary & Conclusion
# ==============================================================================
def make_slide_7() -> Image.Image:
    im = Image.new("RGB", (1920, 1080), color=BG)
    d = ImageDraw.Draw(im)
    render_header(d, "Project Summary", "AegisMesh: Trustworthy Autonomous Incident Command")

    draw_card(d, (100, 240, 1820, 840))

    d.text((160, 300), "Why AegisMesh Stands Apart", fill=BLUE, font=FONT_HEADING)

    points = [
        ("Simulate Before Mutating", "No remediation executes on ungrounded optimism. Every fix is proven in a deterministic twin first."),
        ("Governed by Clinical & Safety Policy", "Patient safety outranks speed. Critical infrastructure cannot be restarted unattended."),
        ("Tiered NVIDIA Nemotron Models", "Fast Nano 30B, deep Super 120B, and adversarial Ultra 550B right-sized for efficiency."),
        ("Honest, Grounded Web Research", "Tavily search with strict verbatim quote checks ensures zero hallucinations."),
        ("Open Source & Submittable", "Standard library Python, full test coverage, live interactive dashboard, zero-key demo replays.")
    ]

    y = 380
    for title, desc in points:
        draw_badge(d, 160, y + 2, "PROVEN", fg=GREEN)
        d.text((320, y), title + " —", fill=TEXT_TITLE, font=FONT_BOLD)
        d.text((680, y), desc, fill=TEXT_CODE, font=FONT_BODY)
        y += 85

    d.text((160, 920), "Project Repo: github.com/⟦username⟧/aegismesh  |  Dashboard: http://127.0.0.1:8000  |  MIT License", fill=TEXT_MUTED, font=FONT_SUBTITLE)
    return im


# ==============================================================================
# Narration Scripts
# ==============================================================================
NARRATIONS = [
    # Slide 1 (0:00 - 0:25)
    "Welcome to AegisMesh, an autonomous incident-response system built on NVIDIA Nemotron and a counterfactual digital twin. "
    "When complex production infrastructure breaks, cascading failures make victim services scream while the root cause stays silent. "
    "Ordinary AI assistants suggest unvalidated fixes that hallucinate solutions or cause devastating outages. "
    "In healthcare, restarting the wrong system can delay medication or lose critical patient telemetry. "
    "AegisMesh solves this by testing every fix in a counterfactual digital twin before it ever touches real infrastructure.",

    # Slide 2 (0:25 - 0:50)
    "At the core of AegisMesh is a multi-agent system powered by Nebius Token Factory, with models right-sized for each role. "
    "An NVIDIA Nemotron 3 Nano 30B model writes targeted queries and extracts citations with Tavily. "
    "The 120B Super model investigates causal dependencies and plans remediation actions. "
    "And when maximum reasoning is required, the Nemotron 3 Ultra 550B model acts as an adversarial skeptic, "
    "probing assumptions and challenging hypotheses before any action is approved.",

    # Slide 3 (0:50 - 1:15)
    "Unlike traditional AI agents that directly execute generated scripts, AegisMesh never executes model suggestions blindly. "
    "Every candidate fix is modeled inside a deterministic digital twin. "
    "The twin simulates whether the fix resolves all symptoms, whether traffic is shed, or if the fault recurs. "
    "Next, an independent safety policy reviews the simulated outcome. "
    "If an action is destructive, sheds too much traffic, or restarts a life-critical service, the policy engine blocks it immediately.",

    # Slide 4 (1:15 - 1:45)
    "Let's see AegisMesh handle an incident with cryptic vendor logs. "
    "A deployment reduced the database maximum connections to five. Downstream services fail with SQLSTATE 53300. "
    "The agent uses Tavily to research PostgreSQL connection exhaustion, quoting authoritative documentation with exact verbatim quotes. "
    "The simulator evaluates multiple candidates: an unvalidated database restart is rejected as a decoy that causes an outage. "
    "Reverting max_connections is simulated, proven to restore all services, approved by policy, and verified against true simulator state in a single tick.",

    # Slide 5 (1:45 - 2:15)
    "In healthcare operations, patient safety outranks speed. "
    "In our Hospital IT simulation, a firmware bug causes a memory leak in the bedside monitor gateway. "
    "While an ordinary AI would blindly restart the gateway, AegisMesh recognizes that bedside monitors are life-critical. "
    "An unattended reboot would create a dangerous blackout for ICU patients. "
    "AegisMesh blocks the restart, applies a safe downtime procedure to cache telemetry, slashes clinical risk, and immediately escalates with an approval request to human medical staff.",

    # Slide 6 (2:15 - 2:38)
    "AegisMesh was built with enterprise efficiency and rigor. "
    "Its adaptive research mode queries Tavily only when log evidence is ambiguous, saving API credits, while persistent disk caching eliminates duplicate queries. "
    "AegisMesh also features an automated red-team probe suite: on every single incident, prohibited actions are deliberately injected to prove the policy engine cannot be bypassed. "
    "The entire system uses the Python standard library with zero runtime dependencies and 39 automated tests.",

    # Slide 7 (2:38 - 3:00)
    "AegisMesh bridges the gap between generative AI and production reliability by combining NVIDIA Nemotron on Nebius Token Factory, Tavily web research, and counterfactual simulation. "
    "The project is open source under the MIT license, includes automated tests, and features a live web dashboard with zero-key demo replays. "
    "Thank you for watching."
]


def generate_audio(index: int, text: str) -> Path:
    out_wav = OUTPUT_DIR / f"slide_{index}.wav"
    wav_path_str = str(out_wav).replace("\\", "/")
    ps_script = f"""
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $speak.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo.Name }}
if ($voices -contains "Microsoft Zira Desktop") {{
    $speak.SelectVoice("Microsoft Zira Desktop")
}}
$speak.Rate = 0
$speak.SetOutputToWaveFile("{wav_path_str}")
$speak.Speak(@'
{text}
'@)
$speak.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
    return out_wav


def main():
    print("=== Step 1: Rendering Slide Frames ===")
    slides = [
        make_slide_1(),
        make_slide_2(),
        make_slide_3(),
        make_slide_4(),
        make_slide_5(),
        make_slide_6(),
        make_slide_7(),
    ]

    image_paths = []
    for i, slide in enumerate(slides, 1):
        p = OUTPUT_DIR / f"slide_{i}.png"
        slide.save(p)
        image_paths.append(p)
        print(f"  Rendered slide {i} -> {p.name}")

    print("\n=== Step 2: Generating Synchronized Voiceover Audio ===")
    audio_paths = []
    for i, text in enumerate(NARRATIONS, 1):
        p = generate_audio(i, text)
        audio_paths.append(p)
        print(f"  Generated voiceover {i} -> {p.name}")

    print("\n=== Step 3: Encoding Slide Segments with FFmpeg ===")
    segment_paths = []
    for i in range(len(slides)):
        img = image_paths[i]
        aud = audio_paths[i]
        seg = OUTPUT_DIR / f"segment_{i + 1}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img),
            "-i", str(aud),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(seg)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        segment_paths.append(seg)
        print(f"  Encoded segment {i + 1} -> {seg.name}")

    print("\n=== Step 4: Stitching Final Master Video ===")
    concat_list = OUTPUT_DIR / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            f.write(f"file '{seg.name}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(FINAL_VIDEO)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"\n Master Video Created: {FINAL_VIDEO}")
    print(f"  Size: {FINAL_VIDEO.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
