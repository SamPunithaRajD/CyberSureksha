import requests
import os

def test_cases_flow():
    print("========================================")
    print("Verifying SecureDocXAI Case-centric API Flow...")
    print("========================================")
    
    base_url = "http://localhost:8000/api/v1"
    
    # 1. Login
    print("Logging in as Underwriter Vikram Nair...")
    r_underwriter = requests.post(f"{base_url}/auth/login", json={
        "email": "underwriter@bank.com",
        "password": "Password123"
    })
    assert r_underwriter.status_code == 200
    underwriter_token = r_underwriter.json()["access_token"]
    underwriter_headers = {"Authorization": f"Bearer {underwriter_token}"}
    
    print("Logging in as Analyst Rahul Sharma...")
    r_analyst = requests.post(f"{base_url}/auth/login", json={
        "email": "analyst@bank.com",
        "password": "Password123"
    })
    assert r_analyst.status_code == 200
    analyst_token = r_analyst.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    
    print("Logging in as Manager Priya Iyer...")
    r_manager = requests.post(f"{base_url}/auth/login", json={
        "email": "manager@bank.com",
        "password": "Password123"
    })
    assert r_manager.status_code == 200
    manager_token = r_manager.json()["access_token"]
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    # 2. Upload Case Documents
    print("\nUploading case documents simultaneously...")
    upload_dir = "uploads/2026-05-31"
    payslip_path = os.path.join(upload_dir, "529bf7114c64415b_clean_salary_payslip.pdf")
    statement_path = os.path.join(upload_dir, "f7668ce607d243d3_clean_statement.pdf")
    
    # Check if files exist, otherwise create dummy ones
    if not os.path.exists(payslip_path):
        os.makedirs(upload_dir, exist_ok=True)
        with open(payslip_path, "wb") as f:
            f.write(b"%PDF-1.4 mock payslip")
    if not os.path.exists(statement_path):
        os.makedirs(upload_dir, exist_ok=True)
        with open(statement_path, "wb") as f:
            f.write(b"%PDF-1.4 mock bank statement")

    files = [
        ("files", (os.path.basename(payslip_path), open(payslip_path, "rb"), "application/pdf")),
        ("files", (os.path.basename(statement_path), open(statement_path, "rb"), "application/pdf")),
    ]
    
    r_upload = requests.post(
        f"{base_url}/cases/upload",
        files=files,
        data={"case_name": "Case Study: Vikram Nair Verification", "priority": "MEDIUM"},
        headers=underwriter_headers
    )
    
    assert r_upload.status_code == 201, f"Expected 201, got {r_upload.status_code}: {r_upload.text}"
    case_data = r_upload.json()
    case_id = case_data["id"]
    case_id_readable = case_data["case_id"]
    case_name_preview = case_data['case_name']
    print(f"Created Case successfully: {case_name_preview} (Readable ID: {case_id_readable}, DB ID: {case_id})")
    assert len(case_data["document_ids"]) == 2
    print(f"Associated Document IDs: {case_data['document_ids']}")

    # 3. Retrieve Case Details
    print("\nFetching Case details...")
    r_case = requests.get(f"{base_url}/cases/{case_id}", headers=analyst_headers)
    assert r_case.status_code == 200
    case_details = r_case.json()
    print(f"Case name: {case_details['case_name']}, Status: {case_details['status']}, Priority: {case_details['priority']}")
    print(f"Case Trust Score: {case_details['trust_score']['score']}% ({case_details['trust_score']['category']})")
    print(f"Case Financial Risk: {case_details['risk_score']['composite']}%")
    print(f"Executive Summary preview: {case_details['explanation']['executive_summary'][:150]}...")
    assert len(case_details["documents"]) == 2
    
    # 4. Trigger Analysis
    print("\nRe-triggering Case analysis...")
    r_analyze = requests.post(f"{base_url}/cases/{case_id}/analyze", headers=analyst_headers)
    assert r_analyze.status_code == 200
    print("Case analysis triggered successfully.")

    # 5. Add Notes
    print("\nAdding investigator comments...")
    r_note = requests.post(f"{base_url}/cases/{case_id}/notes", json={"text": "Checked the Aadhaar photo matches PAN photo."}, headers=analyst_headers)
    assert r_note.status_code == 200
    print("Comment added successfully.")

    # 6. Assign Case
    print("\nAssigning case to analyst Rahul Sharma...")
    r_assign = requests.post(f"{base_url}/cases/{case_id}/assign", headers=analyst_headers)
    assert r_assign.status_code == 200
    print("Case assigned successfully.")

    # 7. Escalate Case
    print("\nEscalating case to Branch Manager...")
    r_escalate = requests.post(
        f"{base_url}/cases/{case_id}/escalate", 
        json={"reason": "Name mismatch is critical between payslip and bank statement. Overriding requires manager approval."}, 
        headers=analyst_headers
    )
    assert r_escalate.status_code == 200
    print("Case escalated successfully.")

    # 8. Interactive LLM Q&A
    print("\nQuerying LLM Reasoning Engine via Q&A Chat...")
    queries = [
        "What names are extracted in the documents?",
        "Is there any visual tampering detected in the statement?",
        "What are the key risk factors in this case?",
    ]
    for q in queries:
        r_qa = requests.post(f"{base_url}/cases/{case_id}/qa", json={"question": q}, headers=analyst_headers)
        assert r_qa.status_code == 200
        print(f"Q: '{q}'")
        print(f"A: '{r_qa.json()['answer']}'\n")

    # 9. Manager Decision
    print("Submitting Branch Manager final decision (APPROVED)...")
    r_decide = requests.post(
        f"{base_url}/cases/{case_id}/decide",
        json={"decision": "APPROVED", "justification": "Verified employer history on EPFO portal. Clean profile."},
        headers=manager_headers
    )
    assert r_decide.status_code == 200
    print("Manager decision APPROVED submitted successfully.")

    # 10. styled report
    print("\nFetching styled PDF/HTML print-ready report...")
    r_report = requests.get(f"{base_url}/cases/{case_id}/report", headers=manager_headers)
    assert r_report.status_code == 200
    assert "SecureDocXAI" in r_report.text
    print("HTML Report generation verified. Title found: 'SecureDocXAI'")
    
    print("\n========================================")
    print("All SecureDocXAI Case API Flow Tests passed!")
    print("========================================")

if __name__ == "__main__":
    test_cases_flow()
