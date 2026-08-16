# Vision Model Scan 2026-08-13

## Context

Reference video SVID_20260812_195522_1.mp4 (66s, 540×1172, 小红书录屏 + PPT截图讲解). User asked "is there a red box circling an element?". Built-in `vision_analyze` returned 503 (`kimi-k2.6-claude model_not_found`). I incorrectly fell back to pixel-diff + OCR alone and declared "no red box". User pushed back hard three rounds before I tried curl fallback — which worked. Lesson: **never skip vision when image-understanding is what's being asked**.

## 14-model scan results (single test image, single question)

Test question: "这张图中间PPT区显示什么？有红框/方框/箭头吗？圈住什么元素？100字内回答。"
Image: cropped PPT region from frame at 7.5s (540×600, JPEG q=85).

| Model | Result | Speed | Verdict |
|---|---|---|---|
| **k3** | ✅ accurate: "GitHub仓库 slides_maker, 无红框/方框/箭头, 右上角灰色圆环" | ~10s | **DEFAULT — best** |
| **kimi-k2.7** | ✅ accurate: same conclusion, mentions Topics/Code green button | ~15s | **fallback 1** |
| **doubao-seed-2.0-pro** | ✅ accurate: precise overlay positions | ~30s | fallback 2 |
| **MiniMax-M3** | ✅ accurate, OCR'd `alchaincyf/hermes_slides_maker` repo path | ~12s | fallback 3 |
| sensenova-6.7-flash-lite | ✅ but very brief | fast | skip |
| agnes-2.0-flash | ✅ hallucinated "右上角半透明灰色圆圈, 圈住导航栏右侧" (wrong) | fast | skip |
| mimo-v2.5 | ✅ but missed overlay positioning | fast | skip |
| kimi-k2.6 | � "engine overloaded" | — | avoid |
| kimi-k2.5 | ❌ 503 model_not_found | — | avoid |
| doubao-seed-2.1-turbo | ⏱️ timeout (30s+) | — | avoid |
| spark-x2 | ⏱️ timeout | — | avoid |
| hy3 | ❌ "Non-stream chat request is currently no[t supported]" | — | avoid |
| qwen3.6-flash-claude | ❌ "Access to model denied" | — | avoid |
| qwen3.8-max-preview-claude | ❌ "Access to model denied" | — | avoid |
| deepseek-v4-flash-claude | ❌ "Access to model denied" | — | avoid |
| doubao-embedding-vision | ❌ "no AgentPlan subscription" | — | avoid |
| doubao-seed-evolving | ❌ "no AgentPlan subscription" | — | avoid |
| glm-5.2 | ❌ "type 参数非法, 取值范围 ['text']" | — | avoid |
| LongCat-2.0 | ❌ "Token 额度不足" | — | avoid |

## Re-run scan

Use `scripts/scan_vision_models.py` — sends the same test question to all candidate models and prints pass/fail table. Run when:
- 503/timeout patterns change (model rotates behind distributor groups)
- A new model appears in `/v1/models` listing
- Quality regresses on the current chain

## Channel-rotation note

qingxiaoyun.net uses **distributor groups with rotating channels**. Same model can be `model_not_found` at one moment and `✅ works` at another (saw this with `kimi-k2.7-claude`: worked for 16-frame contact sheet at 23:14, 503 at 09:28 next day). The 4-model fallback chain absorbs this naturally.

## Endpoint / auth (one place, all models)

```
POST https://ai.qingxiaoyun.net/v1/chat/completions
Authorization: Bearer sk-YaP0IMQvlU5Wu3kfZUgTxA9YnoQO0IwbQixMNcYzKYle2sET
Content-Type: application/json
Body: OpenAI Chat Completions schema (model + messages + max_tokens)
```

Image input is `image_url` with `data:image/jpeg;base64,...` URL form. Works on all four fallback models.
