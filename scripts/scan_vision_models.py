#!/usr/bin/env python3
"""scan_vision_models.py — 扫描 qingxiaoyun 端点上所有可用的视觉模型。

用途:
  - 探测哪些模型支持视觉（图片输入）
  - 测速：每个模型响应时间
  - 简单质量对比：用同一张测试图 + 同一个问题
  - 输出排名表，更新 vision_helper.py 的 MODELS 列表

用法:
  python3 scan_vision_models.py <test_image.jpg> [--question "描述这张图"]
  python3 scan_vision_models.py --list-only          # 只列模型，不测视觉
  python3 scan_vision_models.py --update-helper      # 测完自动更新 vision_helper.py

输出:
  排名表（按速度+可用性排序）+ 建议的 MODELS 列表
"""
import subprocess, base64, json, os, sys, time, argparse

API_BASE = 'https://ai.qingxiaoyun.net/v1'
API_KEY = 'sk-YaP0IMQvlU5Wu3kfZUgTxA9YnoQO0IwbQixMNcYzKYle2sET'

TIMEOUT = 30  # 单模型超时

# 常见视觉模型候选（用于优先排序测试）
VISION_CANDIDATES = [
    'k3',
    'kimi-k2.7',
    'kimi-k2.5',
    'kimi-k2.6',
    'doubao-seed-2.0-pro',
    'doubao-seed-2.1-turbo',
    'MiniMax-M3',
    'MiniMax-M2.5',
    'spark-x2',
    'spark-x3',
    'glm-4v',
    'glm-4v-plus',
    'qwen-vl-max',
    'qwen-vl-plus',
    'claude-sonnet-4',
    'claude-opus-4',
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4.1',
]


def list_models() -> list:
    """获取端点上所有可用模型列表"""
    r = subprocess.run([
        'curl', '-s', f'{API_BASE}/models',
        '-H', f'Authorization: Bearer {API_KEY}'
    ], capture_output=True, text=True, timeout=15)

    try:
        data = json.loads(r.stdout)
        return [m['id'] for m in data.get('data', [])]
    except (json.JSONDecodeError, KeyError):
        print(f'[ERROR] 无法获取模型列表: {r.stdout[:200]}', file=sys.stderr)
        return []


def test_vision(model: str, img_path: str, question: str, max_tokens: int = 300) -> dict:
    """测试单个模型的视觉能力。返回 {model, ok, time, content, error}"""
    result = {'model': model, 'ok': False, 'time': 0, 'content': '', 'error': ''}

    # 压缩图片
    tmp_path = img_path
    if os.path.getsize(img_path) > 500_000:
        try:
            from PIL import Image
            img = Image.open(img_path)
            img.thumbnail((1200, 1200))
            tmp_path = '/tmp/_scan_vision_test.jpg'
            img.save(tmp_path, quality=75)
        except ImportError:
            pass  # PIL 没有就用原图

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

    start = time.time()
    try:
        r = subprocess.run([
            'curl', '-s', '-X', 'POST', f'{API_BASE}/chat/completions',
            '-H', 'Content-Type: application/json',
            '-H', f'Authorization: Bearer {API_KEY}',
            '-d', json.dumps(payload)
        ], capture_output=True, text=True, timeout=TIMEOUT)
        elapsed = time.time() - start
        result['time'] = round(elapsed, 1)

        body = r.stdout
        if '\"choices\"' in body:
            data = json.loads(body)
            content = data['choices'][0]['message']['content']
            if content and content.strip():
                result['ok'] = True
                result['content'] = content[:200]
            else:
                result['error'] = 'empty content'
        else:
            result['error'] = body[:120]
    except subprocess.TimeoutExpired:
        result['time'] = TIMEOUT
        result['error'] = f'timeout ({TIMEOUT}s)'
    except Exception as e:
        result['error'] = str(e)[:120]

    return result


