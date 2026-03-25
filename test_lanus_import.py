#!/usr/bin/env python3
try:
    import LanusStats as ls
    print("✅ LanusStats imported successfully!")
    print("Available pages:", ls.get_available_pages())
except Exception as e:
    print("❌ Error importing LanusStats:", str(e))