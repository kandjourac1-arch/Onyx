"""
Python wrapper for onyx-rust native module.
Provides high-performance functions implemented in Rust.
"""

import sys
import os
from pathlib import Path

# Try to import the compiled Rust module
try:
    import onyx_rust
    RUST_AVAILABLE = True
except ImportError:
    onyx_rust = None
    RUST_AVAILABLE = False


def get_system_info() -> dict:
    """Get system info via Rust (fast)."""
    if RUST_AVAILABLE:
        import json
        return json.loads(onyx_rust.get_system_info())
    return {}


def get_top_processes(limit: int = 10) -> list:
    """Get top processes via Rust."""
    if RUST_AVAILABLE:
        import json
        return json.loads(onyx_rust.get_top_processes(limit))
    return []


def fast_json_parse(json_str: str) -> dict:
    """Fast JSON parsing via Rust."""
    if RUST_AVAILABLE:
        import json
        return json.loads(onyx_rust.fast_json_parse(json_str))
    import json
    return json.loads(json_str)


def hash_string(input_str: str, algorithm: str = "sha256") -> str:
    """Hash string via Rust (supports md5, sha1, sha256)."""
    if RUST_AVAILABLE:
        return onyx_rust.hash_string(input_str, algorithm)
    import hashlib
    h = hashlib.new(algorithm)
    h.update(input_str.encode())
    return h.hexdigest()


def cpu_intensive_task(n: int) -> int:
    """CPU-intensive task offloaded to Rust."""
    if RUST_AVAILABLE:
        return onyx_rust.cpu_intensive_task(n)
    # Pure Python fallback
    sum_val = 0
    for i in range(n):
        sum_val = (sum_val + (i * 1103515245 + 12345)) & 0xFFFFFFFFFFFFFFFF
    return sum_val


def is_rust_available() -> bool:
    """Check if Rust module is available."""
    return RUST_AVAILABLE


def build_rust_module():
    """Build the Rust module using maturin."""
    import subprocess
    project_root = Path(__file__).parent.parent
    try:
        result = subprocess.run(
            ["maturin", "develop", "--release"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print("Rust module built successfully")
            return True
        else:
            print(f"Build failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("maturin not installed. Install with: pip install maturin")
        return False
    except Exception as e:
        print(f"Build error: {e}")
        return False