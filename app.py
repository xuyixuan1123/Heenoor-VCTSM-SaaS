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

SCORING_RUBRIC = {
    "痛点强度": {"weight":25,"anchors":{"1":"痛点模糊/宽泛，难以代入","3":"痛点具体但较普遍，有一定代入感","5":"痛点极具体尖锐，读者强烈感到'说的就是我'"},"keywords":["没档次","异味","选礼难","纠结","普通","重金属","涂层脱落","漏水","烫手","焦虑","失眠","压力","迷茫","赚不到钱","被裁员","分手","被割韭菜","没面子","社恐","自卑","落后","错过","后悔","被坑","不值"]},
    "情绪密度": {"weight":16,"anchors":{"1":"全文平铺直叙，无情绪峰值","3":"有2-3处情绪起伏，但不密集","5":"每300字1个以上情绪触发点，持续高唤醒"},"keywords":["震惊","泪目","破防","沉默","窒息","头皮发麻","细思极恐","太绝了","心动","高级","精致","向往","惊喜","治愈","氛围感","燃","热血","愤怒","恶心","想哭","笑死","暖","被暖到","泪崩","安全感"]},
    "标题钩子": {"weight":16,"anchors":{"1":"标题平淡，无悬念/利益/冲突","3":"有一定吸引力，可点可不点","5":"强烈好奇缺口/恐惧/期待/认知反差，必须点进去"},"keywords":["真相","秘诀","反直觉","为什么","别再","避雷","保姆级","后悔没早买","竟然","以为","其实","终于","只有","别再被","对不起","我承认"]},
    "社交货币": {"weight":15,"anchors":{"1":"分享后无助于提升形象","3":"有一定谈资价值，身份表达不强","5":"分享后显得有品位/懂行/前沿/聪明"},"keywords":["品位","体面","背书","格调","高端","身份","送礼","拿得出手","审美在线","不落俗套","圈内","只有懂的人","进阶","内行","天花板"]},
    "论证深度": {"weight":12,"anchors":{"1":"纯观点输出，无数据/案例支撑","3":"有部分数据或案例，基本完整","5":"数据充分、逻辑严密、原创框架/模型"},"keywords":["纯钛","真空","工艺","专利","内胆","抑菌","无涂层","数据","研究表明","实验","对比","实测","%","倍","排名","引用"]},
    "情境代入感": {"weight":16,"anchors":{"1":"场景抽象笼统，难以代入","3":"场景较具体，有一定代入感","5":"场景极具体（时间/地点/人物/细节），如临其境"},"keywords":["办公室","会议","出差","打开那一刻","礼盒","床头","地铁上","周末早晨","接孩子","过年回家","第一次约会","团建","年终总结","搬家那天","楼下超市"]}
}

DIMENSIONS = list(SCORING_RUBRIC.keys())
DIM_TIPS = {"情绪密度":"在关键段落加入情感爆发点：愤怒质问、震撼数据、泪点故事、反转结局","痛点强度":"把痛点升级为「具体场景+身份标签+后果放大」，让读者觉得「说的就是我」","标题钩子":"加入好奇缺口（'竟然'）、利益承诺（'3个方法'）、认知反差（'你以为的...其实...'）","社交货币":"让内容成为读者的'谈资'：提供新知、反常识观点、圈层暗语、可炫耀的工具/方法","论证深度":"补充具体数据、案例、研究引用、对比表格、或原创分析框架","情境代入感":"增加具体场景描写：时间/地点/人物/对话/细节，让读者脑中自动'放电影'"}

def keyword_score(text:str)->dict:
    if not isinstance(text,str) or not text.strip(): return {dim:2.5 for dim in DIMENSIONS}
    kw_source = st.session_state.get("custom_keywords") or SCORING_RUBRIC
    result = {}
    for dim in DIMENSIONS:
        kws = kw_source.get(dim, {}).get("keywords", []) if isinstance(kw_source.get(dim), dict) else []
        match_count = sum(1 for kw in kws if kw in text)
        result[dim] = round(min(5.0, 2.5 + match_count * 0.3), 1)
    return result

def _read_secret_or_env(name:str):
    try:
        v=st.secrets.get(name)
        if v: return str(v)
    except: pass
    p=Path.home()/".hermes"/".env"
    if p.exists():
        for l in p.read_text().splitlines():
            if l.startswith(f"{name}="): return l.split("=",1)[1].strip().strip('"').strip("'")
    return None

