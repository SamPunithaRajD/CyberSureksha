"""
SecureDocXAI — Document Correlation Graph Engine

Generates node-edge representation of document linkages inside a case,
connecting identities, bank accounts, employers, salaries, and files.
Used for visualizing cross-document verification and highlighting contradictions.
"""

from __future__ import annotations

from typing import Any
from loguru import logger


class DocumentCorrelationGraphEngine:
    """
    Builds a network graph of entities extracted across all files in an investigation case.
    """

    def __init__(self):
        logger.info("Initializing Document Correlation Graph Engine")

    def build_graph(self, documents: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Construct nodes and edges connecting documents to entities.
        
        Parameters
        ----------
        documents : list of dict
            List of serialized/loaded document records in the case.
        anomalies : list of dict
            List of detected anomalies (used to add conflict nodes/edges).
            
        Returns
        -------
        dict
            D3-like JSON structure of nodes and edges.
        """
        logger.info("Building correlation graph for {} documents", len(documents))
        nodes = []
        edges = []
        node_ids = set()

        # Add document nodes
        for idx, doc in enumerate(documents):
            doc_id = str(doc.get("id") or doc.get("_id", ""))
            name = doc.get("original_filename", f"Doc {idx+1}")
            category = doc.get("document_category", "unknown")
            
            nodes.append({
                "id": doc_id,
                "label": name,
                "type": "document",
                "category": category,
                "size": 18,
                "color": "#3b82f6" # Blue
            })
            node_ids.add(doc_id)

        # Helper to safely add entity nodes and link to documents
        def add_entity_node(entity_id: str, label: str, entity_type: str, doc_id: str, is_mismatch: bool = False):
            clean_id = f"entity_{entity_type}_{entity_id}".replace(" ", "_").lower()
            if clean_id not in node_ids:
                nodes.append({
                    "id": clean_id,
                    "label": label,
                    "type": "entity",
                    "entity_type": entity_type,
                    "size": 12,
                    "color": "#e11d48" if is_mismatch else "#10b981" # Red if mismatch, Green if matching
                })
                node_ids.add(clean_id)
                
            # Add link between document and entity
            edges.append({
                "source": doc_id,
                "target": clean_id,
                "type": "contains",
                "label": f"contains {entity_type}",
                "style": "dashed" if is_mismatch else "solid",
                "color": "#f43f5e" if is_mismatch else "#27272a"
            })

        # Process each document and extract nodes
        for doc in documents:
            doc_id = str(doc.get("id") or doc.get("_id", ""))
            ocr = doc.get("ocr_result", {}) or doc.get("results", {}).get("ocr", {})
            if not ocr:
                continue

            entities = ocr.get("entities", {})
            structured = ocr.get("structured_data", {})

            # 1. Names
            names = entities.get("name", [])
            for name in names:
                if name:
                    add_entity_node(name, f"Name: {name}", "name", doc_id)

            # 2. PAN Cards
            pans = entities.get("pan", [])
            for pan in pans:
                if pan:
                    add_entity_node(pan, f"PAN: {pan}", "pan", doc_id)

            # 3. Aadhaar
            aadhaars = entities.get("aadhaar", [])
            for a in aadhaars:
                if a:
                    add_entity_node(a, f"Aadhaar: {a}", "aadhaar", doc_id)

            # 4. Bank Accounts
            accounts = entities.get("account_number", [])
            for acc in accounts:
                if acc:
                    add_entity_node(acc, f"Account: {acc}", "account_number", doc_id)

            # 5. Employer
            employers = entities.get("employer", [])
            for emp in employers:
                if emp:
                    add_entity_node(emp, f"Employer: {emp}", "employer", doc_id)

        # 6. Mark conflicts from anomalies in the graph
        for idx, a in enumerate(anomalies):
            if a.get("category") == "cross_document_inconsistency":
                evidence = a.get("evidence", {})
                ref_doc = evidence.get("reference_doc_id")
                conf_doc = evidence.get("conflict_doc_id")
                field = a.get("field", "identity")
                
                # Check if we have source and target docs
                if ref_doc and conf_doc:
                    conflict_node_id = f"conflict_{field}_{idx}"
                    nodes.append({
                        "id": conflict_node_id,
                        "label": f"Mismatch: {field.upper()}",
                        "type": "conflict",
                        "size": 14,
                        "color": "#f43f5e" # Rose red
                    })
                    
                    edges.append({
                        "source": ref_doc,
                        "target": conflict_node_id,
                        "type": "conflict_link",
                        "label": "disputed",
                        "color": "#f43f5e"
                    })
                    edges.append({
                        "source": conf_doc,
                        "target": conflict_node_id,
                        "type": "conflict_link",
                        "label": "disputed",
                        "color": "#f43f5e"
                    })

        return {
            "nodes": nodes,
            "edges": edges
        }
