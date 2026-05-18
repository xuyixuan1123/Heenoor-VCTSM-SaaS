#!/bin/bash
# VCTSM Streamlit 本地启动脚本
cd "$(dirname "$0")"
echo "🚀 启动 VCTSM 爆款内容打分工具..."
streamlit run app.py --server.port 8501
