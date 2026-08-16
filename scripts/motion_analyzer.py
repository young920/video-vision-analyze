#!/usr/bin/env python3
"""
Motion Analyzer: 把视频拆成"动效区间" + "静态段"，定位每段动效发生位置。

Usage:
    python motion_analyzer.py <video.mp4> [--fps 8] [--static-thresh 1.5] [--motion-thresh 8.0]

Output:
    - static_segments.txt: 持续 > 1s 的静态段（diff < threshold）
    - motion_zones.txt: diff > motion_thresh 的动效区间（含 TOP/MID/BOT 区域 diff）
    - per_frame_diff.csv: 每帧的 full/top/mid/bot diff（可画曲线图）

Logic:
    1. ffmpeg 抽帧到 /tmp/motion_{fps}fps/
    2. 对每对相邻帧：resize 270x586，算全帧 + TOP/MID/BOT 区域 diff
    3. 静态段 = 连续 N 帧 (N > fps) diff < static_thresh
    4. 动效区间 = 连续帧 diff > motion_thresh
    5. 输出人类可读的"动效报告"
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image


def extract_frames(video_path: str, fps: int, out_dir: str) -> int:
    """ffmpeg 抽帧到 out_dir，文件名 m%04d.jpg。"""
    os.makedirs(out_dir, exist_ok=True)
    # 清空旧帧
    for f in Path(out_dir).glob("*.jpg"):
        f.unlink()
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps={fps}", "-q:v", "2",
         f"{out_dir}/m%04d.jpg"],
        capture_output=True, check=True)
    return len(list(Path(out_dir).glob("*.jpg")))


def compute_region_diffs(frame_dir: str, fps: int):
    """对每对相邻帧，算全帧 + TOP/MID/BOT 区域 diff。"""
    frames = sorted(Path(frame_dir).glob("*.jpg"))
    diffs = []
    for i in range(1, len(frames)):
        a1 = np.array(Image.open(frames[i-1]).resize((270, 586))).astype(int)
        a2 = np.array(Image.open(frames[i]).resize((270, 586))).astype(int)
        full = np.abs(a1 - a2).mean()
        top = np.abs(a1[80:180] - a2[80:180]).mean()    # overlay 标题区
        mid = np.abs(a1[200:450] - a2[200:450]).mean()  # 产品截图区
        bot = np.abs(a1[470:560] - a2[470:560]).mean()  # 底部字幕区
        diffs.append({
            "frame_idx": i,
            "time_s": i / fps,
            "full": float(full),
            "top": float(top),
            "mid": float(mid),
            "bot": float(bot),
        })
    return diffs


def find_static_segments(diffs, fps: int, threshold: float, min_duration_s: float = 1.0):
    """连续 N 帧 diff < threshold 且 N > fps * min_duration_s = 静态段。"""
    static_segs = []
    in_static = False
    start_idx = 0
    for d in diffs:
        if d["full"] < threshold:
            if not in_static:
                start_idx = d["frame_idx"]
                in_static = True
        else:
            if in_static:
                dur = (d["frame_idx"] - start_idx) / fps
                if dur >= min_duration_s:
                    static_segs.append({
                        "start_s": start_idx / fps,
                        "end_s": d["frame_idx"] / fps,
                        "duration_s": dur,
                    })
                in_static = False
    return static_segs


def find_motion_zones(diffs, threshold: float):
    """diff > threshold 的动效区间，含 TOP/MID/BOT 区域归因。"""
    zones = []
    in_zone = False
    start_idx = 0
    peak_diff = 0
    for d in diffs:
        if d["full"] > threshold:
            if not in_zone:
                start_idx = d["frame_idx"]
                peak_diff = d["full"]
                in_zone = True
            peak_diff = max(peak_diff, d["full"])
        else:
            if in_zone:
                # 归因：哪个区域 diff 最大
                zone_diffs = [d for d in diffs
                              if start_idx <= d["frame_idx"] < d["frame_idx"]]
                # 简化：取 zone 内平均 TOP/MID/BOT
                zone_window = [dd for dd in diffs if start_idx <= dd["frame_idx"] < d["frame_idx"]]
                if zone_window:
                    avg_top = np.mean([dd["top"] for dd in zone_window])
                    avg_mid = np.mean([dd["mid"] for dd in zone_window])
                    avg_bot = np.mean([dd["bot"] for dd in zone_window])
                    if avg_mid > 8:
                        area = "PPT切换"
                    elif avg_top > 8:
                        area = "顶动"
                    elif avg_bot > 8:
                        area = "底动"
                    else:
                        area = "微动"
                    zones.append({
                        "start_s": start_idx / fps,
                        "end_s": d["frame_idx"] / fps,
                        "duration_s": (d["frame_idx"] - start_idx) / fps,
                        "peak_diff": float(peak_diff),
                        "area": area,
                        "avg_top": float(avg_top),
                        "avg_mid": float(avg_mid),
                        "avg_bot": float(avg_bot),
                    })
                in_zone = False
    return zones


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="path to video file")
    parser.add_argument("--fps", type=int, default=8, help="extraction fps (default 8)")
    parser.add_argument("--static-thresh", type=float, default=1.5,
                        help="static segment threshold (default 1.5)")
    parser.add_argument("--motion-thresh", type=float, default=8.0,
                        help="motion zone threshold (default 8.0)")
    parser.add_argument("--out-dir", default="/tmp/motion_analysis",
                        help="output directory (default /tmp/motion_analysis)")
    args = parser.parse_args()

    print(f"[motion_analyzer] extracting frames from {args.video} @ {args.fps}fps...")
    n_frames = extract_frames(args.video, args.fps, args.out_dir)
    print(f"[motion_analyzer] extracted {n_frames} frames")

    print(f"[motion_analyzer] computing region diffs...")
    diffs = compute_region_diffs(args.out_dir, args.fps)
    print(f"[motion_analyzer] computed {len(diffs)} frame-pair diffs")

    print(f"\n=== Static segments (diff < {args.static_thresh}, dur >= 1s) ===")
    static = find_static_segments(diffs, args.fps, args.static_thresh)
    for s in static:
        print(f"  {s['start_s']:.2f}s - {s['end_s']:.2f}s ({s['duration_s']:.2f}s)")

    print(f"\n=== Motion zones (diff > {args.motion_thresh}) ===")
    print(f"{'start':<8} {'end':<8} {'dur':<8} {'peak':<8} {'area':<10} {'TOP':<6} {'MID':<6} {'BOT':<6}")
    zones = find_motion_zones(diffs, args.motion_thresh)
    for z in zones:
        print(f"  {z['start_s']:5.2f}s  {z['end_s']:5.2f}s  {z['duration_s']:5.2f}s   "
              f"{z['peak_diff']:6.2f}  {z['area']:<10} {z['avg_top']:5.2f}  "
              f"{z['avg_mid']:5.2f}  {z['avg_bot']:5.2f}")

    # 保存 CSV（可选）
    if diffs:
        csv_path = f"{args.out_dir}/per_frame_diff.csv"
        with open(csv_path, "w") as f:
            f.write("frame_idx,time_s,full,top,mid,bot\n")
            for d in diffs:
                f.write(f"{d['frame_idx']},{d['time_s']:.4f},"
                        f"{d['full']:.2f},{d['top']:.2f},{d['mid']:.2f},{d['bot']:.2f}\n")
        print(f"\n[motion_analyzer] CSV saved to {csv_path}")


if __name__ == "__main__":
    main()