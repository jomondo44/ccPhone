"""Android (APK) entry point. The python-for-android "webview" bootstrap runs
this file and shows http://127.0.0.1:8765/ in a full-screen WebView."""
import os

if "ANDROID_PRIVATE" in os.environ:
    os.environ.setdefault("INDIE_ADMIN_HOME",
                          os.path.join(os.environ["ANDROID_PRIVATE"], "data"))

from indie_admin.server import main  # noqa: E402

main(["--no-browser", "--port", "8765"])
