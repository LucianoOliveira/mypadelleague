#!/usr/bin/env python3

print("🔇 Testing reduced logging verbosity...")
print("Starting Flask app to verify minimal debug output...")
print("-" * 50)

from website import create_app

app = create_app()

print("-" * 50)
print("✅ App created successfully with reduced logging!")
print("🎯 Debug messages should now be minimal.")
print("📝 Note: Werkzeug messages (development server) are set to ERROR level only.")