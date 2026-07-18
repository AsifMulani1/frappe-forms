# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# The compile engine: the bridge between a friendly FF Form and a real Frappe DocType.
# Ported faithfully from design-reference/src/fieldmodel.jsx.
#
# Split into naming (fieldname vocabulary), doctypes (schema materialisation), and publish
# (the publish step). Re-exported here so `from forms.compile import <name>` keeps resolving.

from forms.compile.doctypes import build_docfields, ensure_checkbox_doctypes
from forms.compile.naming import (
	CHOICE_TYPES,
	FIELD_TYPE_MAP,
	GRID_TYPES,
	LAYOUT_TYPES,
	RESERVED_FIELDNAMES,
	TEXT_TYPES,
	cint_bool,
	freeze_fieldnames,
	newline_options,
	resolve_fieldname,
	scrub_fieldname,
	title_case,
)
from forms.compile.publish import (
	compile_preview,
	publish,
	publish_collection,
	publish_linked,
)
from forms.compile.validate import validate_conditional_logic

__all__ = [
	"CHOICE_TYPES",
	"FIELD_TYPE_MAP",
	"GRID_TYPES",
	"LAYOUT_TYPES",
	"RESERVED_FIELDNAMES",
	"TEXT_TYPES",
	"build_docfields",
	"cint_bool",
	"compile_preview",
	"ensure_checkbox_doctypes",
	"freeze_fieldnames",
	"newline_options",
	"publish",
	"publish_collection",
	"publish_linked",
	"resolve_fieldname",
	"scrub_fieldname",
	"title_case",
	"validate_conditional_logic",
]
