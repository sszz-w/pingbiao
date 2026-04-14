"""HTML 报告生成服务"""
from datetime import datetime
from models.schemas import Clause


def generate_report(
    clauses: list[Clause],
    bids: dict[str, dict],
    results: list[dict],
) -> str:
    """
    生成 HTML 评标报告

    Args:
        clauses: 评审条款列表
        bids: {bid_id: {"chunks": [...], "file_name": "xxx.pdf"}}
        results: [{"clause_no", "bid_name", "score", "reason"}, ...]

    Returns:
        HTML 字符串
    """
    # 构建结果查找表: (bid_name, clause_no) -> {score, reason}
    result_map = {}
    for r in results:
        key = (r["bid_name"], r["clause_no"])
        result_map[key] = r

    # 收集所有投标文件名
    bid_names = [data["file_name"] for data in bids.values()]

    # 构建表格行
    rows_html = ""
    bid_totals = {name: 0.0 for name in bid_names}

    for clause in clauses:
        for bid_name in bid_names:
            key = (bid_name, clause.no)
            r = result_map.get(key, {})
            score = r.get("score", 0)
            reason = r.get("reason", "—")
            bid_totals[bid_name] += score
            rows_html += f"""
        <tr>
            <td>{bid_name}</td>
            <td>{clause.no}</td>
            <td>{clause.desc}</td>
            <td style="text-align:center">{clause.score}</td>
            <td style="text-align:center; font-weight:bold">{score}</td>
            <td>{reason}</td>
        </tr>"""

    # 汇总行
    summary_rows = ""
    for bid_name in bid_names:
        total = round(bid_totals[bid_name], 1)
        summary_rows += f"""
        <tr style="background:#f0f0f0; font-weight:bold">
            <td>{bid_name}</td>
            <td colspan="3">总分</td>
            <td style="text-align:center; font-size:1.2em; color:#1a56db">{total}</td>
            <td>—</td>
        </tr>"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>评标报告</title>
    <style>
        body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 40px; color: #333; }}
        h1 {{ text-align: center; color: #1a56db; }}
        .meta {{ text-align: center; color: #666; margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background: #1a56db; color: white; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .footer {{ text-align: center; color: #999; margin-top: 32px; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>评标报告</h1>
    <p class="meta">投标文件数：{len(bid_names)} | 评审条款数：{len(clauses)} | 生成时间：{timestamp}</p>

    <table>
        <thead>
            <tr>
                <th>投标文件</th>
                <th>条款编号</th>
                <th>条款描述</th>
                <th>满分</th>
                <th>得分</th>
                <th>评审理由</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
            {summary_rows}
        </tbody>
    </table>

    <p class="footer">本报告由 Pingbiao-Power 智能评标系统自动生成</p>
</body>
</html>"""

    return html
