from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_required_open_source_governance_files_exist():
    required = [
        "README.md",
        "README.en.md",
        "LICENSE",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "SUPPORT.md",
        "GOVERNANCE.md",
        "MAINTAINERS.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "NOTICE",
        "docs/RELEASE.md",
        "docs/open-source/onboarding-without-secrets.md",
        "docs/open-source/data-compliance.md",
        "docs/open-source/privacy.md",
        "docs/open-source/security-and-sbom.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        ".github/workflows/release.yml",
    ]

    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []


def test_issue_templates_and_workflows_are_valid_yaml():
    yaml_files = [
        *sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")),
        ROOT / ".github" / "dependabot.yml",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "security.yml",
        ROOT / ".github" / "workflows" / "release.yml",
        ROOT / "CITATION.cff",
    ]

    for path in yaml_files:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None, path


def test_local_metadata_files_are_not_tracked():
    import subprocess

    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    forbidden_suffixes = ("/.DS_Store",)
    forbidden_exact = {".DS_Store", ".pytest_cache/README.md"}

    offenders = [
        path
        for path in tracked
        if path in forbidden_exact or path.endswith(forbidden_suffixes)
    ]
    assert offenders == []
