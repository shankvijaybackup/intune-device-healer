# ⚡ AWS Lambda - Quick Start (5 Minutes)

The fastest way to deploy Intune Device Healer to AWS Lambda.

---

## 🚀 **5-Minute Deployment**

### **Step 1: Install Prerequisites** (2 minutes)

```bash
# Install AWS CLI
brew install awscli

# Install Serverless Framework
npm install -g serverless

# Configure AWS credentials
aws configure
```

### **Step 2: Setup Secrets** (2 minutes)

```bash
cd ~/intune-device-healer
./setup-aws-secrets.sh prod us-east-1
```

**Enter your Azure credentials:**
- Tenant ID: `6adf129d-28f9-498f-871f-ac0bdcdff25f`
- Client ID: `267c8a9f-0e9a-43d2-ae9e-d225d93d4bdd`
- Client Secret: `ral8Q~wVxgExYDF9iPxsziEUWx65GppKew5-ybCa`

### **Step 3: Deploy** (1 minute)

```bash
./deploy-aws.sh prod us-east-1
```

**Wait for deployment...** ☕

---

## ✅ **Test Your API**

After deployment, you'll get an API URL like:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod
```

### **Test Health:**
```bash
curl https://YOUR_API_URL/health
```

### **Test Webhook:**
```bash
curl -X POST https://YOUR_API_URL/webhook/ticket \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "ticket_created",
    "ticket": {
      "ticket_id": "TEST-001",
      "subject": "VPN not working",
      "description": "Cannot connect to VPN",
      "priority": "high",
      "requester_email": "test@example.com",
      "asset": {
        "intune_device_id": "74576fb0-726d-415a-a97d-0bebe5ad8b42"
      }
    }
  }'
```

---

## 📋 **What You Get**

✅ **Always-on REST API** (24/7 availability)
✅ **Auto-scaling** (handles 1 to 1000s of requests)
✅ **Secure secrets** (encrypted in AWS Parameter Store)
✅ **Logging** (CloudWatch logs)
✅ **Monitoring** (CloudWatch metrics)
✅ **Low cost** (~$5-10/month typical usage)

---

## 🔗 **Webhook URL for Atomicwork**

Give this URL to Atomicwork for ticket automation:
```
https://YOUR_API_URL/webhook/ticket
```

---

## 📊 **View Logs**

```bash
serverless logs -f api -t --stage prod
```

---

## 🔄 **Update Deployment**

Made changes? Redeploy:
```bash
./deploy-aws.sh prod us-east-1
```

---

## ❌ **Delete Everything**

To remove the deployment:
```bash
serverless remove --stage prod --region us-east-1
```

---

## 💰 **Cost**

**Free Tier (first 12 months):**
- 1 million requests/month FREE
- 400,000 GB-seconds compute FREE

**After free tier:**
- ~$5-10/month for typical usage
- ~$25/month for heavy usage (1M requests)

---

## 🆘 **Need Help?**

See full guide: `AWS_DEPLOYMENT_GUIDE.md`

**Common Issues:**

1. **"Command not found: serverless"**
   ```bash
   npm install -g serverless
   ```

2. **"Access Denied" errors**
   ```bash
   aws configure  # Re-enter credentials
   ```

3. **"Docker not running"**
   ```bash
   open -a Docker  # Start Docker Desktop
   ```

---

**🎉 That's it! Your API is live!**
