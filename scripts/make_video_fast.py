"""Creates a faster under-3-minute video cut specifically compliant with Devpost's 3:00 max rule.
Uses SpeechSynthesizer Rate = 2 to deliver a crisp, dynamic 2m 45s presentation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "deliverables" / "video_build_devpost"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SLIDE_DIR = ROOT / "deliverables" / "video_build"
FINAL_VIDEO = ROOT / "deliverables" / "AegisMesh_Devpost_Submission_Under3Min.mp4"

from scripts.make_video import NARRATIONS


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
$speak.Rate = 2
$speak.SetOutputToWaveFile("{wav_path_str}")
$speak.Speak(@'
{text}
'@)
$speak.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
    return out_wav


def main():
    print("=== Generating Devpost 3-Min Cut Voiceover (Rate = 2) ===")
    audio_paths = []
    for i, text in enumerate(NARRATIONS, 1):
        p = generate_audio(i, text)
        audio_paths.append(p)
        print(f"  Generated fast audio {i} -> {p.name}")

    print("\n=== Encoding Slide Segments ===")
    segment_paths = []
    for i in range(1, 8):
        img = SLIDE_DIR / f"slide_{i}.png"
        aud = audio_paths[i - 1]
        seg = OUTPUT_DIR / f"segment_{i}.mp4"
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
        print(f"  Encoded segment {i} -> {seg.name}")

    print("\n=== Stitching Master Devpost Video ===")
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
    print(f"\n Master Devpost Video Created: {FINAL_VIDEO}")


if __name__ == "__main__":
    main()
