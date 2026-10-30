"""Generates high-contrast YouTube and Devpost thumbnails for AegisMesh."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_1080 = ROOT / "deliverables" / "AegisMesh_Thumbnail_1080p.png"
OUT_720 = ROOT / "deliverables" / "AegisMesh_Thumbnail.jpg"

W, H = 1920, 1080
img = Image.new("RGB", (W, H), (10, 15, 24))
draw = ImageDraw.ImageDraw(img)

# Glow background
for r in range(500, 0, -20):
    alpha = int(12 * (1 - r / 500))
    c = (15 + alpha, 25 + alpha * 2, 45 + alpha * 3)
    draw.ellipse((960 - r * 1.5, 400 - r, 960 + r * 1.5, 400 + r), fill=c)

# Fonts
font_hero = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 96)
font_sub = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 40)
font_badge = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 24)
font_card_h = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
font_card_b = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 20)
font_pill = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)

# Top Bar Badge
bx, by = 120, 70
draw.rounded_rectangle((bx, by, bx + 640, by + 46), radius=23, fill=(20, 30, 48), outline=(56, 189, 248), width=2)
draw.text((bx + 26, by + 8), "NEBIUS × NVIDIA GLOBAL AI HACKATHON 2026", fill=(56, 189, 248), font=font_badge)

# Track Badge
tx = W - 120 - 360
draw.rounded_rectangle((tx, by, tx + 360, by + 46), radius=23, fill=(20, 45, 35), outline=(16, 185, 129), width=2)
draw.text((tx + 24, by + 8), "TRACK: BEST APPS & AGENTS", fill=(52, 211, 153), font=font_badge)

# Hero Title
draw.text((120, 150), "AEGISMESH", fill=(255, 255, 255), font=font_hero)
# Green accent bar under title
draw.rounded_rectangle((120, 275, 520, 283), radius=4, fill=(118, 185, 0)) # NVIDIA Green

# Hero Subtitle / Value Prop
draw.text((120, 305), "Autonomous AI Incident-Response Digital Twin", fill=(226, 232, 240), font=font_sub)
draw.text((120, 365), "Tests Every Fix in Simulation Before Touching Production • Proven Recovery", fill=(148, 163, 184), font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26))

# 3 Flow Cards
cards = [
    {
        "title": "1. LIVE OUTAGE",
        "color": (239, 68, 68),
        "bg": (28, 18, 24),
        "desc": ["Cryptic Vendor Logs", "HL7 / Cloud Failure", "Cascading Disruption"]
    },
    {
        "title": "2. TWIN SIMULATION",
        "color": (118, 185, 0), # NVIDIA Green
        "bg": (18, 28, 18),
        "desc": ["4 Nemotron Agents", "Tavily Live Web Search", "Independent Policy Guard"]
    },
    {
        "title": "3. VERIFIED RECOVERY",
        "color": (16, 185, 129),
        "bg": (16, 30, 26),
        "desc": ["Safe Fix Executed", "Simulator-Proven State", "Zero Clinical / Tech Harm"]
    }
]

card_w = 510
gap = 35
start_x = 120
start_y = 445

for i, c in enumerate(cards):
    cx = start_x + i * (card_w + gap)
    cy = start_y
    draw.rounded_rectangle((cx, cy, cx + card_w, cy + 340), radius=18, fill=c["bg"], outline=c["color"], width=2)
    # Header tag
    draw.rounded_rectangle((cx + 25, cy + 25, cx + 320, cy + 72), radius=12, fill=(10, 15, 24), outline=c["color"], width=1)
    draw.text((cx + 42, cy + 33), c["title"], fill=c["color"], font=font_card_h)
    
    # Bullet lines
    for bi, text in enumerate(c["desc"]):
        ly = cy + 115 + bi * 65
        draw.ellipse((cx + 35, ly + 6, cx + 47, ly + 18), fill=c["color"])
        draw.text((cx + 65, ly), text, fill=(241, 245, 249), font=font_card_b)

# Bottom Tech Badges
pills = [
    ("NVIDIA Nemotron 30B / 120B / 550B", (118, 185, 0), (22, 38, 12)),
    ("Nebius Token Factory API", (56, 189, 248), (14, 34, 52)),
    ("Tavily Verified Web Search", (168, 85, 247), (32, 16, 48)),
    ("100% Python Standard Library", (245, 158, 11), (40, 28, 10))
]

px = 120
py = 840
for label, fg, pbg in pills:
    bbox = draw.textbbox((px, py), label, font=font_pill)
    pw = bbox[2] - bbox[0] + 40
    draw.rounded_rectangle((px, py, px + pw, py + 52), radius=14, fill=pbg, outline=fg, width=2)
    draw.text((px + 20, py + 12), label, fill=fg, font=font_pill)
    px += pw + 25

# Save 1080p
img.save(OUT_1080, "PNG")

# Resize to standard YouTube Thumbnail (1280x720) with high quality resampling
img_720 = img.resize((1280, 720), Image.Resampling.LANCZOS)
img_720.save(OUT_720, "JPEG", quality=95)

print(f"Generated:\n  1. {OUT_1080}\n  2. {OUT_720}")
