# macOS Vision OCR Recipe

## When to use

When you need to OCR an image and `tesseract` isn't installed (it usually isn't on a clean macOS box, and Homebrew installs ~1GB of language data). macOS ships with Vision.framework via `swift`, which gives you:

- **Speed**: ~1 second per frame (vs vision_analyze 30-90s)
- **Cost**: free, local, no API key
- **Languages**: Chinese Simplified + English out of the box

This is the **primary OCR method for video analysis** — use it BEFORE vision_analyze for any text extraction.

## Recipe (copy-paste into a Python execute_code block)

```python
import subprocess

# Save this Swift script once
swift_ocr = '''
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let tiff = img.tiffRepresentation,
      let bm = NSBitmapImageRep(data: tiff) else { exit(1) }

let handler = VNImageRequestHandler(cgImage: bm.cgImage!, options: [:])
let req = VNRecognizeTextRequest { (request, err) in
    guard let obs = request.results as? [VNRecognizedTextObservation] else { return }
    for o in obs {
        if let c = o.topCandidates(1).first {
            print(c.string)
        }
    }
}
req.recognitionLevel = .accurate
req.recognitionLanguages = ["zh-Hans", "en-US"]
try handler.perform([req])
'''

with open('/tmp/ocr.swift', 'w') as f:
    f.write(swift_ocr)

# Run on an image
r = subprocess.run(['swift', '/tmp/ocr.swift', '/path/to/image.jpg'],
    capture_output=True, text=True, timeout=15)
print(r.stdout)
```

## Pitfalls

1. **`swift` compile time**: first invocation can take 5-10s while Swift compiles the script. Subsequent calls are ~1s because macOS caches. If you need it in a tight loop, do a warmup call first.

2. **Timeout**: set timeout=15 minimum. Large or complex images can take 3-5s.

3. **Recognition level**: `.accurate` is slower but much better for Chinese. `.fast` is ~3x faster but misses ~30% of Chinese characters.

4. **Languages**: pass `["zh-Hans", "en-US"]` for mixed CN/EN content. Use `["zh-Hant"]` for Traditional. Vision auto-detects mixed scripts even without explicit lang list, but accuracy drops.

5. **Output format**: one line per recognized text block, in reading order (top-to-bottom, left-to-right). Coordinates are NOT included — if you need bounding boxes, use `VNRecognizedTextObservation.boundingBox` and modify the swift script.

6. **Garbled output**: vision OCR sometimes outputs random English characters for Chinese text it can't read (e.g. "7:55" when the real text is "X/8"). Always cross-check OCR output with the image — see Pitfall #10 in SKILL.md.

## When NOT to use

- For **handwriting** or very low-res text: vision_analyze fallback chain works better
- For **table extraction** (preserving cell structure): use Python `pytesseract` if available, or vision_analyze
- For **rotated text** (`VNDetectTextRectanglesRequest`): needs a different swift script

## Pre-compiled binary (10x faster)

If you'll OCR >50 frames in one session, compile once:

```bash
# Compile a standalone binary
swiftc /tmp/ocr.swift -o /usr/local/bin/macos-ocr -framework Vision -framework AppKit
# Now use it
macos-ocr /path/to/image.jpg
```

The compile takes ~3s but binary invocation is ~100ms per frame. Worth it for bulk analysis.

## Example: extract text from 8 contact-sheet frames

```python
import subprocess, os

frames = [4, 32, 108, 156, 192, 316, 408, 528, 608]
for fn in frames:
    p = f'/tmp/frames/pt{fn:04d}.jpg'
    if not os.path.exists(p):
        continue
    r = subprocess.run(['swift', '/tmp/ocr.swift', p],
        capture_output=True, text=True, timeout=15)
    lines = [l for l in r.stdout.split('\n') if l.strip()]
    top3 = lines[:3]
    bot3 = lines[-3:] if len(lines) > 6 else []
    print(f"帧{fn}: {len(lines)} 行")
    for l in top3:
        print(f"  TOP: {l}")
    if bot3:
        print("  ...")
        for l in bot3:
            print(f"  BOT: {l}")
```