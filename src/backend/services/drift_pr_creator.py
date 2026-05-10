"""
Drift Remediation via GitHub PR
--------------------------------
Generates PRs to fix drift in either direction:
1. Update Terraform to match AWS (AWS is truth)
2. Update AWS to match Terraform (Terraform is truth)
"""

import os
import json
from github import Github
from typing import Literal

# ---------------------------------------------------------------------------
# Terraform file updater
# ---------------------------------------------------------------------------

def update_terraform_file(
    resource_type: str,
    resource_id: str,
    field: str,
    new_value: str,
    tf_dir: str = "./terraform-generated",
) -> tuple[str, str]:
    """
    Update a Terraform .tf file to match AWS actual value.
    Returns (file_path, updated_content).
    """
    
    # Find the resource by reading terraform.tfstate
    state_file = os.path.join(tf_dir, "terraform.tfstate")
    if not os.path.exists(state_file):
        raise FileNotFoundError(f"terraform.tfstate not found at {state_file}")
    
    with open(state_file) as f:
        state = json.load(f)
    
    # Find the resource in state
    resource_mapping = {
        "ec2": "aws_instance",
        "sg": "aws_security_group",
        "rds": "aws_db_instance",
        "s3": "aws_s3_bucket",
    }
    
    tf_resource_type = resource_mapping.get(resource_type.lower(), "")
    if not tf_resource_type:
        raise ValueError(f"Unsupported resource type: {resource_type}")
    
    # Find resource name from state
    resource_name = None
    for res in state.get("resources", []):
        if res.get("type") == tf_resource_type:
            for inst in res.get("instances", []):
                attrs = inst.get("attributes", {})
                if attrs.get("id") == resource_id:
                    resource_name = res.get("name")
                    break
        if resource_name:
            break
    
    if not resource_name:
        raise FileNotFoundError(
            f"Resource {resource_id} not found in terraform.tfstate"
        )
    
    # Now find the .tf file containing this resource
    target_file = None
    for root, dirs, files in os.walk(tf_dir):
        for file in files:
            if not file.endswith(".tf"):
                continue
            
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            # Look for the resource block
            if f'resource "{tf_resource_type}" "{resource_name}"' in content:
                target_file = filepath
                break
        if target_file:
            break
    
    if not target_file:
        raise FileNotFoundError(
            f"Could not find .tf file for {tf_resource_type}.{resource_name}"
        )
    
    with open(target_file, "r") as f:
        original_content = f.read()
    
    # Update the field
    updated_content = _update_tf_field(original_content, field, new_value)
    
    return target_file, updated_content


def _update_tf_field(content: str, field: str, new_value: str) -> str:
    """
    Simple field updater for demo purposes.
    In production, parse HCL properly.
    """
    # Example: instance_type = "t3.micro" → instance_type = "t3.large"
    import re
    
    # Handle different value types
    if isinstance(new_value, bool):
        value_str = "true" if new_value else "false"
    elif isinstance(new_value, list):
        value_str = json.dumps(new_value)
    else:
        value_str = f'"{new_value}"'
    
    # Find and replace the field
    pattern = rf'{field}\s*=\s*[^\n]+'
    replacement = f'{field} = {value_str}'
    
    updated = re.sub(pattern, replacement, content)
    return updated


# ---------------------------------------------------------------------------
# PR generation
# ---------------------------------------------------------------------------

