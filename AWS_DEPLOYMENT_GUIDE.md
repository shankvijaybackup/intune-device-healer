# 🚀 AWS Lambda Deployment Guide

Complete guide to deploy Intune Device Healer to AWS Lambda.

---

## 📋 **Prerequisites**

### 1. **AWS Account**
- Active AWS account with billing enabled
- IAM user with Administrator access (or specific permissions)

### 2. **Install Required Tools**

```bash
# AWS CLI
brew install awscli

# Configure AWS credentials
aws configure
# Enter:
#   AWS Access Key ID: [your-key]
#   AWS Secret Access Key: [your-secret]
#   Default region: us-east-1
#   Default output format: json

# Serverless Framework
npm install -g serverless

# Verify installations
aws --version          # Should be 2.x or higher
serverless --version   # Should be 3.x or higher
node --version         # Should be 18.x or higher
```

### 3. **Verify AWS Credentials**

```bash
aws sts get-caller-identity
```

Should output your AWS account details.

---

## 🔧 **Step 1: Setup AWS Secrets**

Store your Azure credentials securely in AWS Systems Manager Parameter Store:

```bash
cd ~/intune-device-healer
./setup-aws-secrets.sh prod us-east-1
```

**You'll be prompted for:**
1. Azure Tenant ID: `6adf129d-28f9-498f-871f-ac0bdcdff25f`
2. Azure Client ID: `267c8a9f-0e9a-43d2-ae9e-d225d93d4bdd`
3. Azure Client Secret: `ral8Q~wVxgExYDF9iPxsziEUWx65GppKew5-ybCa`
4. Atomicwork API URL: (optional, for future integration)
5. Atomicwork API Key: (optional, for future integration)

**Security Notes:**
- ✅ Secrets are encrypted at rest using AWS KMS
- ✅ SecureString parameters use additional encryption
- ✅ Lambda has IAM permissions to read only these specific parameters
- ✅ No secrets stored in code or environment variables

---

## 🚀 **Step 2: Deploy to AWS Lambda**

Deploy the entire stack:

```bash
cd ~/intune-device-healer
./deploy-aws.sh prod us-east-1
```

**What happens:**
1. ✅ Verifies AWS credentials
2. ✅ Checks secrets in Parameter Store
3. ✅ Installs Serverless plugins
4. ✅ Packages Python dependencies
5. ✅ Creates Lambda function
6. ✅ Creates API Gateway
7. ✅ Configures IAM roles
8. ✅ Sets up CloudWatch logging

**Deployment time:** ~3-5 minutes

---

## 🎯 **Step 3: Test Your Deployment**

### **A) Test Health Endpoint**

```bash
# Get your API endpoint from deployment output
API_URL="https://xxxxx.execute-api.us-east-1.amazonaws.com/prod"

# Test health check
curl $API_URL/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "intune_connection": "ok",
  "timestamp": "2026-02-16T10:30:00Z"
}
```

### **B) Test Device Listing**

```bash
curl -X POST $API_URL/execute-remediation \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "74576fb0-726d-415a-a97d-0bebe5ad8b42",
    "actions": ["diagnose_device_comprehensive"],
    "platform": "Windows"
  }'
```

### **C) Test Webhook (Atomicwork Integration)**

```bash
curl -X POST $API_URL/webhook/ticket \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "ticket_created",
    "ticket": {
      "ticket_id": "TEST-12345",
      "subject": "VPN not connecting",
      "description": "User cannot connect to VPN",
      "priority": "high",
      "requester_email": "test@atombank.co",
      "asset": {
        "asset_id": "ASSET-001",
        "intune_device_id": "74576fb0-726d-415a-a97d-0bebe5ad8b42",
        "user_email": "vijay@atombank.co"
      }
    }
  }'
```

**Expected response:**
```json
{
  "status": "accepted",
  "ticket_id": "TEST-12345",
  "analysis": {
    "issue_type": "vpn",
    "confidence": 0.8,
    "recommended_actions": ["check_network_health", "fix_vpn_configuration"],
    "priority": "high"
  },
  "message": "Ticket received and queued for remediation"
}
```