DB_API_KEY=_read_secret_or_env("DOUBAO_API_KEY")
DB_ENDPOINT=_read_secret_or_env("DOUBAO_ENDPOINT_ID")

def build_prompt(title:str,body:str)->str:
    ss=[]
    for d in DIMENSIONS:
        a=SCORING_RUBRIC[d]["anchors"]
        ss.append(f"### {d}\n- 1分：{a['1']}\n- 3分：{a['3']}\n- 5分：{a['5']}")
    return f"""你是一位严格的内容编码专家。根据锚点标准，对文章六维度逐一打分（1-5分，允许半分如3.5）。

## 打分标准
{"\n\n".join(ss)}

## 待评分文章
【标题】：{title}
【正文】：{body[:6000]}

## 输出格式
只输出JSON：{{"{DIMENSIONS[0]}": 分数, "{DIMENSIONS[1]}": 分数, "{DIMENSIONS[2]}": 分数, "{DIMENSIONS[3]}": 分数, "{DIMENSIONS[4]}": 分数, "{DIMENSIONS[5]}": 分数}}"""

def call_llm(prompt:str,provider:str="doubao",retries:int=3)->str:
    if not DB_API_KEY or not DB_ENDPOINT: raise RuntimeError("未配置 DOUBAO_API_KEY / DOUBAO_ENDPOINT_ID")
    url="https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers={"Content-Type":"application/json","Authorization":f"Bearer {DB_API_KEY}"}
    payload=json.dumps({"model":DB_ENDPOINT,"messages":[{"role":"user","content":prompt}],"temperature":0.3,"max_tokens":500}).encode()
    for a in range(retries):
        try:
            req=Request(url,data=payload,headers=headers)
            with urlopen(req,timeout=60) as r: return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception as e:
            if a==retries-1: raise
            time.sleep(3*(a+1))

def parse_scores(text:str)->dict:
    try: return json.loads(text)
    except: pass
    m=re.search(r'\{[^{}]*\}',text,re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass
    sc={}
    for d in DIMENSIONS:
        m2=re.search(rf'{d}["\']?\s*[:：]\s*([\d.]+)',text)
        if m2: sc[d]=float(m2.group(1))
    return sc if len(sc)==6 else None

def radar_chart(scores:dict):
    vals=[scores.get(d,3) for d in DIMENSIONS]; vals.append(vals[0])
    dc=DIMENSIONS+[DIMENSIONS[0]]
    fig=go.Figure()
    fig.add_trace(go.Scatterpolar(r=vals,theta=dc,fill='toself',fillcolor='rgba(255,107,53,0.25)',line=dict(color='#FF6B35',width=2.5),name='得分'))
    fig.add_trace(go.Scatterpolar(r=[3]*len(dc),theta=dc,line=dict(color='gray',width=1,dash='dot'),name='基准',showlegend=False))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0,5],tickvals=[1,2,3,4,5],gridcolor='#e5e5e5'),angularaxis=dict(gridcolor='#e5e5e5')),height=400,margin=dict(l=40,r=40,t=20,b=20),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    return fig

def score_level(t:float)->str:
    if t>=80: return "🔥 高爆款潜力"
    if t>=65: return "👍 较好潜力"
    if t>=50: return "📝 中等潜力"
    return "🔍 低潜力"

def suggestions(sc:dict): return [f"**{d}**（{s:.1f}分）：{DIM_TIPS[d]}" for d,s in sc.items() if s<3.5]

def calc_total_custom(sc:dict)->float:
    t=0.0
    for d in DIMENSIONS: t+=sc.get(d,3)/5*st.session_state.get("custom_weights",{}).get(d,SCORING_RUBRIC[d]["weight"])
    return round(t,1)

st.set_page_config(page_title="VCTSM · 爆款内容打分",page_icon="🔥",layout="wide")

