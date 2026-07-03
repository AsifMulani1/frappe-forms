# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Quiz grading: score the visible graded answers against their server-only answer keys.

from frappe.utils import cint, flt


def _is_correct(spec: dict, value, correct: list[str]) -> bool:
	"""Did this answer match the question's correct answer(s)? (quiz grading)"""
	if value is None or value == "":
		return False
	ft = spec["field_type"]
	if ft == "checkboxes":
		return {str(v) for v in (value or [])} == set(correct)
	if ft == "yes_no":
		picked = "Yes" if value in (1, "1", "Yes", "yes", "true", True) else "No"
		return picked in correct or str(value) in correct
	if ft == "rating":
		# Stored as a fraction of 5; compare on the star count.
		return str(round(flt(value) * 5)) in correct
	return str(value).strip() in correct


def _grade(specs: dict, clean: dict) -> tuple[float, float]:
	"""Total awarded points and max possible, over visible graded fields."""
	score = max_score = 0.0
	for fieldname, spec in specs.items():
		correct = spec.get("correct_answer") or []
		pts = cint(spec.get("points"))
		if not correct or not pts:
			continue
		max_score += pts
		if _is_correct(spec, clean.get(fieldname), correct):
			score += pts
	return score, max_score
