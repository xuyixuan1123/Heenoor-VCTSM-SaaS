#!/usr/bin/env python3
"""
VCTSM 统计验证工具
输入：批量打分结果 CSV（含「是否爆款」列）
输出：Cohen's d 效应量、分类准确率、维度相关性分析
"""
import sys, csv, json
import numpy as np
from pathlib import Path
from collections import defaultdict

DIMS = ['情绪密度', '痛点强度', '标题钩子', '社交货币', '论证深度', '情境代入感']

def load_results(csv_path: str) -> dict:
    data = {d: [] for d in DIMS}
    data['viral'] = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                label = row.get('是否爆款', '')
                if label in ('是', '1', 'True', 'true'):
                    data['viral'].append(1)
                elif label in ('否', '0', 'False', 'false'):
                    data['viral'].append(0)
                else:
                    continue
                for d in DIMS:
                    data[d].append(float(row[d]))
            except (ValueError, KeyError):
                continue
    return data

def cohens_d(group1, group2):
    m1, m2 = np.mean(group1), np.mean(group2)
    v1, v2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled = np.sqrt((v1 + v2) / 2)
    return (m1 - m2) / pooled if pooled > 0 else 0

def main():
    if len(sys.argv) < 2:
        print("用法: python3 analyze.py <批量结果.csv>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    if not Path(csv_path).exists():
        print(f"文件不存在: {csv_path}")
        sys.exit(1)
    
    data = load_results(csv_path)
    viral_idx = [i for i, v in enumerate(data['viral']) if v == 1]
    nonviral_idx = [i for i, v in enumerate(data['viral']) if v == 0]
    n_v, n_nv = len(viral_idx), len(nonviral_idx)
    
    print(f"\n样本：{len(data['viral'])} 篇（爆款 {n_v} / 非爆款 {n_nv}）")
    print("=" * 60)
    
    # Cohen's d
    print("\n【Cohen's d 效应量】\n")
    d_vals = {}
    for d in DIMS:
        v = np.array([data[d][i] for i in viral_idx])
        nv = np.array([data[d][i] for i in nonviral_idx])
        cd = cohens_d(v, nv)
        d_vals[d] = cd
        print(f"  {d:　<6}: d = {cd:6.2f}")
    
    # Classification
    print("\n【阈值分类准确率】\n")
    total_scores = []
    for i in range(len(data['viral'])):
        row = {d: data[d][i] for d in DIMS}
        # weighted score
        w = {'痛点强度': 25, '情绪密度': 16, '标题钩子': 16, '社交货币': 15, '论证深度': 12, '情境代入感': 16}
        total = sum(row[d] / 5 * w[d] for d in DIMS)
        total_scores.append(total)
    
    best_acc = 0
    best_thresh = 0
    for t in np.arange(40, 90, 0.5):
        correct = sum(1 for i in range(len(data['viral'])) 
                      if (total_scores[i] >= t) == (data['viral'][i] == 1))
        acc = correct / len(data['viral'])
        if acc > best_acc:
            best_acc, best_thresh = acc, t
    
    print(f"  最佳阈值: {best_thresh:.1f}")
    print(f"  分类准确率: {best_acc*100:.1f}%")
    
    # Correlation
    print("\n【维度间相关性】\n")
    for i, d1 in enumerate(DIMS):
        for j, d2 in enumerate(DIMS):
            if i < j:
                r = np.corrcoef(data[d1], data[d2])[0, 1]
                flag = " ⚠️ 高相关" if abs(r) > 0.7 else ""
                print(f"  {d1} × {d2}: r = {r:.3f}{flag}")
    
    print(f"\n分析完成。")

if __name__ == '__main__':
    main()
