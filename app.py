import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import platform
import io

# --- 1. 环境配置 ---
if platform.system() == "Windows":
    plt.rcParams['font.sans-serif'] = ['SimHei']
elif platform.system() == "Darwin":
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="希诺 VCTSM 批量分析系统", layout="wide")

# --- 2. 核心 AI 模拟引擎 (增加批量处理支持) ---
def ai_analyze_batch(text):
    """单条文案评分逻辑"""
    base_scores = {
        "社交货币": 5.0, "标题钩子": 5.0, "情境代入": 5.0, 
        "情绪唤醒": 5.0, "论证深度": 5.0, "痛点强度": 5.0
    }
# 找到这一段进行修改
    keywords = {
        "社交货币": ["品位", "体面", "背书", "格调", "高端", "身份", "送礼", "拿得出手", "审美在线", "不落俗套"],
        "标题钩子": ["真相", "秘诀", "反直觉", "为什么", "别再", "避雷", "保姆级", "后悔没早买"],
        "情境代入": ["办公室", "会议", "出差", "打开那一刻", "礼盒", "车载", "健身房", "床头"],
        "情绪唤醒": ["心动", "高级", "精致", "向往", "惊喜", "入股不亏", "被问要链接", "治愈", "氛围感"],
        "论证深度": ["纯钛", "真空", "工艺", "专利", "内胆", "抑菌", "无涂层", "双层抽真空", "冷萃"],
        "痛点强度": ["没档次", "异味", "选礼难", "纠结", "普通", "重金属", "涂层脱落", "漏水", "烫手"]
    }
    if not isinstance(text, str): return base_scores
    for dim, kw_list in keywords.items():
        match_count = sum(1 for kw in kw_list if kw in text)
        base_scores[dim] = min(10.0, base_scores[dim] + match_count * 1.5)
    return base_scores

# --- 3. 页面侧边栏：参数配置 ---
st.sidebar.title("⚙️ 权重配置")
w_social = st.sidebar.slider("社交货币权重", 0.0, 1.0, 0.3)
w_hook = st.sidebar.slider("标题钩子权重", 0.0, 1.0, 0.2)
w_context = st.sidebar.slider("情境代入权重", 0.0, 1.0, 0.2)
w_emotion = st.sidebar.slider("情绪唤醒权重", 0.0, 1.0, 0.15)
w_depth = st.sidebar.slider("论证深度权重", 0.0, 1.0, 0.1)
w_pain = st.sidebar.slider("痛点强度权重", 0.0, 1.0, 0.05)

weights = {
    "社交货币": w_social, "标题钩子": w_hook, "情境代入": w_context,
    "情绪唤醒": w_emotion, "论证深度": w_depth, "痛点强度": w_pain
}

# --- 4. 主界面 ---
st.title("🚀 VCTSM 样本批量研究工作台")
st.info("作为研究员，你可以上传小红书/公众号的样本 Excel，系统将自动完成 1000 篇级别的量化。")

uploaded_file = st.file_uploader("上传 Excel 样本文件 (需包含一列名为 '内容' 的文本)", type=["xlsx", "csv"])

if uploaded_file:
    # 读取数据
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    
    st.write(f"已检测到 {len(df)} 条样本数据。")
    
    if '内容' not in df.columns:
        st.error("表格中未找到 '内容' 列，请检查表头。")
    else:
        if st.button("开始批量自动化编码"):
            progress_bar = st.progress(0)
            all_results = []
            
            for i, row in df.iterrows():
                # 1. 自动打分
                scores = ai_analyze_batch(row['内容'])
                # 2. 计算综合预测分
                final_score = sum(scores[k] * weights[k] for k in scores)
                # 3. 整合结果
                res = {"综合得分": round(final_score, 2)}
                res.update(scores)
                all_results.append(res)
                progress_bar.progress((i + 1) / len(df))
            
            # 合并回原表
            results_df = pd.concat([df, pd.DataFrame(all_results)], axis=1)
            
            st.success("批量分析完成！")
            st.dataframe(results_df.head(10)) # 预览前10行
            
            # --- 下载按钮 ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                results_df.to_excel(writer, index=False, sheet_name='VCTSM分析结果')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 下载带分数的分析报告",
                data=processed_data,
                file_name="VCTSM_Research_Result.xlsx",
                mime="application/vnd.ms-excel"
            )
            
            # --- 统计视图 ---
            st.subheader("📊 样本分布洞察")
            fig, ax = plt.subplots()
            results_df['综合得分'].hist(bins=20, ax=ax, color='skyblue', edgecolor='white')
            ax.set_title("样本预测得分分布直方图")
            st.pyplot(fig)