---

## 📊 **Monitoring & Logs**

### **View Real-time Logs**

```bash
# Follow logs in real-time
serverless logs -f api -t --stage prod --region us-east-1

# View last 100 lines
serverless logs -f api --stage prod --region us-east-1
```

### **CloudWatch Dashboard**

1. Go to AWS Console → CloudWatch
2. Navigate to Log Groups
3. Find: `/aws/lambda/intune-device-healer-prod-api`
4. View logs, create metrics, set alarms

### **API Gateway Metrics**

1. Go to AWS Console → API Gateway
2. Find: `intune-device-healer-prod`
3. View metrics: requests, latency, errors

---

## 💰 **Cost Estimation**

### **AWS Lambda Pricing (us-east-1)**

**Free Tier (First 12 months):**
- 1 million requests/month FREE
- 400,000 GB-seconds compute FREE

**After Free Tier:**
- $0.20 per 1 million requests
- $0.0000166667 per GB-second

**Example Monthly Costs:**

| Usage Scenario | Requests/Month | Execution Time | Monthly Cost |
|----------------|----------------|----------------|--------------|
| Light (Testing) | 10,000 | 500ms | **$0.05** |
| Medium (Production) | 100,000 | 1s | **$2.50** |
| Heavy (Enterprise) | 1,000,000 | 2s | **$25.00** |

**Additional Costs:**
- API Gateway: ~$3.50 per million requests
- CloudWatch Logs: ~$0.50 per GB ingested
- Parameter Store: FREE (< 10,000 parameters)

**Estimated Total: $5-30/month for typical usage**

---

## 🔐 **Security Best Practices**

### **1. IAM Permissions**

Lambda has minimal permissions:
- ✅ Read Parameter Store values
- ✅ Write CloudWatch logs
- ❌ NO access to other AWS resources

### **2. API Gateway Security**

Add API key authentication:

```yaml
# In serverless.yml, add:
provider:
  apiGateway:
    apiKeys:
      - intune-healer-api-key
    usagePlan:
      quota:
        limit: 10000
        period: MONTH
      throttle:
        rateLimit: 100
        burstLimit: 200

functions:
  api:
    events:
      - http:
          path: /webhook/ticket
          method: post
          private: true  # Requires API key
```

Deploy:
```bash
serverless deploy --stage prod
```

Get API key:
```bash
aws apigateway get-api-keys --include-values --query 'items[0].value' --output text
```

Use in requests:
```bash
curl -H "x-api-key: YOUR_API_KEY" $API_URL/webhook/ticket
```

### **3. Network Security**

**Option A: VPC Integration** (Private subnets)
```yaml
provider:
  vpc:
    securityGroupIds:
      - sg-xxxxx
    subnetIds:
      - subnet-xxxxx
      - subnet-yyyyy
```

**Option B: IP Whitelist** (API Gateway)
```yaml
provider:
  apiGateway:
    resourcePolicy:
      - Effect: Allow
        Principal: "*"
        Action: execute-api:Invoke
        Resource:
          - execute-api:/*
        Condition:
          IpAddress:
            aws:SourceIp:
              - "203.0.113.0/24"  # Your office IP
              - "198.51.100.0/24" # Atomicwork IP
```

---

## 🔄 **Updates & Rollbacks**

### **Deploy Updates**

```bash
# Deploy latest code
./deploy-aws.sh prod us-east-1

# Deploy to staging first
./deploy-aws.sh dev us-east-1
```

### **Rollback to Previous Version**

```bash
# List deployments
serverless deploy list --stage prod

# Rollback to specific timestamp
serverless rollback -t 1708124400000 --stage prod
```

### **Update Secrets**

```bash
# Update a single parameter
aws ssm put-parameter \
  --name "/intune-healer/prod/azure-client-secret" \
  --value "new-secret-value" \
  --type SecureString \
  --overwrite

# Lambda picks up new value on next invocation (no redeploy needed!)
```

