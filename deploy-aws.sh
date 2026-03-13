#!/bin/bash
set -e

###############################################################################
# AWS Lambda Deployment Script for Intune Device Healer
###############################################################################

echo "🚀 Intune Device Healer - AWS Lambda Deployment"
echo "================================================"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first:"
    echo "   brew install awscli"
    exit 1
fi

# Check if Serverless Framework is installed
if ! command -v serverless &> /dev/null; then
    echo "❌ Serverless Framework is not installed. Please install it first:"
    echo "   npm install -g serverless"
    exit 1
fi

# Check if required plugins are installed
echo "📦 Checking Serverless plugins..."
serverless plugin install -n serverless-python-requirements 2>/dev/null || echo "✅ serverless-python-requirements already installed"
serverless plugin install -n serverless-prune-plugin 2>/dev/null || echo "✅ serverless-prune-plugin already installed"

# Get deployment stage (prod or dev)
STAGE=${1:-prod}
echo "🎯 Deployment Stage: $STAGE"
echo ""

# Get AWS region
REGION=${2:-us-east-1}
echo "🌍 AWS Region: $REGION"
echo ""

# Verify AWS credentials
echo "🔐 Verifying AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run:"
    echo "   aws configure"
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "✅ AWS Account: $AWS_ACCOUNT"
echo ""

# Check if secrets are stored in AWS Systems Manager Parameter Store
echo "🔑 Checking AWS Systems Manager Parameter Store..."
MISSING_PARAMS=0

check_parameter() {
    local PARAM_NAME=$1
    if aws ssm get-parameter --name "$PARAM_NAME" --region "$REGION" &> /dev/null; then
        echo "✅ $PARAM_NAME exists"
    else
        echo "❌ $PARAM_NAME NOT FOUND"
        MISSING_PARAMS=1
    fi
}

check_parameter "/intune-healer/$STAGE/azure-tenant-id"
check_parameter "/intune-healer/$STAGE/azure-client-id"
check_parameter "/intune-healer/$STAGE/azure-client-secret"
check_parameter "/intune-healer/$STAGE/atomicwork-api-url"

if [ $MISSING_PARAMS -eq 1 ]; then
    echo ""
    echo "⚠️  Missing parameters detected!"
    echo "Please run the setup script first:"
    echo "   ./setup-aws-secrets.sh $STAGE $REGION"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "📋 Deployment Configuration:"
echo "   Stage: $STAGE"
echo "   Region: $REGION"
echo "   AWS Account: $AWS_ACCOUNT"
echo ""

read -p "Ready to deploy? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

echo ""
echo "🚀 Deploying to AWS Lambda..."
echo ""

# Copy Lambda requirements
cp requirements-lambda.txt requirements.txt

# Deploy using Serverless Framework
serverless deploy --stage "$STAGE" --region "$REGION" --verbose

# Restore original requirements.txt
git checkout requirements.txt 2>/dev/null || true

echo ""
echo "✅ Deployment Complete!"
echo ""

# Get API endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "intune-device-healer-$STAGE" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ServiceEndpoint`].OutputValue' \
    --output text)

if [ -n "$API_ENDPOINT" ]; then
    echo "🌐 API Endpoint:"
    echo "   $API_ENDPOINT"
    echo ""
    echo "📍 Webhook URL for Atomicwork:"
    echo "   $API_ENDPOINT/webhook/ticket"
    echo ""
    echo "🏥 Health Check:"
    echo "   curl $API_ENDPOINT/health"
    echo ""
fi

echo "📊 View logs:"
echo "   serverless logs -f api -t --stage $STAGE --region $REGION"
echo ""

echo "🎉 Deployment successful! Your API is now live."
