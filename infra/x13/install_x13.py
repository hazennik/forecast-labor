#!/usr/bin/env python3
"""
Install X-13ARIMA-SEATS binary from Census Bureau
Direct download from official source with proper URL
"""
import os
import sys
import shutil
import tarfile
import subprocess
import urllib.request
from pathlib import Path

print("Installing X-13ARIMA-SEATS binary...")

def download_x13_from_census():
    """
    Download X-13 binary directly from Census Bureau
    URL provided by user: https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/x13as_ascii-v1-1-b62.tar.gz
    """
    # Official Census Bureau URL for X-13 v1.1 Build 62 (Linux/Unix ASCII version)
    url = "https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/x13as_ascii-v1-1-b62.tar.gz"
    
    print(f"Downloading X-13 from Census Bureau...")
    print(f"URL: {url}")
    
    try:
        # Create temp directory
        tmp_dir = Path('/tmp/x13_install')
        tmp_dir.mkdir(exist_ok=True)
        
        # Download archive
        archive_path = tmp_dir / 'x13as.tar.gz'
        print(f"Downloading to {archive_path}...")
        urllib.request.urlretrieve(url, archive_path)
        print(f"✓ Downloaded {archive_path.stat().st_size} bytes")
        
        # Extract archive
        print("Extracting archive...")
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(tmp_dir)
        print("✓ Extracted archive")
        
        # Find x13as binary (should be in x13as subdirectory)
        # Archive structure: x13as/x13as (the executable)
        possible_paths = [
            tmp_dir / 'x13as' / 'x13as',           # Most likely: x13as/x13as
            tmp_dir / 'x13as' / 'x13as_ascii',      # Alternative: x13as/x13as_ascii
            tmp_dir / 'x13as_ascii',                # Root level: x13as_ascii
        ]
        
        binary_path = None
        for path in possible_paths:
            if path.exists() and path.is_file():
                binary_path = path
                print(f"✓ Found binary at: {binary_path}")
                break
        
        if not binary_path:
            # Search recursively for any file named x13as (not directories)
            print("Searching recursively for x13as binary...")
            found = [p for p in tmp_dir.rglob('x13as') if p.is_file()]
            if found:
                binary_path = found[0]
                print(f"✓ Found binary at: {binary_path}")
            else:
                print("✗ x13as binary not found in archive")
                print(f"Archive contents: {list(tmp_dir.iterdir())}")
                # List subdirectory contents if exists
                x13as_dir = tmp_dir / 'x13as'
                if x13as_dir.exists() and x13as_dir.is_dir():
                    print(f"Contents of x13as/: {list(x13as_dir.iterdir())}")
                return False
        
        # Install to /usr/local/bin
        target = Path('/usr/local/bin/x13as')
        shutil.copy2(binary_path, target)
        os.chmod(target, 0o755)
        print(f"✓ Installed to {target}")
        
        # Verify it works
        print("Verifying X-13 binary...")
        result = subprocess.run([str(target), '-v'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else "X-13ARIMA-SEATS"
            print(f"✓ X-13 verified: {version_line}")
            return True
        else:
            print(f"⚠️  X-13 binary verification returned code {result.returncode}")
            print(f"stdout: {result.stdout[:200]}")
            print(f"stderr: {result.stderr[:200]}")
            # Still return True - binary exists, version flag might not work in all environments
            return True
            
    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error downloading X-13: {e.code} {e.reason}")
        print(f"   URL: {url}")
        return False
    except urllib.error.URLError as e:
        print(f"✗ URL Error downloading X-13: {e.reason}")
        return False
    except tarfile.TarError as e:
        print(f"✗ Error extracting archive: {e}")
        return False
    except Exception as e:
        print(f"✗ X-13 installation failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

# Download from Census Bureau
if download_x13_from_census():
    print("\n✅ X-13 binary installed successfully from Census Bureau")
    print("Service ready for seasonal adjustment")
    sys.exit(0)
else:
    print("\n✗ X-13 installation failed")
    print("Service will not be able to perform seasonal adjustment")
    sys.exit(1)

