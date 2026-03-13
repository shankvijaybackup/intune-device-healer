#!/usr/bin/env python3
"""
Test script to verify Windows remediation fixes
Run this after restarting Claude Desktop to verify all fixes work
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.config import settings
from core.auth import GraphAuthenticator
from core.graph_client import GraphClient
from tools.windows_remediation import WindowsRemediationTools

async def test_windows_script_deployment():
    """Test that Windows scripts now deploy successfully"""

    print("=" * 70)
    print("TESTING WINDOWS REMEDIATION FIXES")
    print("=" * 70)

    # Initialize
    authenticator = GraphAuthenticator(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret
    )

    graph = GraphClient(authenticator, settings)
    windows_tools = WindowsRemediationTools(authenticator, settings)

    # Get Windows device
    print("\n1. Finding Windows device...")
    devices = await graph.get_managed_devices()
    windows_device = None

    for device in devices:
        if device.get("operatingSystem") == "Windows":
            windows_device = device
            break

    if not windows_device:
        print("❌ No Windows device found in tenant")
        return False

    device_id = windows_device["id"]
    device_name = windows_device.get("deviceName", "Unknown")
    print(f"✅ Found Windows device: {device_name} ({device_id})")

    # Test a simple remediation tool
    print(f"\n2. Testing cleanup_disk_space on {device_name}...")

    try:
        result = await windows_tools.cleanup_disk_space(device_id)

        if result.get("success"):
            print(f"✅ SUCCESS! Script deployed")
            print(f"   Script ID: {result.get('execution_result', {}).get('script_id')}")
            print(f"   Message: {result.get('message')}")
            return True
        else:
            print(f"❌ FAILED: {result.get('message')}")
            print(f"   Error: {result.get('execution_result', {}).get('error')}")
            return False

    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Windows Remediation Fix Validation")
    print("=" * 70)

    try:
        success = await test_windows_script_deployment()

        print("\n" + "=" * 70)
        if success:
            print("✅ ALL TESTS PASSED - Windows remediation tools are working!")
            print("=" * 70)
            sys.exit(0)
        else:
            print("❌ TESTS FAILED - Windows remediation tools still broken")
            print("=" * 70)
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test suite failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