---

## 🧪 **Testing in Production**

### **Smoke Test Script**

```bash
#!/bin/bash
API_URL="https://xxxxx.execute-api.us-east-1.amazonaws.com/prod"

echo "🧪 Running smoke tests..."

# Test 1: Health check
echo "Test 1: Health check"
curl -s $API_URL/health | jq .

# Test 2: Analyze ticket
echo "Test 2: Analyze ticket"
curl -s -X POST $API_URL/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "TEST-001",
    "subject": "Computer running slow",
    "description": "My computer is very slow",
    "priority": "medium",
    "requester_email": "test@example.com"
  }' | jq .

echo "✅ Smoke tests complete"
```

---

## 🐛 **Troubleshooting**

### **Issue: "Module not found" error**

**Cause:** Dependencies not packaged correctly

**Solution:**
```bash
# Install Docker (required for serverless-python-requirements)
brew install docker

# Start Docker Desktop
open -a Docker

# Redeploy
./deploy-aws.sh prod us-east-1
```

### **Issue: "Access Denied" on Parameter Store**

**Cause:** Lambda doesn't have IAM permission

**Solution:**
Check IAM role in `serverless.yml` includes:
```yaml
- Effect: Allow
  Action:
    - ssm:GetParameter
  Resource:
    - arn:aws:ssm:*:*:parameter/intune-healer/prod/*
```

### **Issue: "Timeout" errors**

**Cause:** Function takes longer than 30s

**Solution:**
Increase timeout in `serverless.yml`:
```yaml
provider:
  timeout: 60  # Increase to 60 seconds
```

### **Issue: Graph API authentication fails**

**Cause:** Incorrect Azure credentials

**Solution:**
```bash
# Verify secrets
aws ssm get-parameter --name "/intune-healer/prod/azure-tenant-id"
aws ssm get-parameter --name "/intune-healer/prod/azure-client-id"
aws ssm get-parameter --name "/intune-healer/prod/azure-client-secret" --with-decryption

# Update if needed
./setup-aws-secrets.sh prod us-east-1
```

---

## 🎯 **Next Steps**

### **1. Configure Atomicwork Webhook**

In Atomicwork admin panel:
1. Go to Settings → Webhooks
2. Add new webhook:
   - **URL:** `https://xxxxx.execute-api.us-east-1.amazonaws.com/prod/webhook/ticket`
   - **Event:** Ticket Created
   - **Method:** POST
   - **Headers:** `Content-Type: application/json`

### **2. Set Up Monitoring**

```bash
# Create CloudWatch alarm for errors
aws cloudwatch put-metric-alarm \
  --alarm-name intune-healer-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=intune-device-healer-prod-api
```

### **3. Enable X-Ray Tracing** (Optional)

```yaml
# In serverless.yml
provider:
  tracing:
    lambda: true
    apiGateway: true
```

---

## 📞 **Support**

**Documentation:**
- AWS Lambda: https://docs.aws.amazon.com/lambda/
- Serverless Framework: https://www.serverless.com/framework/docs/
- Microsoft Graph: https://learn.microsoft.com/graph/

**Logs:**
```bash
# Real-time logs
serverless logs -f api -t --stage prod

# CloudWatch Insights query
aws logs tail /aws/lambda/intune-device-healer-prod-api --follow
```

**Delete Deployment** (cleanup):
```bash
serverless remove --stage prod --region us-east-1
```

---

## ✅ **Deployment Checklist**

- [ ] AWS CLI installed and configured
- [ ] Serverless Framework installed
- [ ] Docker installed (for packaging)
- [ ] Secrets stored in Parameter Store
- [ ] Deployment successful
- [ ] Health endpoint responding
- [ ] Test ticket processed successfully
- [ ] CloudWatch logs visible
- [ ] Webhook URL shared with Atomicwork
- [ ] Monitoring alarms configured

---

**🎉 Your Intune Device Healer is now running 24/7 on AWS Lambda!**
