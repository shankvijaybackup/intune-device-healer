# Quick Start Guide - Intune Device Healer MCP

Get up and running in **5 minutes**!

## Prerequisites

- Python 3.10 or higher
- Azure subscription with admin access
- Microsoft Intune tenant
- Git

## Step 1: Clone and Install (2 minutes)

```bash
# Clone repository
cd intune-device-healer

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Azure App Registration (3 minutes)

### Create App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Name: `Intune Device Healer MCP`
5. Click **Register**

### Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Description: `MCP Server Secret`
4. Expiration: **24 months**
5. Click **Add**
6. **Copy the secret value immediately** (you won't see it again!)

### Add API Permissions

1. Go to **API permissions**
2. Click **Add a permission** > **Microsoft Graph** > **Application permissions**
3. Add these permissions:

```
✅ DeviceManagementManagedDevices.ReadWrite.All
✅ DeviceManagementConfiguration.ReadWrite.All
✅ DeviceManagementApps.ReadWrite.All
✅ DeviceManagementServiceConfig.ReadWrite.All
✅ DeviceManagementManagedDevices.PrivilegedOperations.All
✅ Directory.Read.All
```

4. Click **Grant admin consent for [Your Tenant]**

### Copy Credentials

From the **Overview** page, copy:

- **Application (client) ID**
- **Directory (tenant) ID**
- **Client secret** (from previous step)

## Step 3: Configure Environment (<1 minute)

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
AZURE_CLIENT_ID=your-client-id-here
AZURE_TENANT_ID=your-tenant-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
```

## Step 4: Run the Server (<1 minute)

```bash
python src/server.py
```

You should see:

```
Starting Intune Device Healer MCP Server
Authentication successful
Server ready (50+ tools available)
```

## Step 5: Connect MCP Client

### For Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "intune-healer": {
      "command": "python",
      "args": ["/absolute/path/to/intune-device-healer/src/server.py"],
      "env": {
        "AZURE_CLIENT_ID": "your-client-id",
        "AZURE_TENANT_ID": "your-tenant-id",
        "AZURE_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### For VS Code Copilot

Add to VS Code `settings.json`:

```json
{
  "mcp": {
    "server": {
      "intune-healer": {
        "command": "python",
        "args": ["/absolute/path/to/intune-device-healer/src/server.py"],
        "env": {
          "AZURE_CLIENT_ID": "your-client-id",
          "AZURE_TENANT_ID": "your-tenant-id",
          "AZURE_CLIENT_SECRET": "your-client-secret"
        }
      }
    }
  }
}
```

## Try It Out!

Ask your AI assistant:

```
"List all Windows devices in my Intune tenant"
```

```
"Check the health of device WIN-LAPTOP-001"
```

```
"Show me the fleet health dashboard"
```

```
"Fix VPN issues on device MACOS-001"
```

```
"Auto-heal device WIN-PC-005 and show me the results"
```

## Available Tools (50+)

### Diagnostic (10 tools)
- `diagnose_device_comprehensive` - Full health check
- `check_hardware_health` - CPU, disk, battery
- `check_network_health` - Connectivity, VPN
- `predict_failures` - AI-powered predictions
- And more...

### Windows Fixes (25+ tools)
- `fix_windows_updates` - Reset Windows Update
- `repair_outlook_pst` - Fix Outlook PST files
- `fix_vpn_configuration` - Repair VPN
- `cleanup_disk_space` - Free up space
- `reset_network_stack` - Fix network issues
- `enable_bitlocker` - Enable encryption
- And 20+ more fixes...

### macOS Fixes (15+ tools)
- `reset_smc` - Fix power/thermal issues
- `reset_nvram` - Fix display/sound issues
- `fix_vpn_profile` - Repair VPN on Mac
- `fix_outlook_mac` - Fix Outlook for Mac
- `repair_disk_permissions` - Fix permissions
- And 10+ more fixes...

### Automation (5 tools)
- `auto_heal_device` - Diagnose + fix automatically
- `bulk_heal_devices` - Fix multiple devices
- `deploy_remediation_script` - Custom scripts
- `sync_device` - Trigger Intune sync

### Monitoring (5 tools)
- `get_fleet_health_dashboard` - Real-time fleet health
- `scan_for_issues` - Find problematic devices
- `get_device_health_score` - Health score (0-100)

## Example Workflows

### 1. Fix a Single Device

```
AI: "Check device WIN-LAPTOP-001 and fix all issues automatically"

You: diagnose_device_comprehensive(device_id="WIN-LAPTOP-001")
     → Health score: 65/100, 5 issues found

You: auto_heal_device(device_id="WIN-LAPTOP-001", auto_approve_safe_fixes=True)
     → Fixed 4/5 issues, health score improved to 92/100
```

### 2. Fleet-Wide VPN Fix

```
AI: "Find all devices with VPN issues and fix them"

You: scan_for_issues(issue_type="vpn")
     → Found 12 devices with VPN problems

You: bulk_heal_devices(device_ids=[...], fix_types=["vpn"])
     → Fixed 11/12 devices successfully
```

### 3. Outlook PST Repair

```
AI: "User reports Outlook is slow on WIN-PC-042, fix it"

You: diagnose_device_comprehensive(device_id="WIN-PC-042")
     → Found: PST file corruption

You: repair_outlook_pst(device_id="WIN-PC-042")
     → PST repaired successfully

You: rebuild_outlook_profile(device_id="WIN-PC-042", user_email="user@company.com")
     → Profile rebuilt, OST will be recreated
```

## Safety Features

### Three-Tier Approval System

**Tier 1 - Automatic** (No approval needed)
- Disk cleanup
- Network resets
- Cache clearing

**Tier 2 - Semi-Automatic** (Approval with `auto_approve=True`)
- Windows Update fixes
- Driver updates
- System file repairs

**Tier 3 - Manual Approval** (Always requires explicit approval)
- Disk repairs (CHKDSK)
- Profile rebuilds
- High-risk operations

## Troubleshooting

### Authentication Failed

```
Error: AADSTS7000215: Invalid client secret
```

**Solution:** Regenerate client secret in Azure Portal and update `.env`

### Permission Denied

```
Error: Application is not authorized
```

**Solution:**
1. Verify all permissions are added in Azure Portal
2. Grant admin consent
3. Wait 10 minutes for permissions to propagate

### Device Not Found

```
Error: Device not found: DEVICE-NAME
```

**Solution:** Device name is case-sensitive, or use device ID instead

## Next Steps

- Read full documentation in [README.md](README.md)
- Check [BUILD_STATUS.md](BUILD_STATUS.md) for implementation details
- Explore all 50+ tools in the server

## Support

- GitHub Issues: [Report bugs](https://github.com/yourusername/intune-device-healer/issues)
- Documentation: [Full docs](docs/)

---

**You're ready to go!** Start healing devices automatically! 🎉
