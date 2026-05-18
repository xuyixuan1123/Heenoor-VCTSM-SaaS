"""
VCTSM 爆款内容六维打分工具 — 双引擎版
- LLM 引擎: DeepSeek AI 语义理解，精准
- 关键词引擎: 规则匹配，快速免费
- 单篇 + 批量 · Excel/CSV · 雷达图 + 优化建议
"""
import sys, os, json, time, csv, io, re, math
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# ── 六维模型定义 ──
SCORING_RUBRIC = {
    "痛点强度": {
        "weight": 25,
        "anchors": {
            "1": "痛点模糊/宽泛，难以代入",
            "3": "痛点具体但较普遍，有一定代入感",
            "5": "痛点极具体尖锐，读者强烈感到'说的就是我'"
        },
        "keywords": ["没档次", "异味", "选礼难", "纠结", "普通", "重金属", "涂层脱落", "漏水", "烫手",
                      "焦虑", "失眠", "压力", "迷茫", "赚不到钱", "被裁员", "分手", "被割韭菜",
                      "没面子", "社恐", "自卑", "落后", "错过", "后悔", "被坑", "不值"]
    },
    "情绪密度": {
        "weight": 16,
        "anchors": {
            "1": "全文平铺直叙，无情绪峰值",
            "3": "有2-3处情绪起伏，但不密集",
            "5": "每300字1个以上情绪触发点，持续高唤醒"
        },
        "keywords": ["震惊", "泪目", "破防", "沉默", "窒息", "头皮发麻", "细思极恐", "太绝了",
                      "心动", "高级", "精致", "向往", "惊喜", "治愈", "氛围感", "燃", "热血",
                      "愤怒", "恶心", "想哭", "笑死", "暖", "被暖到", "泪崩", "安全感"]
    },
    "标题钩子": {
        "weight": 16,
        "anchors": {
            "1": "标题平淡，无悬念/利益/冲突",
            "3": "有一定吸引力，可点可不点",
            "5": "强烈好奇缺口/恐惧/期待/认知反差，必须点进去"
        },
        "keywords": ["真相", "秘诀", "反直觉", "为什么", "别再", "避雷", "保姆级", "后悔没早买",
                      "竟然", "以为", "其实", "终于", "只有", "别再被", "对不起", "我承认"]
    },
    "社交货币": {
        "weight": 15,
        "anchors": {
            "1": "分享后无助于提升形象",
            "3": "有一定谈资价值，身份表达不强",
            "5": "分享后显得有品位/懂行/前沿/聪明"
        },
        "keywords": ["品位", "体面", "背书", "格调", "高端", "身份", "送礼", "拿得出手",
                      "审美在线", "不落俗套", "圈内", "只有懂的人", "进阶", "内行", "天花板"]
    },
    "论证深度": {
        "weight": 12,
        "anchors": {
            "1": "纯观点输出，无数据/案例支撑",
            "3": "有部分数据或案例，基本完整",
            "5": "数据充分、逻辑严密、原创框架/模型"
        },
        "keywords": ["纯钛", "真空", "工艺", "专利", "内胆", "抑菌", "无涂层", "数据",
                      "研究表明", "实验", "对比", "实测", "%", "倍", "排名", "引用"]
    },
    "情境代入感": {
        "weight": 16,
        "anchors": {
            "1": "场景抽象笼统，难以代入",
            "3": "场景较具体，有一定代入感",
            "5": "场景极具体（时间/地点/人物/细节），如临其境"
        },
        "keywords": ["办公室", "会议", "出差", "打开那一刻", "礼盒", "床头",
                      "地铁上", "周末早晨", "接孩子", "过年回家", "第一次约会",
                      "团建", "年终总结", "搬家那天", "楼下超市"]
    }
}

