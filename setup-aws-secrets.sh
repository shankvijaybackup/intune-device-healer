#!/bin/bash
set -e

###############################################################################
# AWS Systems Manager Parameter Store Setup
# Stores secrets securely for Lambda deployment
###############################################################################

echo "🔐 AWS Systems Manager Parameter Store Setup"
echo "=============================================="
echo ""

# Get stage (prod or dev)
STAGE=${1:-prod}
echo "📌 Stage: $STAGE"

# Get region
REGION=${2:-us-east-1}
echo "🌍 Region: $REGION"
echo ""

# Verify AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not installed. Install with:"
    echo "   brew install awscli"
    exit 1
fi

# Verify credentials
echo "🔐 Verifying AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Run:"
    echo "   aws configure"
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "✅ AWS Account: $AWS_ACCOUNT"
echo ""

# Function to create/update parameter
create_parameter() {
    local NAME=$1
    local VALUE=$2
    local TYPE=${3:-String}
    local DESCRIPTION=$4

    echo "📝 Setting parameter: $NAME"

    aws ssm put-parameter \
        --name "$NAME" \
        --value "$VALUE" \
        --type "$TYPE" \
        --description "$DESCRIPTION" \
        --region "$REGION" \
        --overwrite \
        &> /dev/null

    if [ $? -eq 0 ]; then
        echo "   ✅ Success"
    else
        echo "   ❌ Failed"
    fi
}

echo "🔑 Azure Credentials"
echo "-------------------"

# Azure Tenant ID
read -p "Enter Azure Tenant ID: " AZURE_TENANT_ID
create_parameter \
    "/intune-healer/$STAGE/azure-tenant-id" \
    "$AZURE_TENANT_ID" \
    "String" \
    "Azure AD Tenant ID for Intune Device Healer"

# Azure Client ID
read -p "Enter Azure Client ID: " AZURE_CLIENT_ID
create_parameter \
    "/intune-healer/$STAGE/azure-client-id" \
    "$AZURE_CLIENT_ID" \
    "String" \
    "Azure AD Application (Client) ID"

# Azure Client Secret (SecureString for encryption at rest)
read -sp "Enter Azure Client Secret: " AZURE_CLIENT_SECRET
echo ""
create_parameter \
    "/intune-healer/$STAGE/azure-client-secret" \
    "$AZURE_CLIENT_SECRET" \
    "SecureString" \
    "Azure AD Application Client Secret (encrypted)"

echo ""
echo "🔗 Atomicwork Configuration"
echo "---------------------------"

# Atomicwork API URL
read -p "Enter Atomicwork API URL (or press Enter to skip): " ATOMICWORK_API_URL
if [ -n "$ATOMICWORK_API_URL" ]; then
    create_parameter \
        "/intune-healer/$STAGE/atomicwork-api-url" \
        "$ATOMICWORK_API_URL" \
        "String" \
        "Atomicwork API base URL"
else
    echo "⏭️  Skipped Atomicwork API URL"
fi

# Atomicwork API Key (optional)
read -sp "Enter Atomicwork API Key (or press Enter to skip): " ATOMICWORK_API_KEY
echo ""
if [ -n "$ATOMICWORK_API_KEY" ]; then
    create_parameter \
        "/intune-healer/$STAGE/atomicwork-api-key" \
        "$ATOMICWORK_API_KEY" \
        "SecureString" \
        "Atomicwork API Key (encrypted)"
else
    echo "⏭️  Skipped Atomicwork API Key"
fi

echo ""
echo "✅ All secrets configured successfully!"
echo ""
echo "📋 Stored Parameters:"
echo "   /intune-healer/$STAGE/azure-tenant-id"
echo "   /intune-healer/$STAGE/azure-client-id"
echo "   /intune-healer/$STAGE/azure-client-secret (SecureString)"

if [ -n "$ATOMICWORK_API_URL" ]; then
    echo "   /intune-healer/$STAGE/atomicwork-api-url"
fi

if [ -n "$ATOMICWORK_API_KEY" ]; then
    echo "   /intune-healer/$STAGE/atomicwork-api-key (SecureString)"
fi

echo ""
echo "🔒 Security Notes:"
echo "   - Secrets are encrypted at rest using AWS KMS"
echo "   - SecureString parameters are encrypted"
echo "   - Lambda has IAM permissions to read these"
echo ""

echo "🚀 Next Steps:"
echo "   1. Review your parameters in AWS Console:"
echo "      https://console.aws.amazon.com/systems-manager/parameters"
echo ""
echo "   2. Deploy to Lambda:"
echo "      ./deploy-aws.sh $STAGE $REGION"
echo ""

# Save configuration summary
cat > ".aws-deployment-config.txt" <<EOF
AWS Deployment Configuration
============================
Stage: $STAGE
Region: $REGION
AWS Account: $AWS_ACCOUNT
Date: $(date)

Parameters Configured:
- /intune-healer/$STAGE/azure-tenant-id
- /intune-healer/$STAGE/azure-client-id
- /intune-healer/$STAGE/azure-client-secret
- /intune-healer/$STAGE/atomicwork-api-url
- /intune-healer/$STAGE/atomicwork-api-key

Next: Run ./deploy-aws.sh $STAGE $REGION
EOF

echo "💾 Configuration saved to: .aws-deployment-config.txt"
