#!/usr/bin/env python3
"""
Test script to verify routes are working
"""
from website import create_app

def test_routes():
    app = create_app()
    
    with app.test_client() as client:
        print("=== TESTING EVENT ROUTES ===\n")
        
        # Test /events route (lowercase)
        print("Testing /events (lowercase)...")
        response = client.get('/events')
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.data.decode()[:200]}...")
        else:
            print("✅ /events route working")
        
        # Test /Events route (uppercase)  
        print("\nTesting /Events (uppercase)...")
        response = client.get('/Events')
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.data.decode()[:200]}...")
        else:
            print("✅ /Events route working")
            
        # Test translate function in context
        print("\nTesting translate function...")
        with app.app_context():
            from website.views import translate
            result = translate('Navigation')
            print(f"translate('Navigation') = '{result}'")
            print("✅ translate function working")
            
        print("\n=== ROUTE TESTING COMPLETE ===")

if __name__ == '__main__':
    test_routes()