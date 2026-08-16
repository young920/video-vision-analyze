#!/usr/bin/env python3
"""Direct vision API helper - bypass vision_analyze 503.

Calls a configurable vision model via the qingxiaoyun.net OpenAI-compatible endpoint.
Default model: k3 (most reliable + best visual understanding as of 2026-08-13 test).

Falls back through a chain if the primary model fails. Swap MODELS in this file
to change the chain; vision_analyze() signature stays stable.
"""
import subprocess, base64, json, os, sys, tempfile

# === Configuration: edit here to change model chain ===
API_BASE = 'https://ai.qingxiaoyun.net/v1'
API_KEY = 'sk-5NwKkQKIDLAFmYZ6qGteou58kqNg9AMHjDZfgiN61ykJDQlc'

# Ordered list: first try #0, then #1, etc.
# 2026-08-16 杨新给的 5 个模型 + 新 key，按好→次排列
# k3 主模型，kimi-k2.7 第二，2.1-turbo 第三，MiniMax-M3 兜底 OCR，2.0-pro 最后兜底
MODELS = [
    'k3',                     # ✅ 主模型 — 快、准、稳
    'kimi-k2.7',              # ✅ 第二 — 视觉理解强
    'doubao-seed-2.1-turbo',  # ⚡ 第三 — 速度快，新版试试
    'MiniMax-M3',             # ✅ 兜底 — OCR 强
    'doubao-seed-2.0-pro',    # 🛡 最后兜底 — 慢但准
]
# === End configuration ===

TIMEOUT = 60  # seconds per model attempt


def _call_one(model: str, img_path: str, question: str, max_tokens: int) -> str:
    """Single model call. Returns content string or raises."""
    # Compress large images
    tmp_path = img_path
    if os.path.getsize(img_path) > 500_000:
        from PIL import Image
        img = Image.open(img_path)
        img.thumbnail((1600, 1600))
        tmp_path = '/tmp/_vision_compressed.jpg'
        img.save(tmp_path, quality=80)

    with open(tmp_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': question},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{img_b64}'}}
        ]}],
        'max_tokens': max_tokens
    }
    with open('/tmp/_vision_payload.json', 'w') as f:
        json.dump(payload, f)

    r = subprocess.run([
        'curl', '-s', '-X', 'POST', f'{API_BASE}/chat/completions',
        '-H', 'Content-Type: application/json',
        '-H', f'Authorization: Bearer {API_KEY}',
        '-d', '@/tmp/_vision_payload.json'
    ], capture_output=True, text=True, timeout=TIMEOUT)

    body = r.stdout
    if '"choices"' not in body:
        raise RuntimeError(f'{model}: non-choice response: {body[:200]}')
    data = json.loads(body)
    content = data['choices'][0]['message']['content']
    if not content or not content.strip():
        raise RuntimeError(f'{model}: empty content')
    return content


def vision_analyze(image_path: str, question: str, max_tokens: int = 1500,
                   model: str = None, verbose: bool = False) -> str:
    """Call vision model with auto-fallback through MODELS chain.

    Args:
        image_path: absolute path to image file
        question: text prompt to ask about the image
        max_tokens: response length cap
        model: override primary model (still falls back if it fails)
        verbose: print which model was used to stderr

    Returns:
        Assistant text content. If all models fail, returns error string.
    """
    chain = [model] + [m for m in MODELS if m != model] if model else MODELS

    errors = []
    for m in chain:
        try:
            result = _call_one(m, image_path, question, max_tokens)
            if verbose:
                print(f'[vision] used model={m}', file=sys.stderr)
            return result
        except Exception as e:
            errors.append(f'{m}: {str(e)[:80]}')
            continue

    return f'[vision_analyze ALL FAILED]\n' + '\n'.join(errors)


if __name__ == '__main__':
    img_path = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else '描述这张图'
    print(vision_analyze(img_path, question, verbose=True))