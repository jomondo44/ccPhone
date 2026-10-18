[app]
title = Indie Admin Lite
package.name = indieadminlite
package.domain = org.indieadmin
source.dir = .
source.include_exts = py,html,js,css
source.exclude_dirs = tests,bin,.buildozer,.github,termux
version = 1.0.0
requirements = python3
orientation = portrait
fullscreen = 0

# Python serves the UI on localhost; the webview bootstrap displays it.
p4a.bootstrap = webview
p4a.port = 8765

android.permissions = INTERNET
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0
