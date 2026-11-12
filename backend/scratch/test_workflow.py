import requests

def test_workflow():
    print("Testing Case Notes, Underwriter Decisions, and Audit Trail integration...")
    base_url = "http://localhost:8000/api/v1"
    
    # 1. Log in as Underwriter
    print("\nLogging in as Underwriting Officer...")
    r = requests.post(f"{base_url}/auth/login", json={
        "email": "underwriter@bank.com",
        "password": "Password123"
    })
    assert r.status_code == 200, "Underwriter login failed"
    underwriter_token = r.json()["access_token"]
    underwriter_headers = {"Authorization": f"Bearer {underwriter_token}"}
    
    # Get any document to find an analysis ID
    print("Fetching documents...")
    r_docs = requests.get(f"{base_url}/documents/", headers=underwriter_headers)
    assert r_docs.status_code == 200, "Failed to fetch documents"
    docs = r_docs.json()["documents"]
    if not docs:
        print("No documents found. Skipping test.")
        return
        
    doc_id = docs[0]["id"]
    print(f"Using document {doc_id} to get analysis...")
    
    r_analysis = requests.get(f"{base_url}/analysis/document/{doc_id}", headers=underwriter_headers)
    assert r_analysis.status_code == 200, "Failed to fetch analysis"
    analysis_id = r_analysis.json()["id"]
    print(f"Using analysis ID: {analysis_id}")
    
    # Add a case note as Underwriter
    print("Adding a case note as Underwriting Officer...")
    r_note = requests.post(f"{base_url}/analysis/{analysis_id}/notes", json={
        "note": "Underwriter check: Verified employer status. Salary looks consistent with profile."
    }, headers=underwriter_headers)
    print(f"Status Code: {r_note.status_code} | Response: {r_note.json()}")
    assert r_note.status_code == 200, "Failed to add case note"
    
    # Try to make a decision as Underwriter (should be forbidden: 403)
    print("Attempting to make decision as Underwriter (expected: 403)...")
    r_dec_underwriter = requests.post(f"{base_url}/analysis/{analysis_id}/decide", json={
        "decision": "approve",
        "comment": "Underwriter approval comment"
    }, headers=underwriter_headers)
    print(f"Status Code: {r_dec_underwriter.status_code} | Details: {r_dec_underwriter.json()}")
    assert r_dec_underwriter.status_code == 403, "Underwriter was incorrectly allowed to make a final decision!"
    print("Success: Underwriter was denied final decision authority.")
    
    # 2. Log in as Branch Manager
    print("\nLogging in as Branch Manager...")
    r_mgr = requests.post(f"{base_url}/auth/login", json={
        "email": "manager@bank.com",
        "password": "Password123"
    })
    assert r_mgr.status_code == 200, "Manager login failed"
    manager_token = r_mgr.json()["access_token"]
    manager_headers = {"Authorization": f"Bearer {manager_token}"}
    
    # Submit decision as Branch Manager
    print("Submitting decision as Branch Manager...")
    r_dec = requests.post(f"{base_url}/analysis/{analysis_id}/decide", json={
        "decision": "approve",
        "comment": "Salary verified and confirmed via backend check. Approved for loan processing."
    }, headers=manager_headers)
    print(f"Status Code: {r_dec.status_code} | Response: {r_dec.json()}")
    assert r_dec.status_code == 200, "Branch Manager decision failed"
    print("Success: Branch Manager successfully approved the case.")
    
    # 3. Log in as Compliance Auditor
    print("\nLogging in as Compliance Auditor...")
    r_aud = requests.post(f"{base_url}/auth/login", json={
        "email": "auditor@bank.com",
        "password": "Password123"
    })
    assert r_aud.status_code == 200, "Auditor login failed"
    auditor_token = r_aud.json()["access_token"]
    auditor_headers = {"Authorization": f"Bearer {auditor_token}"}
    
    # Fetch compliance logs
    print("Fetching compliance logs as Compliance Auditor...")
    r_logs = requests.get(f"{base_url}/compliance/logs", headers=auditor_headers)
    print(f"Status Code: {r_logs.status_code}")
    assert r_logs.status_code == 200, "Auditor failed to fetch logs"
    
    logs_data = r_logs.json()
    print(f"Fetched {len(logs_data['logs'])} logs. Total logs: {logs_data['total']}")
    
    # Verify that our actions show up in the logs
    actions = [l["action"] for l in logs_data["logs"]]
    print(f"Recent actions in audit trail: {actions[:5]}")
    assert "add_case_note" in actions, "Case note was not logged in the audit trail!"
    assert "decision_approve" in actions, "Manager approval decision was not logged in the audit trail!"
    print("Success: Both actions were correctly logged in the immutable audit trail.")
    
    print("\nAll Multi-role Workflow Tests Passed Successfully!")

if __name__ == "__main__":
    test_workflow()
