from pathlib import Path


def _acceptance_rows():
    for line in Path("docs/acceptance-matrix.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cols = [col.strip() for col in line.strip("|").split("|")]
        if len(cols) >= 8 and cols[0] and cols[0][0].isdigit():
            yield cols


def test_acceptance_matrix_quality_debt_summary_matches_gap_rows():
    text = Path("docs/acceptance-matrix.md").read_text(encoding="utf-8")
    gap_count = sum(1 for cols in _acceptance_rows() if cols[-1] not in {"—", "-", ""})

    summary_line = next(
        line for line in text.splitlines()
        if line.startswith("| **合计**")
    )

    assert f"| **{gap_count}** |" in summary_line


def test_acceptance_matrix_summary_counts_match_domain_rows():
    text = Path("docs/acceptance-matrix.md").read_text(encoding="utf-8")
    domain_labels = {
        "## 1.": "数据管道",
        "## 2.": "信号系统",
        "## 3.": "回测引擎",
        "## 4.": "执行层",
        "## 5.": "Web 平台",
        "## 6.": "多资产架构",
    }
    current_domain = ""
    row_counts = {label: 0 for label in domain_labels.values()}
    summary_counts: dict[str, int] = {}

    for line in text.splitlines():
        if line.startswith("## "):
            current_domain = next(
                (label for prefix, label in domain_labels.items() if line.startswith(prefix)),
                "",
            )
        if current_domain and line.startswith("|") and not line.startswith("|---"):
            cols = [col.strip() for col in line.strip("|").split("|")]
            if cols and cols[0].startswith(tuple(str(i) for i in range(1, 7))):
                row_counts[current_domain] += 1
        if line.startswith("|") and not line.startswith("|---"):
            cols = [col.strip().strip("*") for col in line.strip("|").split("|")]
            if len(cols) >= 2 and cols[0] in row_counts:
                summary_counts[cols[0]] = int(cols[1])
            elif len(cols) >= 2 and cols[0] == "合计":
                summary_counts["合计"] = int(cols[1])

    assert summary_counts == {**row_counts, "合计": sum(row_counts.values())}
