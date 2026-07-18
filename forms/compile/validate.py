# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Publish-time integrity checks that the FF Form controller's per-save validate() can't cheaply do:
# conditional-logic graph sanity. A field's condition_field references another field's stable
# field_key; a cycle (A shows-if B, B shows-if A) or a dangling reference (a controller that was
# since deleted) would otherwise slip through and produce a form that hides fields unexpectably.

import frappe

from forms.compile.naming import LAYOUT_TYPES


def validate_conditional_logic(form):
	"""Throw if any conditional-logic rule references a missing field or forms a cycle.

	Each field has at most one controller (condition_field -> a field_key), so the dependency graph
	is functional: cycle detection is a walk along each field's single out-edge until we revisit a
	node already on the current path.
	"""
	# field_key -> a human label, for readable error messages. Includes layout fields so a rule that
	# (wrongly) points at a section header is still reported by name rather than as a dangling key.
	label_of = {f.field_key: (f.label or f.fieldname or f.field_key) for f in form.fields if f.field_key}

	# field_key -> the field_key it depends on (its controller), for non-layout fields with a rule.
	edge = {}
	for f in form.fields:
		if f.field_type in LAYOUT_TYPES or not f.field_key:
			continue
		controller = (f.condition_field or "").strip()
		if not controller:
			continue
		if controller not in label_of:
			frappe.throw(
				f"'{label_of.get(f.field_key, f.field_key)}' has a conditional-logic rule that "
				f"references a field which no longer exists. Reselect its condition or remove the rule."
			)
		edge[f.field_key] = controller

	# Walk each field's controller chain; a revisit within one walk is a cycle.
	for start in edge:
		seen = []
		node = start
		while node in edge:
			if node in seen:
				loop = seen[seen.index(node):] + [node]
				names = " -> ".join(label_of.get(k, k) for k in loop)
				frappe.throw(f"Conditional-logic rules form a loop: {names}. Break the cycle to publish.")
			seen.append(node)
			node = edge[node]
