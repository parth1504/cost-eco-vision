#!/bin/bash
set -e

# Generate Terraform from existing AWS resources
# Uses terraformer: https://github.com/GoogleCloudPlatform/terraformer

REGION="${AWS_REGION:-us-east-1}"
OUTPUT_DIR="./terraform-generated"

echo "🔧 Generating Terraform for AWS resources in $REGION..."

# Install terraformer if not present
if ! command -v terraformer &> /dev/null; then
    echo "📦 Installing terraformer..."
    
    # Detect OS
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    
    if [ "$ARCH" = "x86_64" ]; then
        ARCH="amd64"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        ARCH="arm64"
    fi
    
    # Download latest release
    LATEST_URL="https://github.com/GoogleCloudPlatform/terraformer/releases/latest/download/terraformer-aws-${OS}-${ARCH}"
    
    curl -LO "$LATEST_URL"
    chmod +x "terraformer-aws-${OS}-${ARCH}"
    sudo mv "terraformer-aws-${OS}-${ARCH}" /usr/local/bin/terraformer
    
    echo "✅ Terraformer installed"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

# Initialize Terraform (required by terraformer)
if [ ! -f "versions.tf" ]; then
cat > versions.tf <<EOF
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "$REGION"
}
EOF
fi

terraform init

# Import resources
# Starting with the ones you care about: EC2, S3, RDS, Security Groups
echo "📥 Importing EC2 instances..."
terraformer import aws --resources=ec2_instance --regions=$REGION --profile="" || echo "⚠️  EC2 import had issues (may be empty)"

echo "📥 Importing Security Groups..."
terraformer import aws --resources=sg --regions=$REGION --profile="" || echo "⚠️  SG import had issues"

echo "📥 Importing S3 buckets..."
terraformer import aws --resources=s3 --regions=$REGION --profile="" || echo "⚠️  S3 import had issues"

echo "📥 Importing RDS instances..."
terraformer import aws --resources=rds --regions=$REGION --profile="" || echo "⚠️  RDS import had issues"

# Clean up generated files (terraformer creates a messy structure)
echo "🧹 Organizing generated files..."

# Move all .tf files to root
find . -name "*.tf" -not -path "./versions.tf" -exec mv {} . \; 2>/dev/null || true

# Remove empty directories
find . -type d -empty -delete 2>/dev/null || true

echo "✅ Terraform generation complete!"
echo "📁 Files created in: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "1. Review the generated .tf files"
echo "2. Run 'terraform plan' to verify"
echo "3. Commit to Git as your baseline"
echo "4. Run drift detection against this state"