with st.sidebar:
    st.title("🔥 VCTSM")
    st.caption("Viral Content Theoretical Scoring Model")
    st.markdown("---")
    st.markdown("**🧠 评分引擎**")
    engine=st.radio("engine",["🫘 豆包（免费额度）","⚡ 关键词（免费）"],label_visibility="collapsed")
    use_llm="豆包" in engine
    llm_provider="doubao" if use_llm else None
    if use_llm and (not DB_API_KEY or not DB_ENDPOINT): st.warning("⚠️ 未配置 DOUBAO_API_KEY / DOUBAO_ENDPOINT_ID")
    st.markdown("---")
    st.markdown("**⚙️ 六维权重**")
    st.caption("拖拽调整，自动归一化")
    defaults={d:i["weight"] for d,i in SCORING_RUBRIC.items()}
    if "raw_weights" not in st.session_state: st.session_state.raw_weights=dict(defaults)
    raw={}
    for d in DIMENSIONS: raw[d]=st.slider(d,0,100,st.session_state.raw_weights.get(d,defaults[d]),step=1,key=f"w_{d}")
    st.session_state.raw_weights=dict(raw)
    tw=sum(raw.values())
    cw={d:round(v/tw*100,1) if tw>0 else 0 for d,v in raw.items()}
    st.session_state.custom_weights=cw
    st.caption(" · ".join(f"{d[:2]} {w}%" for d,w in cw.items()))
    def _reset_weights():
        st.session_state.raw_weights=dict(defaults)
        for d in DIMENSIONS: st.session_state[f"w_{d}"]=defaults[d]
    if st.button("🔄 恢复默认权重",use_container_width=True,on_click=_reset_weights):
        st.toast("✅ 权重已恢复默认",icon="🔄")
    st.markdown("---")
    st.markdown("**📝 品类关键词库**")
    with st.expander("📤 上传自定义词库 (JSON)"):
        st.caption("换品类只需替换词库，六维模型不变")
        kw_file=st.file_uploader("上传 JSON 词库文件",type=["json"],key="kw_upload",help='格式: {"痛点强度":{"keywords":["词1","词2"]},...}')
        if kw_file:
            try:
                custom_kw=json.loads(kw_file.read())
                st.session_state.custom_keywords=custom_kw
                st.success(f"✅ 已加载 {len(custom_kw)} 个维度的自定义词库")
            except Exception as e: st.error(f"JSON 解析失败: {e}")
        if st.button("🔄 恢复默认词库",use_container_width=True):
            st.session_state.pop("custom_keywords",None)
            st.rerun()
        st.caption("当前：自定义词库" if st.session_state.get("custom_keywords") else "当前：希诺保温杯默认词库")
    mode=st.radio("📋 模式",["📝 单篇打分","📊 批量分析"],label_visibility="collapsed")
    st.markdown("---")
    st.caption("豆包 / 关键词 · 社交货币 · 情绪唤醒 · 使用与满足")

st.title("爆款内容六维打分工具")
st.caption(f"当前引擎：{engine}  |  让你对内容的判断从「感觉」变成可量化的数学语言。")

if mode=="📝 单篇打分":
    title=st.text_input("文章标题",placeholder="粘贴标题...")
    body=st.text_area("文章正文",height=260,placeholder="粘贴正文内容...")
    disabled=not body.strip() or (use_llm and (not DB_API_KEY or not DB_ENDPOINT))
    if st.button("🔍 开始打分",type="primary",use_container_width=True,disabled=disabled):
        with st.spinner("AI 正在从六个维度深度分析..." if use_llm else "分析中..."):
            try:
                if use_llm:
                    resp=call_llm(build_prompt(title or "无标题",body))
                    scores=parse_scores(resp)
                    if not scores: st.error("LLM 回复解析失败"); st.code(resp[:300]); st.stop()
                else: scores=keyword_score(body)
                total=calc_total_custom(scores)
                st.success(f"综合分 **{total:.1f}/100** — {score_level(total)}")
                st.markdown("---")
                c1,c2=st.columns([1,1.2])
                with c1: st.plotly_chart(radar_chart(scores),use_container_width=True)
                with c2:
                    st.markdown("### 📋 六维得分")
                    st.dataframe(pd.DataFrame([{"维度":d,"得分":f"{scores.get(d,0):.1f}/5","权重":f"{cw.get(d,0):.1f}%"} for d in DIMENSIONS]),hide_index=True,use_container_width=True)
                tips=suggestions(scores)
                if tips:
                    st.markdown("### 💡 优化建议")
                    for i,t in enumerate(tips,1): st.markdown(f"{i}. {t}")
                else: st.info("✅ 所有维度均 ≥ 3.5 分，内容质量较高！")
            except Exception as e: st.error(f"打分失败：{e}")

