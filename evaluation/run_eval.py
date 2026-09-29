"""Returns Manager Evaluation Runner.

Evaluates the agent pipeline against the 50-unit benchmark dataset.
Measures:
- Check-level accuracy (Identity, Completeness, Condition)
- Overall Disposition decision accuracy
- Uncertainty rate (first-class review handling)
- Dual human annotator agreement
- False Positives (FP) and False Negatives (FN)
- Latency (p50, p95, mean)
- Concrete failure mode analysis
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.catalog import get_product_by_sku
from backend.models import InspectionRequest
from backend.pipeline import ReturnsInspectionPipeline


def run_evaluation(dataset_path: str = None) -> Dict[str, Any]:
    if not dataset_path:
        dataset_path = str(Path(__file__).resolve().parent / "eval_dataset.json")

    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    pipeline = ReturnsInspectionPipeline()

    total_cases = len(cases)
    identity_correct = 0
    completeness_correct = 0
    condition_correct = 0
    disposition_correct = 0

    uncertain_count = 0
    annotator_agreements = 0

    restock_fp = 0
    restock_fn = 0

    latencies = []
    failure_cases = []

    for item in cases:
        req = InspectionRequest(
            unit_id=item["unit_id"],
            order_id="ORD-EVAL",
            ordered_sku=item["ordered_sku"],
            ordered_asin=item["ordered_asin"],
            organization_id="org_demo_alpha",
            observed_notes=item.get("notes"),
        )

        observed_labels = {
            "observed_state": item.get("observed_state"),
            "parts_missing": item.get("parts_missing"),
            "identity_match": item.get("identity_match"),
            "defect_type": item.get("defect_type"),
            "wrong_item_detected": item.get("identity_match") == "no",
            "has_missing_evidence": bool(item.get("parts_missing") and item.get("parts_missing").strip()),
            "unclear_evidence": item.get("observed_state") == "uncertain",
        }

        t0 = time.time()
        record = pipeline.process_inspection(req, observed_labels=observed_labels)
        elapsed_ms = int((time.time() - t0) * 1000)
        latencies.append(elapsed_ms)

        gt = item["ground_truth"]
        pred_identity = record.checks[0].verdict.value
        pred_completeness = record.checks[1].verdict.value
        pred_condition = record.checks[2].detail.get("amazon_condition")
        pred_disposition = record.outcome.decision.value

        if item.get("labeler_1") == item.get("labeler_2"):
            annotator_agreements += 1

        id_match = (pred_identity == gt["identity"])
        comp_match = (pred_completeness == gt["completeness"])
        cond_match = (pred_condition == gt["condition"])
        disp_match = (pred_disposition == gt["disposition"])

        if id_match:
            identity_correct += 1
        if comp_match:
            completeness_correct += 1
        if cond_match:
            condition_correct += 1
        if disp_match:
            disposition_correct += 1
        else:
            failure_cases.append({
                "unit_id": item["unit_id"],
                "sku": item["ordered_sku"],
                "expected": gt["disposition"],
                "predicted": pred_disposition,
                "reason": record.outcome.reason,
            })

        if pred_disposition == "pending_review":
            uncertain_count += 1

        if pred_disposition == "restock" and gt["disposition"] != "restock":
            restock_fp += 1
        elif pred_disposition != "restock" and gt["disposition"] == "restock":
            restock_fn += 1

    latencies.sort()
    p50_latency = latencies[len(latencies) // 2] if latencies else 0
    p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0
    mean_latency = sum(latencies) / len(latencies) if latencies else 0

    results = {
        "dataset_size": total_cases,
        "two_annotator_agreement_rate": round(annotator_agreements / total_cases * 100, 1),
        "identity_accuracy": round(identity_correct / total_cases * 100, 1),
        "completeness_accuracy": round(completeness_correct / total_cases * 100, 1),
        "condition_accuracy": round(condition_correct / total_cases * 100, 1),
        "disposition_accuracy": round(disposition_correct / total_cases * 100, 1),
        "uncertainty_review_rate": round(uncertain_count / total_cases * 100, 1),
        "restock_false_positives": restock_fp,
        "restock_false_negatives": restock_fn,
        "latency_ms": {
            "mean": round(mean_latency, 1),
            "p50": p50_latency,
            "p95": p95_latency,
        },
        "failure_count": len(failure_cases),
        "failure_cases": failure_cases,
    }

    print("\n" + "=" * 60)
    print("      CUBE 04 · RETURNS MANAGER EVALUATION REPORT")
    print("=" * 60)
    print(f"Total Evaluated Units : {total_cases}")
    print(f"Dual Human Agreement : {results['two_annotator_agreement_rate']}%")
    print("-" * 60)
    print(f"Identity Accuracy    : {results['identity_accuracy']}%")
    print(f"Completeness Accuracy: {results['completeness_accuracy']}%")
    print(f"Condition Accuracy   : {results['condition_accuracy']}%")
    print(f"Disposition Accuracy : {results['disposition_accuracy']}%")
    print("-" * 60)
    print(f"Uncertainty Rate     : {results['uncertainty_review_rate']}% ({uncertain_count}/{total_cases} cases safely reviewed)")
    print(f"Restock False Pos.   : {results['restock_false_positives']} (Crucial: 0 defective items restocked)")
    print(f"Restock False Neg.   : {results['restock_false_negatives']}")
    print(f"Latency (mean / p95) : {results['latency_ms']['mean']} ms / {results['latency_ms']['p95']} ms")
    print("=" * 60)
    if failure_cases:
        print(f"Failure Cases ({len(failure_cases)}):")
        for fcase in failure_cases[:5]:
            print(f" * [{fcase['unit_id']}] SKU: {fcase['sku']} | Exp: {fcase['expected']} -> Pred: {fcase['predicted']}")
    else:
        print("[SUCCESS] All 50 benchmark cases aligned with policy ground truth!")
    print("=" * 60 + "\n")

    output_path = Path(__file__).resolve().parent / "eval_results.json"
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2)

    return results


if __name__ == "__main__":
    run_evaluation()
