# Intune Device Healer - Testing Guide

## 🎯 Quick Test Commands

After restarting Claude Desktop, test these MCP tools:

---

## 📋 Your Device IDs

```
VIJAY (Windows):           74576fb0-726d-415a-a97d-0bebe5ad8b42
Mac Studio (macOS):        66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0
AnanyaGupta (Android):     b38f49fa-fd70-4d4e-96ac-8b2b44b5eb97
```

---

## ✅ Test Suite - Run These in Order

### 1. **Test Diagnostic Tools** (Already Working)
```
list_intune_devices
get_fleet_health_dashboard
diagnose_device_comprehensive device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42
check_hardware_health device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0
predict_failures device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42
```

### 2. **Test Windows Remediation** (NEWLY FIXED)

#### Safe Operations (Tier 1 - Auto Execute)
```bash
# Test disk cleanup
cleanup_disk_space device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42

# Test network reset
reset_network_stack device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42

# Test VPN fix
fix_vpn_configuration device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42
```

#### Moderate Risk Operations (Tier 2 - Requires Approval)
```bash
# Enable BitLocker (CRITICAL - VIJAY needs this!)
enable_bitlocker device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42

# Fix Windows Updates
fix_windows_updates device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42 auto_approve=true

# Repair system files
repair_system_files device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42 auto_approve=true

# Repair Outlook PST
repair_outlook_pst device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42

# Update drivers
update_drivers_auto device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42
```

### 3. **Test macOS Remediation** (Already Working)

```bash
# Disk cleanup (Mac Studio is 89% full!)
cleanup_disk_space device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0

# Reset network
reset_network_settings_mac device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0

# Fix VPN
fix_vpn_profile_mac device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0

# Fix Outlook
fix_outlook_mac device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0
```

### 4. **Test Automation Tools**

```bash
# Auto-heal device (fixes all detected issues)
auto_heal_device device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42 auto_approve_safe_fixes=true

# Get health score
get_device_health_score device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42

# Scan for issues
scan_for_issues issue_type=all severity=all
```

---

## 🎯 Priority Tests (Most Important)

### Test #1: Enable BitLocker on VIJAY (CRITICAL SECURITY ISSUE)
```
enable_bitlocker device_id=74576fb0-726d-415a-a97d-0bebe5ad8b42
```
**Expected:** Script deployed successfully, BitLocker enablement starts

### Test #2: Cleanup Mac Studio Disk (89% FULL!)
```
cleanup_disk_space device_id=66eb56a7-4819-4b4d-a15e-9dd9cf04c2d0
```
**Expected:** Script deployed, disk cleanup runs, frees up space

### Test #3: Reset Network on Android (OFFLINE)
```
check_network_health device_id=b38f49fa-fd70-4d4e-96ac-8b2b44b5eb97
```
**Expected:** Confirms device is offline (expected for mobile device)

---

## ✅ Success Indicators

### For Windows Tools:
```json
{
  "success": true,
  "script_id": "some-guid",
  "message": "Script deployed and device synced. Check Intune for execution results.",
  "note": "Script execution happens asynchronously..."
}
```

### For Failures (OLD - Should Not See This):
```json
{
  "success": false,
  "error": "Resource not found for the segment 'deviceManagementScripts'"
}
```

---

## 🔍 Verification in Intune Portal

After deploying scripts via MCP:

1. Go to **Intune Portal** → https://intune.microsoft.com
2. Navigate to **Devices** → **Scripts and remediations** → **Platform scripts**
3. Look for scripts created by "Intune Device Healer"
4. Check **Device status** to see execution results

---

## 📊 Expected Test Results

| Tool Category | Total Tools | Expected Working |
|---------------|-------------|------------------|
| Diagnostic | 7 | 7 (100%) ✅ |
| Windows Remediation | 10 | 10 (100%) ✅ |
| macOS Remediation | 7 | 7 (100%) ✅ |
| Monitoring | 6 | 6 (100%) ✅ |
| Automation | 4 | 3 (75%) ⚠️ |
| **TOTAL** | **34** | **33 (97%)** |

*Note: 1 automation tool (`deploy_remediation_script`) not yet implemented*

---

## 🐛 Troubleshooting

### If Windows tools still fail:

1. **Check Claude Desktop restarted:**
   - Must fully quit (Cmd+Q) and reopen
   - Server logs at: `~/Library/Logs/Claude/mcp*.log`

2. **Verify beta API enabled:**
   ```bash
   # Should see use_beta=True in code
   grep "use_beta=True" ~/intune-device-healer/src/core/graph_client.py
   ```

3. **Run validation test:**
   ```bash
   cd ~/intune-device-healer
   ./venv/bin/python test_windows_fixes.py
   ```

4. **Check Azure permissions:**
   - App must have `DeviceManagementConfiguration.ReadWrite.All`
   - Admin consent must be granted

---

## 📈 Performance Notes

- **Script deployment:** Instant (creates in Intune, device picks up on next check-in)
- **Execution:** Asynchronous (device runs when it checks in, typically 8-hour cycle or on-demand sync)
- **Results:** Available in Intune portal after execution completes
- **Device sync:** Can trigger immediate check-in with `sync_device` tool

---

## 🎉 What's Next

After confirming all tools work:

1. ✅ Enable BitLocker on VIJAY
2. ✅ Clean up Mac Studio disk
3. 🔧 Build Atomicwork webhook integration
4. 📊 Set up automated health monitoring
5. 🤖 Deploy proactive remediation schedules

---

*Happy testing! 🚀*