else:
    st.markdown("### 📤 上传样本数据")
    st.caption("支持 Excel (.xlsx) 或 CSV，需包含「内容」或「正文」列。可选「是否爆款」列用于统计验证。")
    uploaded=st.file_uploader("选择文件",type=["xlsx","csv"])
    if uploaded:
        df=pd.read_csv(uploaded) if uploaded.name.endswith('.csv') else pd.read_excel(uploaded)
        st.caption(f"共 **{len(df)}** 条记录")
        st.dataframe(df.head(5),hide_index=True,use_container_width=True)
        text_col=None
        for c in ["内容","正文","body","text","content"]:
            if c in df.columns: text_col=c; break
        if not text_col: st.error("未找到文本列！"); st.stop()
        if use_llm and (not DB_API_KEY or not DB_ENDPOINT):
            st.error("豆包引擎未配置密钥。")
        else:
            delay=st.slider("调用间隔（秒）",0.0,5.0,0.0 if not use_llm else 1.0,0.5,disabled=not use_llm) if use_llm else 0
            if st.button("🚀 开始批量分析",type="primary",use_container_width=True):
                total_n=len(df)
                progress=st.progress(0,f"0/{total_n}")
                status=st.empty()
                results=[]
                for i,row in df.iterrows():
                    text=str(row[text_col]) if pd.notna(row[text_col]) else ""
                    ttl=str(row.get("标题","")) if pd.notna(row.get("标题","")) else ""
                    if not text.strip(): continue
                    status.text(f"[{i+1}/{total_n}] {text[:40]}...")
                    try:
                        if use_llm:
                            resp=call_llm(build_prompt(ttl,text))
                            scores=parse_scores(resp)
                            if not scores: scores={d:0 for d in DIMENSIONS}
                        else: scores=keyword_score(text)
                        rd=row.to_dict(); rd.update(scores)
                        rd["综合分"]=calc_total_custom(scores); rd["等级"]=score_level(rd["综合分"])
                        results.append(rd)
                    except Exception as e:
                        rd=row.to_dict(); rd["综合分"]=f"ERROR:{e}"; results.append(rd)
                    progress.progress((i+1)/total_n,f"{i+1}/{total_n}")
                    if delay>0: time.sleep(delay)
                progress.empty(); status.empty()
                df_out=pd.DataFrame(results)
                valid=[r for r in results if isinstance(r.get("综合分"),(int,float))]
                st.success(f"✅ 完成！有效结果 {len(valid)}/{total_n} 篇")
                if valid:
                    sl=[r["综合分"] for r in valid]
                    c1,c2,c3,c4=st.columns(4)
                    c1.metric("平均分",f"{np.mean(sl):.1f}"); c2.metric("中位数",f"{np.median(sl):.1f}")
                    c3.metric("最高分",f"{max(sl):.1f}"); c4.metric("最低分",f"{min(sl):.1f}")
                    bins={"🔥 ≥80":sum(1 for s in sl if s>=80),"👍 65-79":sum(1 for s in sl if 65<=s<80),"📝 50-64":sum(1 for s in sl if 50<=s<65),"🔍 <50":sum(1 for s in sl if s<50)}
                    fig_bar=px.bar(x=list(bins.keys()),y=list(bins.values()),color=list(bins.keys()),color_discrete_map={"🔥 ≥80":"#FF6B35","👍 65-79":"#FFA726","📝 50-64":"#42A5F5","🔍 <50":"#90A4AE"},labels={"x":"等级","y":"篇数"})
                    fig_bar.update_layout(showlegend=False,height=280)
                    st.plotly_chart(fig_bar,use_container_width=True)
                    fig_hist=px.histogram(df_out,x="综合分",nbins=20,color_discrete_sequence=["#FF6B35"],labels={"综合分":"综合得分","count":"篇数"})
                    fig_hist.update_layout(height=280)
                    st.plotly_chart(fig_hist,use_container_width=True)
                cdl1,cdl2=st.columns(2)
                with cdl1:
                    cb=io.StringIO(); df_out.to_csv(cb,index=False,encoding="utf-8-sig")
                    st.download_button("📥 下载 CSV",cb.getvalue(),"vctsm_result.csv","text/csv",use_container_width=True)
                with cdl2:
                    xb=io.BytesIO()
                    with pd.ExcelWriter(xb,engine='xlsxwriter') as w: df_out.to_excel(w,index=False,sheet_name='VCTSM分析结果')
                    st.download_button("📥 下载 Excel",xb.getvalue(),"vctsm_result.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
                if "是否爆款" in df_out.columns: st.info("📊 数据含「是否爆款」列 — 可在本地运行 `python3 analyze.py 结果.csv` 做统计验证")
