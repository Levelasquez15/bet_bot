#!/usr/bin/env python3
"""
Simple LanusStats import test
"""

try:
    import LanusStats
    print("✅ LanusStats importado correctamente")
except Exception as e:
    print(f"❌ Error importando LanusStats: {e}")