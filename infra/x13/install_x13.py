#!/usr/bin/env python3
"""
Install X-13ARIMA-SEATS binary via statsmodels
Forces download by attempting to use X-13
"""
import os
import shutil
import pandas as pd
import numpy as np

print("Downloading X-13ARIMA-SEATS via statsmodels...")

try:
    # This forces statsmodels to download X-13 binary
    from statsmodels.tsa.x13 import x13_arima_analysis
    
    # Create dummy data to trigger X-13 download
    dates = pd.date_range('2020-01-01', periods=24, freq='MS')
    dummy_series = pd.Series(np.random.randn(24) + 100, index=dates)
    
    # Attempt X-13 analysis (will download binary on first run)
    try:
        result = x13_arima_analysis(dummy_series)
        print("✓ X-13 download triggered successfully")
    except Exception as e:
        print(f"X-13 analysis attempt (triggers download): {str(e)[:100]}")
    
    # Now look for the binary
    x13_locations = [
        '/root/.statsmodels/x13_arima/x13as',
        os.path.expanduser('~/.statsmodels/x13_arima/x13as'),
        '/usr/local/lib/python3.10/dist-packages/statsmodels/tsa/x13/x13as',
        shutil.which('x13as')
    ]
    
    found = False
    for loc in x13_locations:
        if loc and os.path.exists(loc):
            print(f"Found X-13 binary at: {loc}")
            try:
                shutil.copy2(loc, '/usr/local/bin/x13as')
                os.chmod('/usr/local/bin/x13as', 0o755)
                print("✓ X-13 binary installed to /usr/local/bin/x13as")
                found = True
                break
            except Exception as e:
                print(f"Warning: Could not copy binary: {e}")
    
    if not found:
        print("X-13 binary not found after download attempt")
        print("Service will use statsmodels X-13 integration at runtime")
        
except ImportError as e:
    print(f"Could not import statsmodels X-13: {e}")
    print("Will use runtime download")
except Exception as e:
    print(f"X-13 installation error: {e}")
    print("Will use runtime download")

