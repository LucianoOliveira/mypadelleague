#!/usr/bin/env python3
"""
Test edit_event route specifically
"""
from website import create_app
from flask_login import login_user
from website.models import Users

def test_edit_event():
    app = create_app()
    
    with app.test_client() as client:
        print("=== TESTING EDIT_EVENT ROUTE ===\n")
        
        # Try to access edit_event/1 (might need login)
        print("Testing /edit_event/1...")
        response = client.get('/edit_event/1')
        print(f"Status: {response.status_code}")
        
        if response.status_code == 401:
            print("❗ Login required for edit_event (expected)")
        elif response.status_code == 200:
            print("✅ /edit_event/1 route working")
            print("✅ Template rendering without translate errors")
        else:
            print(f"❌ Error: {response.data.decode()[:300]}...")
            
        print("\n=== EDIT_EVENT TESTING COMPLETE ===")

if __name__ == '__main__':
    test_edit_event()