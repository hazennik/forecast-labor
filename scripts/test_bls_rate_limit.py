#!/usr/bin/env python3
"""
Test BLS API rate limit behavior

This script tests whether BLS counts:
- 1 request with 10 series = 1 request
- OR 1 request with 10 series = 10 requests

Usage:
    python scripts/test_bls_rate_limit.py
"""

import os
import requests
import json
from datetime import datetime

def test_bls_batch_counting():
    """
    Test if BLS counts batched series as separate requests
    """
    api_key = os.getenv('BLS_API_KEY')
    
    if not api_key:
        print("❌ BLS_API_KEY not set")
        return
    
    url = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
    
    print("=" * 60)
    print("BLS Rate Limit Test")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print(f"API Key (first 10 chars): {api_key[:10]}...")
    print()
    
    # Test 1: Single series
    print("Test 1: Requesting 1 series...")
    payload1 = {
        'seriesid': ['CES0000000001'],
        'startyear': '2025',
        'endyear': '2025',
        'registrationkey': api_key
    }
    
    response1 = requests.post(url, json=payload1, timeout=10)
    result1 = response1.json()
    
    print(f"  Status: {result1.get('status')}")
    print(f"  Message: {result1.get('message', [])}")
    print()
    
    # Test 2: Batch of 10 series
    print("Test 2: Requesting 10 series in one batch...")
    payload2 = {
        'seriesid': [
            'CES0000000001',  # Total Nonfarm
            'CES0500000001',  # Total Private
            'CES9000000001',  # Government
            'CES0600000001',  # Goods-Producing
            'CES0700000001',  # Service-Providing
            'CES4200000001',  # Retail Trade
            'CES7000000001',  # Leisure and Hospitality
            'CES6500000001',  # Professional Services
            'CES3000000001',  # Manufacturing
            'CES2000000001',  # Construction
        ],
        'startyear': '2025',
        'endyear': '2025',
        'registrationkey': api_key
    }
    
    response2 = requests.post(url, json=payload2, timeout=10)
    result2 = response2.json()
    
    print(f"  Status: {result2.get('status')}")
    print(f"  Message: {result2.get('message', [])}")
    print()
    
    # Test 3: Check if there's a rate limit header
    print("Test 3: Checking response headers...")
    print(f"  Response headers:")
    for key, value in response2.headers.items():
        if 'rate' in key.lower() or 'limit' in key.lower() or 'remaining' in key.lower():
            print(f"    {key}: {value}")
    
    if not any('rate' in k.lower() or 'limit' in k.lower() for k in response2.headers.keys()):
        print("    (No rate limit headers found)")
    
    print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    if result1.get('status') == 'REQUEST_SUCCEEDED' and result2.get('status') == 'REQUEST_SUCCEEDED':
        print("✅ Both tests succeeded")
        print()
        print("This suggests either:")
        print("  1. Rate limit has reset")
        print("  2. Previous usage was from another source")
        print("  3. BLS counts each batch as 1 request (not per series)")
    else:
        print("❌ One or both tests failed")
        print()
        if 'threshold' in str(result1.get('message', [])) or 'threshold' in str(result2.get('message', [])):
            print("Rate limit error detected!")
            print("The quota has been exhausted.")
    
    print()
    print("=" * 60)
    print("ACTION ITEMS:")
    print("=" * 60)
    print("1. Check BLS account dashboard: https://data.bls.gov/registrationEngine/")
    print("2. Look for 'API Usage' or 'Request History'")
    print("3. Report back:")
    print("   - How many requests BLS says you made today")
    print("   - What time the requests were made")
    print("   - If there are any other processes using this key")

if __name__ == "__main__":
    test_bls_batch_counting()

