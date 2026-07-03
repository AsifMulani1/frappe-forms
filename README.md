### Frappe Forms

Google-Forms-style form builder that compiles to real Frappe DocTypes

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app forms
```

### Embedding forms on other sites

A published form can be embedded in an `<iframe>` on other websites, but only on
domains its owner explicitly allows (default is off — no site may frame it).

1. Open the form, go to **Form settings → Embedding**, and add one origin per line,
   e.g. `https://example.com`.
2. In the **Share** dialog, copy the generated `<iframe>` snippet and paste it into the
   allowed site.

Under the hood the public form page (`/forms/f/<slug>`) responds with a
`Content-Security-Policy: frame-ancestors 'self' <allowed origins>` header for published
forms that have domains listed; all other routes keep the default same-origin framing.

Only **guest** (public) forms embed cleanly — a login-required form won't work in a
third-party iframe, because browsers don't send the session cookie in that context.

#### Production requirement (nginx)

Bench's default nginx config sends `add_header X-Frame-Options "SAMEORIGIN";`, which
browsers honor over CSP and which has no allow-list mode — so it blocks all cross-site
framing regardless of the app. To let embedding work in production, stop nginx sending
that header for the public form path. In your site's nginx config, add a location block
that overrides it (adjust the port/upstream to match your bench):

```nginx
location ~ ^/forms/f/ {
    # Drop the blanket X-Frame-Options so the app's frame-ancestors CSP takes effect.
    proxy_pass http://frappe-bench-frappe;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # nginx add_header does not inherit into a location once it sets its own, so simply
    # not adding X-Frame-Options here removes it for this path.
}
```

(No nginx change is needed for local `bench start`, which doesn't set that header.)

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/forms
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