def main():
    parser = argparse.ArgumentParser(description='扫描可用视觉模型')
    parser.add_argument('image', nargs='?', help='测试图片路径')
    parser.add_argument('--question', '-q', default='用一句话描述这张图的主要内容',
                        help='测试问题')
    parser.add_argument('--list-only', action='store_true', help='只列出所有模型，不测视觉')
    parser.add_argument('--update-helper', action='store_true',
                        help='测完自动更新 vision_helper.py 的 MODELS 列表')
    parser.add_argument('--all', action='store_true',
                        help='测试所有在线模型（否则只测 VISION_CANDIDATES）')
    args = parser.parse_args()

    # Step 1: 获取所有模型
    print('=' * 60)
    print('Step 1: 获取在线模型列表...')
    print('=' * 60)
    all_models = list_models()
    if not all_models:
        print('无法获取模型列表，退出')
        sys.exit(1)
    print(f'共 {len(all_models)} 个模型在线')
    print()

    if args.list_only:
        for m in sorted(all_models):
            print(f'  {m}')
        return

    if not args.image:
        print('错误: 测试视觉能力需要提供图片路径')
        print('用法: scan_vision_models.py <test_image.jpg>')
        sys.exit(1)

    if not os.path.exists(args.image):
        print(f'错误: 图片不存在: {args.image}')
        sys.exit(1)

    # Step 2: 确定要测试的模型
    if args.all:
        test_list = all_models
    else:
        # 只测候选列表里有的
        test_list = [m for m in VISION_CANDIDATES if m in all_models]
        # 额外加一些名字里带 vision/vl/4v 的
        for m in all_models:
            ml = m.lower()
            if any(kw in ml for kw in ['vision', 'vl-', '-v', '4v', '4o', 'gemini']) and m not in test_list:
                test_list.append(m)

    print(f'=' * 60)
    print(f'Step 2: 测试 {len(test_list)} 个模型的视觉能力')
    print(f'测试图: {args.image} ({os.path.getsize(args.image)//1024} KB)')
    print(f'问题: {args.question}')
    print(f'=' * 60)
    print()

    # Step 3: 逐个测试
    results = []
    for i, model in enumerate(test_list):
        print(f'  [{i+1}/{len(test_list)}] {model} ... ', end='', flush=True)
        r = test_vision(model, args.image, args.question)
        results.append(r)
        if r['ok']:
            print(f'✅ {r["time"]}s')
        else:
            print(f'❌ {r["error"][:50]}')

    # Step 4: 排名
    ok_results = [r for r in results if r['ok']]
    ok_results.sort(key=lambda x: x['time'])

    print()
    print('=' * 60)
    print(f'Step 3: 结果排名（通过的 {len(ok_results)}/{len(test_list)} 个）')
    print('=' * 60)
    print(f'{"排名":<4}{"模型":<25}{"耗时(s)":<10}{"内容预览"}')
    print('-' * 80)
    for i, r in enumerate(ok_results):
        preview = r['content'].replace('\n', ' ')[:50]
        print(f'{i+1:<4}{r["model"]:<25}{r["time"]:<10}{preview}')

    print()
    print('建议的 MODELS 列表（按速度排序）:')
    print("MODELS = [")
    for r in ok_results:
        print(f"    '{r['model']}',")
    print("]")

    # Step 5: 可选：更新 vision_helper.py
    if args.update_helper and ok_results:
        helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vision_helper.py')
        if os.path.exists(helper_path):
            with open(helper_path, 'r') as f:
                content = f.read()

            # 找到 MODELS = [ ... ] 块并替换
            import re
            new_models = "MODELS = [\n"
            for r in ok_results[:8]:  # 最多 8 个
                new_models += f"    '{r['model']}',\n"
            new_models += "]"

            pattern = r'MODELS = \[.*?\]'
            new_content = re.sub(pattern, new_models, content, flags=re.DOTALL)

            with open(helper_path, 'w') as f:
                f.write(new_content)

            print()
            print(f'✅ 已更新 {helper_path} 的 MODELS 列表')
        else:
            print(f'\n⚠️  找不到 vision_helper.py: {helper_path}')


if __name__ == '__main__':
    main()
