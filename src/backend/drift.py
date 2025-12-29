
mock_drift_detections = [
    {
    "id": "drift-ec2-1",
    "resource": "web-server-1",
    "resourceType": "EC2",
    "driftType": "Configuration",
    "severity": "High",
    "actualValue": "InstanceType: t3.large",
    "expectedValue": "InstanceType: t3.micro",
    "lastSync": "2024-01-14T08:45:00Z"
},



]


def get_drift_data():
    """Return all drift detection data"""
    return {
        "drifts": mock_drift_detections
    }

import os
from github import Github

SCRIPT_PATH = "./scripts/aws_config.py"

def apply_ec2_drift_fix():
    """
    Reads the IaC script, replaces t3.small → t3.micro,
    and returns the updated file content.
    """
    if not os.path.exists(SCRIPT_PATH):
        raise FileNotFoundError(f"Script file not found: {SCRIPT_PATH}")

    with open(SCRIPT_PATH, "r") as f:
        content = f.read()

    if "t3.small" not in content:
        return None  # Nothing to fix

    updated_content = content.replace("t3.small", "t3.micro")
    return updated_content

def create_github_pr(updated_content):
    """
   
    """
    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")

    if not token or not repo_name:
        raise ValueError("GITHUB_TOKEN and GITHUB_REPO must be set")

    g = Github(token)
    repo = g.get_repo(repo_name)

    # 1. Create branch name
    branch_name = "fix-drift-ec2-" + os.urandom(4).hex()
    base_branch = "main"

    # 2. Create new branch
    main_ref = repo.get_git_ref(f"heads/{base_branch}")
    repo.create_git_ref(
        ref=f"refs/heads/{branch_name}",
        sha=main_ref.object.sha
    )

    # 3. Update the file in new branch
    file = repo.get_contents(SCRIPT_PATH, ref=base_branch)

    repo.update_file(
        path=SCRIPT_PATH,
        message="AutoFix: Update EC2 instance type from t3.small to t3.micro",
        content=updated_content,
        sha=file.sha,
        branch=branch_name
    )

    # 4. Create PR
    pr = repo.create_pull(
        title="AutoFix Drift: EC2 Instance Type Correction",
        body=(
            "This automated PR corrects the drift detected:\n\n"
            "**Actual:** t3.small\n"
            "**Expected:** t3.micro\n\n"
            "Updated `aws_setup.py` accordingly."
        ),
        head=branch_name,
        base=base_branch
    )

    return {
        "pr_url": pr.html_url,
        "branch": branch_name
    }
