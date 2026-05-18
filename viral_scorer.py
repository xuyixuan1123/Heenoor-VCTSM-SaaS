#!/usr/bin/env python3
"""
VCTSM 六维打分核心模块
支持 LLM 调用（DeepSeek/豆包 API）和关键词规则两种模式
"""
import json, time, re
from urllib.request import Request, urlopen

DIMS = ['情绪密度', '痛点强度', '标题钩子', '社交货币', '论证深度', '情境代入感']

ANCHORS = {
    "情绪密度": {"1": "全文平铺直叙，无情绪峰值", "3": "有2-3处情绪起伏，但不密集", "5": "每300字1个以上情绪触发点，持续高唤醒"},
    "痛点强度": {"1": "痛点模糊/宽泛，难以代入", "3": "痛点具体但较普遍", "5": "痛点极具体尖锐，读者强烈感到'说的就是我'"},
    "标题钩子": {"1": "标题平淡，无悬念/利益/冲突", "3": "有一定吸引力", "5": "强烈好奇缺口/恐惧/期待/认知反差"},
    "社交货币": {"1": "分享后无助于提升形象", "3": "有一定谈资价值", "5": "分享后显得有品位/懂行/前沿/聪明"},
    "论证深度": {"1": "纯观点输出，无数据/案例", "3": "有部分数据或案例", "5": "数据充分、逻辑严密"},
    "情境代入感": {"1": "场景抽象笼统", "3": "场景较具体", "5": "场景极具体（时间/地点/人物/细节）"}
}

def call_deepseek(prompt: str, api_key: str, retries: int = 3) -> str:
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 500
    }).encode()
    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers=headers)
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))

def call_doubao(prompt: str, api_key: str, endpoint_id: str, retries: int = 3) -> str:
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = json.dumps({
        "model": endpoint_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 500
    }).encode()
    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers=headers)
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))

def parse_scores(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    scores = {}
    for dim in DIMS:
        m = re.search(rf'{dim}["\']?\s*[:：]\s*([\d.]+)', text)
        if m:
            scores[dim] = float(m.group(1))
    return scores if len(scores) == 6 else None

def build_prompt(title: str, body: str) -> str:
    sections = []
    for dim in DIMS:
        a = ANCHORS[dim]
        sections.append(f"### {dim}\n- 1分：{a['1']}\n- 3分：{a['3']}\n- 5分：{a['5']}")
    return f"""你是一位严格的内容编码专家。根据锚点标准，六维度打分（1-5分，允许半分）。

## 打分标准
{"\n\n".join(sections)}

## 文章
【标题】：{title}
【正文】：{body[:6000]}

## 输出
只输出JSON：{{"{DIMS[0]}": 分数, "{DIMS[1]}": 分数, "{DIMS[2]}": 分数, "{DIMS[3]}": 分数, "{DIMS[4]}": 分数, "{DIMS[5]}": 分数}}"""

def score_article(title: str, body: str, api_key: str, provider: str = "deepseek", endpoint_id: str = None) -> dict:
    prompt = build_prompt(title, body)
    if provider == "doubao":
        if not endpoint_id:
            raise ValueError("豆包需要 endpoint_id")
        resp = call_doubao(prompt, api_key, endpoint_id)
    else:
        resp = call_deepseek(prompt, api_key)
    scores = parse_scores(resp)
    if not scores:
        raise ValueError(f"JSON解析失败: {resp[:200]}")
    return scores