DIMENSIONS = list(SCORING_RUBRIC.keys())
DIM_TIPS = {
    "情绪密度": "在关键段落加入情感爆发点：愤怒质问、震撼数据、泪点故事、反转结局",
    "痛点强度": "把痛点升级为「具体场景+身份标签+后果放大」，让读者觉得「说的就是我」",
    "标题钩子": "加入好奇缺口（'竟然'）、利益承诺（'3个方法'）、认知反差（'你以为的...其实...'）",
    "社交货币": "让内容成为读者的'谈资'：提供新知、反常识观点、圈层暗语、可炫耀的工具/方法",
    "论证深度": "补充具体数据、案例、研究引用、对比表格、或原创分析框架",
    "情境代入感": "增加具体场景描写：时间/地点/人物/对话/细节，让读者脑中自动'放电影'",
}


# ═══════════════════════════════════════════
# 引擎 1: 关键词规则打分（快速 & 免费）
# ═══════════════════════════════════════════
def keyword_score(text: str) -> dict:
    """基于关键词匹配的六维打分 (1-10分制，映射到1-5分)"""
    if not isinstance(text, str) or not text.strip():
        return {dim: 2.5 for dim in DIMENSIONS}

    scores = {}
    kw_source = st.session_state.get("custom_keywords") or SCORING_RUBRIC
    for dim in DIMENSIONS:
        kws = kw_source.get(dim, {}).get("keywords", []) if isinstance(kw_source.get(dim), dict) else []
        match_count = sum(1 for kw in kws if kw in text)
        # 基础分 2.5 + 每命中1个关键词 0.3 分，上限 5
        raw = min(5.0, 2.5 + match_count * 0.3)
        scores[dim] = round(raw, 1)
    return scores


# ═══════════════════════════════════════════
# LLM 引擎配置（DeepSeek / 豆包）
# ═══════════════════════════════════════════
def _read_secret_or_env(name: str) -> str | None:
    """读取密钥：Streamlit Secrets 优先，其次 ~/.hermes/.env"""
    try:
        val = st.secrets.get(name)
        if val: return val
    except Exception:
        pass
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

DS_API_KEY = _read_secret_or_env("DEEPSEEK_API_KEY")
DB_API_KEY = _read_secret_or_env("DOUBAO_API_KEY")
DB_ENDPOINT = _read_secret_or_env("DOUBAO_ENDPOINT_ID")  # 豆包接入点 ID，如 ep-2024xxx

def build_prompt(title: str, body: str) -> str:
    dim_sections = []
    for dim in DIMENSIONS:
        a = SCORING_RUBRIC[dim]["anchors"]
        dim_sections.append(f"### {dim}\n- 1分：{a['1']}\n- 3分：{a['3']}\n- 5分：{a['5']}")

    dim_text = "\n\n".join(dim_sections)
    dim_names = "、".join(DIMENSIONS)

    return f"""你是一位严格的内容编码专家。根据锚点标准，对文章六维度逐一打分（1-5分，允许半分如3.5）。

## 打分标准
{dim_text}

## 待评分文章
【标题】：{title}
【正文】：{body[:6000]}

## 输出格式
只输出JSON：{{"{DIMENSIONS[0]}": 分数, "{DIMENSIONS[1]}": 分数, "{DIMENSIONS[2]}": 分数, "{DIMENSIONS[3]}": 分数, "{DIMENSIONS[4]}": 分数, "{DIMENSIONS[5]}": 分数}}"""


def call_llm(prompt: str, provider: str = "deepseek", retries: int = 3) -> str:
    """统一的 LLM 调用，根据 provider 路由"""
    payload = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 500,
        **({"model": "deepseek-chat"} if provider == "deepseek" else {})
    }).encode()

    if provider == "doubao":
        if not DB_API_KEY or not DB_ENDPOINT:
            raise RuntimeError("未配置 DOUBAO_API_KEY 或 DOUBAO_ENDPOINT_ID")
        url = f"https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DB_API_KEY}"
        }
        # 豆包需要在 body 里传 model=endpoint_id
        payload = json.dumps({
            "model": DB_ENDPOINT,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3, "max_tokens": 500
        }).encode()
    else:
        if not DS_API_KEY:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DS_API_KEY}"
        }

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
    for dim in DIMENSIONS:
        m = re.search(rf'{dim}["\']?\s*[:：]\s*([\d.]+)', text)
        if m:
            scores[dim] = float(m.group(1))
    return scores if len(scores) == 6 else None


