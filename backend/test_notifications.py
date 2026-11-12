import requests

def test_notifications_flow():
    print("Verifying Notifications Pipeline...")
    base_url = "http://localhost:8000/api/v1"
    
    # 1. Login as Underwriter
    print("Underwriter login...")
    r_underwriter = requests.post(f"{base_url}/auth/login", json={
        "email": "underwriter@bank.com",
        "password": "Password123"
    })
    assert r_underwriter.status_code == 200
    underwriter_token = r_underwriter.json()["access_token"]
    underwriter_headers = {"Authorization": f"Bearer {underwriter_token}"}
    
    # Fetch underwriter notifications
    print("Fetching underwriter notifications...")
    r_notifs = requests.get(f"{base_url}/notifications/", headers=underwriter_headers)
    assert r_notifs.status_code == 200
    notifs = r_notifs.json()
    print(f"Total underwriter notifications: {len(notifs)}")
    for n in notifs[:5]:
        print(f" - [{n['type'].upper()}] (Read={n['read']}): {n['message']}")
        
    assert len(notifs) > 0, "No notifications generated for underwriter!"
    
    # 2. Login as Analyst
    print("\nAnalyst login...")
    r_analyst = requests.post(f"{base_url}/auth/login", json={
        "email": "analyst@bank.com",
        "password": "Password123"
    })
    assert r_analyst.status_code == 200
    analyst_token = r_analyst.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    
    # Fetch analyst notifications
    print("Fetching analyst notifications...")
    r_analyst_notifs = requests.get(f"{base_url}/notifications/", headers=analyst_headers)
    assert r_analyst_notifs.status_code == 200
    analyst_notifs = r_analyst_notifs.json()
    print(f"Total analyst notifications: {len(analyst_notifs)}")
    for n in analyst_notifs[:5]:
        print(f" - [{n['type'].upper()}] (Read={n['read']}): {n['message']}")
        
    assert len(analyst_notifs) > 0, "No notifications generated for analyst!"
    
    # 3. Test mark single as read
    target_notif = [n for n in notifs if not n["read"]][0]
    notif_id = target_notif["id"]
    print(f"\nMarking notification {notif_id} as read...")
    r_read = requests.post(f"{base_url}/notifications/{notif_id}/read", headers=underwriter_headers)
    assert r_read.status_code == 200
    
    # Verify it is read
    r_notifs_after = requests.get(f"{base_url}/notifications/", headers=underwriter_headers)
    notif_after = [n for n in r_notifs_after.json() if n["id"] == notif_id][0]
    assert notif_after["read"] is True, "Notification read status did not persist!"
    print("Single notification read status verified.")
    
    # 4. Test mark all as read
    print("Marking all notifications as read...")
    r_read_all = requests.post(f"{base_url}/notifications/read-all", headers=underwriter_headers)
    assert r_read_all.status_code == 200
    
    r_notifs_final = requests.get(f"{base_url}/notifications/", headers=underwriter_headers)
    unread_count = len([n for n in r_notifs_final.json() if not n["read"]])
    assert unread_count == 0, f"Expected 0 unread notifications, got {unread_count}"
    print("Mark all notifications as read verified successfully.")
    
    print("\nAll notifications pipeline verifications succeeded!")

if __name__ == "__main__":
    test_notifications_flow()
