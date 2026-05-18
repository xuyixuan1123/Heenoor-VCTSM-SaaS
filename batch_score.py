#!/usr/bin/env python3
"""
批量打分工具 — 读取 CSV，调用 API 逐篇打分，输出带分数的 CSV
"""
import csv, sys, time, os
from pathlib import Path
from viral_scorer import score_article

def main():
    if len(sys.argv) < 3:
        print("用法: python3 batch_score.py <输入.csv> <API_KEY> [deepseek|doubao] [endpoint_id]")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    api_key = sys.argv[2]
    provider = sys.argv[3] if len(sys.argv) > 3 else "deepseek"
    endpoint_id = sys.argv[4] if len(sys.argv) > 4 else None
    
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
    
    out_fields = list(fieldnames) + ['情绪密度', '痛点强度', '标题钩子', '社交货币', '论证深度', '情境代入感']
    out_path = csv_path.replace('.csv', '_scored.csv')
    
    n = len(rows)
    print(f"共 {n} 篇，开始打分...")
    
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        
        for i, row in enumerate(rows):
            title = row.get('标题', '')
            body = row.get('正文', row.get('内容', ''))
            if not body.strip():
                continue
            
            print(f"[{i+1}/{n}] {title[:30]}...", end=' ')
            try:
                scores = score_article(title, body, api_key, provider, endpoint_id)
                row.update(scores)
                writer.writerow(row)
                print(f"✓")
            except Exception as e:
                print(f"✗ {e}")
            
            time.sleep(1.0)  # rate limit
    
    print(f"\n完成！结果: {out_path}")

if __name__ == '__main__':
    main()