# ═══════════════════════════════════════════
# 可视化
# ═══════════════════════════════════════════
def radar_chart(scores: dict):
    values = [scores.get(d, 3) for d in DIMENSIONS]
    values.append(values[0])
    dims_closed = DIMENSIONS + [DIMENSIONS[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values, theta=dims_closed,
        fill='toself', fillcolor='rgba(255,107,53,0.25)',
        line=dict(color='#FF6B35', width=2.5), name='得分'))
    fig.add_trace(go.Scatterpolar(r=[3]*len(dims_closed), theta=dims_closed,
        line=dict(color='gray', width=1, dash='dot'), name='基准', showlegend=False))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0,5], tickvals=[1,2,3,4,5], gridcolor='#e5e5e5'),
                    angularaxis=dict(gridcolor='#e5e5e5')),
        height=400, margin=dict(l=40, r=40, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig


def score_level(total: float) -> str:
    if total >= 80: return "🔥 高爆款潜力"
    elif total >= 65: return "👍 较好潜力"
    elif total >= 50: return "📝 中等潜力"
    else: return "🔍 低潜力"


def suggestions(scores: dict):
    tips = []
    for dim, s in scores.items():
        if s < 3.5:
            tips.append(f"**{dim}**（{s:.1f}分）：{DIM_TIPS.get(dim, '')}")
    return tips


def calc_total_custom(scores: dict) -> float:
    total = 0.0
    for dim in DIMENSIONS:
        w = st.session_state.get("custom_weights", {}).get(dim, SCORING_RUBRIC[dim]["weight"])
        total += scores.get(dim, 3) / 5 * w
    return round(total, 1)


# ═══════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════
st.set_page_config(page_title="VCTSM · 爆款内容打分", page_icon="🔥", layout="wide")

# ── Sidebar ──
with st.sidebar:
    st.title("🔥 VCTSM")
    st.caption("Viral Content Theoretical Scoring Model")

    # 引擎选择
    st.markdown("---")
    st.markdown("**🧠 评分引擎**")
    engine = st.radio("engine", [
        "🫘 豆包（免费额度）",
        "⚡ 关键词（免费）"
    ], label_visibility="collapsed")
    use_llm = "豆包" in engine
    llm_provider = "doubao" if use_llm else None

    if use_llm and (not DB_API_KEY or not DB_ENDPOINT):
        st.warning("⚠️ 未配置 DOUBAO_API_KEY 或 DOUBAO_ENDPOINT_ID")

    # 权重调整
    st.markdown("---")
    st.markdown("**⚙️ 六维权重**")
    st.caption("拖拽调整，自动归一化")

    default_weights = {dim: info["weight"] for dim, info in SCORING_RUBRIC.items()}
    if "raw_weights" not in st.session_state:
        st.session_state.raw_weights = dict(default_weights)

    raw = {}
    for dim in DIMENSIONS:
        raw[dim] = st.slider(dim, 0, 100, st.session_state.raw_weights.get(dim, default_weights[dim]),
                              step=1, key=f"w_{dim}")
    st.session_state.raw_weights = dict(raw)

    total_w = sum(raw.values())
    custom_weights = {dim: round(v / total_w * 100, 1) if total_w > 0 else 0 for dim, v in raw.items()}
    st.session_state.custom_weights = custom_weights

    st.caption(" · ".join(f"{dim[:2]} {w}%" for dim, w in custom_weights.items()))

    if st.button("🔄 恢复默认权重", use_container_width=True):
        for d in DIMENSIONS:
            st.session_state.pop(f"w_{d}", None)
        st.session_state.pop("raw_weights", None)
        st.rerun()

    # 关键词库
    st.markdown("---")
    st.markdown("**📝 品类关键词库**")
    with st.expander("📤 上传自定义词库 (JSON)"):
        st.caption("换品类只需替换词库，六维模型不变")
        kw_file = st.file_uploader("上传 JSON 词库文件", type=["json"], key="kw_upload",
                                   help='格式: {"痛点强度":{"keywords":["词1","词2"]},...}')
        if kw_file:
            try:
                custom_kw = json.loads(kw_file.read())
                st.session_state.custom_keywords = custom_kw
                st.success(f"✅ 已加载 {len(custom_kw)} 个维度的自定义词库")
            except Exception as e:
                st.error(f"JSON 解析失败: {e}")
        if st.button("🔄 恢复默认词库", use_container_width=True):
            st.session_state.pop("custom_keywords", None)
            st.rerun()
        if st.session_state.get("custom_keywords"):
            st.caption("当前：自定义词库")
        else:
            st.caption("当前：希诺保温杯默认词库")
    mode = st.radio("📋 模式", ["📝 单篇打分", "📊 批量分析"], label_visibility="collapsed")

    st.markdown("---")
    st.caption("豆包 / 关键词 · 社交货币 · 情绪唤醒 · 使用与满足")


# ═══════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════
st.title("爆款内容六维打分工具")
st.caption(f"当前引擎：{engine}  |  让你对内容的判断从「感觉」变成可量化的数学语言。")

# ───── 单篇打分 ─────
if mode == "📝 单篇打分":
    title = st.text_input("文章标题", placeholder="粘贴标题...")
    body = st.text_area("文章正文", height=260, placeholder="粘贴正文内容...")

    disabled = not body.strip() or (use_llm and (not DB_API_KEY or not DB_ENDPOINT))
    if st.button("🔍 开始打分", type="primary", use_container_width=True, disabled=disabled):
        with st.spinner("分析中..." if not use_llm else "AI 正在从六个维度深度分析..."):
            try:
                if use_llm:
                    prompt = build_prompt(title or "无标题", body)
                    response = call_llm(prompt, provider=llm_provider)
                    scores = parse_scores(response)
                    if not scores:
                        st.error("LLM 回复解析失败，请重试")
                        st.code(response[:300])
                        st.stop()
                else:
                    scores = keyword_score(body)

                total = calc_total_custom(scores)
                level = score_level(total)

                st.success(f"综合分 **{total:.1f}/100** — {level}")
                st.markdown("---")

                c1, c2 = st.columns([1, 1.2])
                with c1:
                    st.plotly_chart(radar_chart(scores), use_container_width=True)
                with c2:
                    st.markdown("### 📋 六维得分")
                    st.dataframe(pd.DataFrame([
                        {"维度": d, "得分": f"{scores.get(d,0):.1f}/5", "权重": f"{custom_weights.get(d,0):.1f}%"}
                        for d in DIMENSIONS
                    ]), hide_index=True, use_container_width=True)

                tips = suggestions(scores)
                if tips:
                    st.markdown("### 💡 优化建议")
                    for i, tip in enumerate(tips, 1):
                        st.markdown(f"{i}. {tip}")
                else:
                    st.info("✅ 所有维度均 ≥ 3.5 分，内容质量较高！")

            except Exception as e:
                st.error(f"打分失败：{e}")

# ───── 批量分析 ─────
else:
    st.markdown("### 📤 上传样本数据")
    st.caption("支持 Excel (.xlsx) 或 CSV，需包含「内容」列（或「标题」+「正文」列）。可选「是否爆款」列用于后续统计验证。")

    uploaded = st.file_uploader("选择文件", type=["xlsx", "csv"])

    if uploaded:
        # 读取
        if uploaded.name.endswith('.csv'):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)

        st.caption(f"共 **{len(df)}** 条记录")
        st.dataframe(df.head(5), hide_index=True, use_container_width=True)

        # 检测文本列
        text_col = None
        for col in ["内容", "正文", "body", "text", "content"]:
            if col in df.columns:
                text_col = col
                break
        if text_col is None:
            st.error("未找到文本列！请确保表格包含「内容」或「正文」列。")
            st.stop()

        if use_llm and (not DB_API_KEY or not DB_ENDPOINT):
            st.error("豆包引擎未配置密钥，请在 Secrets 中设置 DOUBAO_API_KEY 和 DOUBAO_ENDPOINT_ID。")
        else:
            delay = st.slider("调用间隔（秒）", 0.0, 5.0, 0.0 if not use_llm else 1.0, 0.5,
                              disabled=not use_llm) if use_llm else 0

            if st.button("🚀 开始批量分析", type="primary", use_container_width=True):
                total_n = len(df)
                progress = st.progress(0, f"0/{total_n}")
                status = st.empty()

                results = []
                for i, row in df.iterrows():
                    text = str(row[text_col]) if pd.notna(row[text_col]) else ""
                    title = str(row.get("标题", "")) if pd.notna(row.get("标题", "")) else ""
                    if not text.strip():
                        continue

                    status.text(f"[{i+1}/{total_n}] {text[:40]}...")
                    try:
                        if use_llm:
                            prompt = build_prompt(title, text)
                            resp = call_llm(prompt, provider=llm_provider)
                            scores = parse_scores(resp)
                            if not scores:
                                scores = {dim: 0 for dim in DIMENSIONS}
                        else:
                            scores = keyword_score(text)

                        row_dict = row.to_dict()
                        row_dict.update(scores)
                        row_dict["综合分"] = calc_total_custom(scores)
                        row_dict["等级"] = score_level(row_dict["综合分"])
                        results.append(row_dict)
                    except Exception as e:
                        row_dict = row.to_dict()
                        row_dict["综合分"] = f"ERROR: {e}"
                        results.append(row_dict)

                    progress.progress((i + 1) / total_n, f"{i+1}/{total_n}")
                    if delay > 0:
                        time.sleep(delay)

                progress.empty()
                status.empty()

                df_out = pd.DataFrame(results)
                valid = [r for r in results if isinstance(r.get("综合分"), (int, float))]
                st.success(f"✅ 完成！有效结果 {len(valid)}/{total_n} 篇")

                # 统计
                if valid:
                    slist = [r["综合分"] for r in valid]
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("平均分", f"{np.mean(slist):.1f}")
                    c2.metric("中位数", f"{np.median(slist):.1f}")
                    c3.metric("最高分", f"{max(slist):.1f}")
                    c4.metric("最低分", f"{min(slist):.1f}")

                    # 等级分布
                    bins = {"🔥 ≥80": sum(1 for s in slist if s>=80),
                            "👍 65-79": sum(1 for s in slist if 65<=s<80),
                            "📝 50-64": sum(1 for s in slist if 50<=s<65),
                            "🔍 <50": sum(1 for s in slist if s<50)}
                    fig_bar = px.bar(x=list(bins.keys()), y=list(bins.values()),
                                     color=list(bins.keys()),
                                     color_discrete_map={"🔥 ≥80":"#FF6B35","👍 65-79":"#FFA726",
                                                         "📝 50-64":"#42A5F5","🔍 <50":"#90A4AE"},
                                     labels={"x":"等级","y":"篇数"})
                    fig_bar.update_layout(showlegend=False, height=280)
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # 直方图
                    fig_hist = px.histogram(df_out, x="综合分", nbins=20,
                                            color_discrete_sequence=["#FF6B35"],
                                            labels={"综合分":"综合得分","count":"篇数"})
                    fig_hist.update_layout(height=280)
                    st.plotly_chart(fig_hist, use_container_width=True)

                # 下载
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    csv_buf = io.StringIO()
                    df_out.to_csv(csv_buf, index=False, encoding="utf-8-sig")
                    st.download_button("📥 下载 CSV", csv_buf.getvalue(),
                                       "vctsm_result.csv", "text/csv", use_container_width=True)
                with col_dl2:
                    xlsx_buf = io.BytesIO()
                    with pd.ExcelWriter(xlsx_buf, engine='xlsxwriter') as w:
                        df_out.to_excel(w, index=False, sheet_name='VCTSM分析结果')
                    st.download_button("📥 下载 Excel", xlsx_buf.getvalue(),
                                       "vctsm_result.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)

                # 是否爆款提示
                if "是否爆款" in df_out.columns:
                    st.info("📊 数据含「是否爆款」列 — 可在本地运行 `python3 analyze.py 结果.csv` 做统计验证")
