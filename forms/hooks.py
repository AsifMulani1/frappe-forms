app_name = "forms"
app_title = "Frappe Forms"
app_publisher = "Acme"
app_description = "Google-Forms-style form builder that compiles to real Frappe DocTypes"
app_email = "mulani.asif12@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "forms",
# 		"logo": "/assets/forms/logo.png",
# 		"title": "Frappe Forms",
# 		"route": "/forms",
# 		"has_permission": "forms.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/forms/css/forms.css"
# app_include_js = "/assets/forms/js/forms.js"

# include js, css files in header of web template
# web_include_css = "/assets/forms/css/forms.css"
# web_include_js = "/assets/forms/js/forms.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "forms/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "forms/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "forms.utils.jinja_methods",
# 	"filters": "forms.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "forms.install.before_install"
# after_install = "forms.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "forms.uninstall.before_uninstall"
# after_uninstall = "forms.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "forms.utils.before_app_install"
# after_app_install = "forms.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "forms.utils.before_app_uninstall"
# after_app_uninstall = "forms.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "forms.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "forms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"forms.tasks.all"
# 	],
# 	"daily": [
# 		"forms.tasks.daily"
# 	],
# 	"hourly": [
# 		"forms.tasks.hourly"
# 	],
# 	"weekly": [
# 		"forms.tasks.weekly"
# 	],
# 	"monthly": [
# 		"forms.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "forms.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "forms.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "forms.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "forms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["forms.utils.before_request"]
# after_request = ["forms.utils.after_request"]

# Job Events
# ----------
# before_job = ["forms.utils.before_job"]
# after_job = ["forms.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"forms.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []



# Frappe Forms - headless SPA wiring
# -----------------------------------
# Serve the Vue SPA at /forms and any sub-path (builder, responses, public form).
website_route_rules = [
	{"from_route": "/forms/<path:app_path>", "to_route": "forms"},
]

# Inject window.csrf_token into the SPA's boot so logged-in POSTs aren't rejected 400.
update_website_context = ["forms.api.inject_csrf_token"]

# Show Forms on the /apps screen with its icon.
add_to_apps_screen = [
	{
		"name": "forms",
		"logo": "/assets/forms/frontend/favicon.svg",
		"title": "Frappe Forms",
		"route": "/forms",
		"has_permission": "forms.admin.has_app_permission",
	}
]

# Post-login landing for Forms Managers is the SPA, not Desk.
role_home_page = {
	"Forms Manager": "forms",
}