def create_drift_fix_pr(
    drift: dict,
    fix_direction: Literal["terraform_to_aws", "aws_to_terraform"],
    github_token: str = None,
    github_repo: str = None,
    tf_dir: str = "./terraform-generated",
) -> dict:
    """
    Create a GitHub PR to fix the drift.
    
    Args:
        drift: Drift object with resource_id, field, terraform_value, aws_value, etc.
        fix_direction: 
            - "terraform_to_aws": Update Terraform to match AWS (AWS is truth)
            - "aws_to_terraform": Add script to run terraform apply (Terraform is truth)
        github_token: GitHub personal access token
        github_repo: Repo in format "owner/repo"
        tf_dir: Path to Terraform files
    """
    token = github_token or os.getenv("GITHUB_TOKEN")
    repo_name = github_repo or os.getenv("GITHUB_REPO")
    
    if not token or not repo_name:
        raise ValueError("GITHUB_TOKEN and GITHUB_REPO must be set")
    
    g = Github(token)
    repo = g.get_repo(repo_name)
    
    base_branch = "main"
    branch_name = f"drift-fix-{drift['resource_id']}-{drift['field']}-{os.urandom(4).hex()}"
    
    # Create branch
    main_ref = repo.get_git_ref(f"heads/{base_branch}")
    repo.create_git_ref(
        ref=f"refs/heads/{branch_name}",
        sha=main_ref.object.sha
    )
    
    if fix_direction == "aws_to_terraform":
        # Update Terraform file to match AWS
        file_path, updated_content = update_terraform_file(
            resource_type=drift["resource_type"],
            resource_id=drift["resource_id"],
            field=drift["field"],
            new_value=drift["aws_value"],
            tf_dir=tf_dir,
        )
        
        # Get relative path for GitHub
        rel_path = "instance.tf"


        
        
        # Get current file SHA
        print(f"DEBUG: Trying to fetch file: {rel_path} from branch: {base_branch}")
        
        file_obj = repo.get_contents(rel_path, ref=base_branch)
        
        # Update file
        commit_msg = (
            f"Fix drift: Update {drift['field']} for {drift['resource_id']}\n\n"
            f"Terraform value: {drift['terraform_value']}\n"
            f"AWS actual value: {drift['aws_value']}\n"
            f"Resolution: Update Terraform to match AWS"
        )
        
        repo.update_file(
            path=rel_path,
            message=commit_msg,
            content=updated_content,
            sha=file_obj.sha,
            branch=branch_name,
        )
        
        pr_title = f"[Drift Fix] Update Terraform: {drift['resource_id']} {drift['field']}"
        pr_body = f"""
## Drift Detected

**Resource:** `{drift['resource_id']}`  
**Field:** `{drift['field']}`  
**Severity:** {drift['severity']}

### Difference
- **Terraform (expected):** `{drift['terraform_value']}`
- **AWS (actual):** `{drift['aws_value']}`

### Resolution
This PR updates the Terraform configuration to match the actual AWS state.

**Next steps:**
1. Review the change
2. Merge this PR
3. Run `terraform plan` to verify no changes needed
"""
    
    else:  # terraform_to_aws
        # Create a remediation script
        script_content = f"""#!/bin/bash
# Auto-generated drift remediation script
# This will force AWS to match Terraform state

set -e

echo "Applying Terraform to fix drift in {drift['resource_id']}..."
terraform apply -auto-approve -target={drift['resource_type'].lower()}.{drift['resource_id']}

echo "✅ Drift fixed: {drift['field']} restored to {drift['terraform_value']}"
"""
        
        script_path = f"scripts/fix_drift_{drift['resource_id']}_{drift['field']}.sh"
        
        commit_msg = (
            f"Fix drift: Apply Terraform for {drift['resource_id']}\n\n"
            f"AWS value: {drift['aws_value']}\n"
            f"Terraform value: {drift['terraform_value']}\n"
            f"Resolution: Run terraform apply to force AWS to match Terraform"
        )
        
        repo.create_file(
            path=script_path,
            message=commit_msg,
            content=script_content,
            branch=branch_name,
        )
        
        pr_title = f"[Drift Fix] Apply Terraform: {drift['resource_id']} {drift['field']}"
        pr_body = f"""
## Drift Detected

**Resource:** `{drift['resource_id']}`  
**Field:** `{drift['field']}`  
**Severity:** {drift['severity']}

### Difference
- **Terraform (expected):** `{drift['terraform_value']}`
- **AWS (actual):** `{drift['aws_value']}`

### Resolution
This PR adds a script to run `terraform apply` and force AWS to match Terraform.

**Next steps:**
1. Review the change
2. Merge this PR
3. Run the script: `bash {script_path}`
4. Verify drift is resolved
"""
    
    # Create PR
    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=branch_name,
        base=base_branch,
    )
    
    return {
        "pr_url": pr.html_url,
        "pr_number": pr.number,
        "branch": branch_name,
        "fix_direction": fix_direction,
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example drift
    test_drift = {
        "resource_id": "i-0abc123def",
        "resource_type": "EC2",
        "field": "instance_type",
        "terraform_value": "t3.micro",
        "aws_value": "t3.large",
        "severity": "High",
    }
    
    # Uncomment to test:
    # result = create_drift_fix_pr(test_drift, "aws_to_terraform")
    # print(json.dumps(result, indent=2))