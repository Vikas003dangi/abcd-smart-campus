# 🚀 ABCD Campus — Play Store TWA Publishing Guide
> Trusted Web Activity (TWA) — Full Native Notifications + Heads-Up Banners

---

## Why TWA for Play Store?

| Feature | Browser/PWA | TWA on Play Store |
|---|---|---|
| Heads-up notification popup | ❌ Chrome blocks it | ✅ Native HIGH importance |
| App icon in notification | ❌ Chrome icon | ✅ Your ABCD icon |
| Monochrome badge in status bar | ✅ (fixed now) | ✅ |
| Guidy = WhatsApp-style popup | ❌ | ✅ |
| Install from Play Store | ❌ | ✅ |
| Offline support | ✅ | ✅ |
| Push notifications | ✅ | ✅ HIGH importance |

---

## Pre-Requisites (Do These First)

- [ ] Google Play Console account — ₹1,750 one-time fee at [play.google.com/console](https://play.google.com/console)
- [ ] Node.js installed (v18+) — `node --version` to check
- [ ] Java JDK 17+ installed — `java -version` to check  
- [ ] Android Studio installed (for signing keystore) — or use command line keytool
- [ ] Your domain `abcdcampus.in` must serve HTTPS ✅ (already done)

---

## STEP 1 — Verify Your Web Manifest is Correct

Your `site.webmanifest` already has the correct Play Store app ID. **Verify these fields are correct:**

```json
{
  "name": "ABCD Coaching & Library",
  "short_name": "ABCD Campus",
  "start_url": "/",
  "display": "standalone",
  "theme_color": "#e09fd5",
  "background_color": "#854c7a",
  "icons": [
    { "src": "/static/data/favicon/web-app-manifest-192x192.png", "sizes": "192x192" },
    { "src": "/static/data/favicon/web-app-manifest-512x512.png", "sizes": "512x512" }
  ]
}
```

> [!IMPORTANT]
> The 512×512 icon is what appears on the Play Store listing. Make sure it looks good.

---

## STEP 2 — Install Bubblewrap (Google's Official TWA Tool)

```bash
npm install -g @bubblewrap/cli
```

Verify:
```bash
bubblewrap --version
```

---

## STEP 3 — Initialize the TWA Project

Create a new folder (e.g. `abcd-twa/`) and run:

```bash
mkdir abcd-twa
cd abcd-twa
bubblewrap init --manifest=https://abcdcampus.in/static/data/favicon/site.webmanifest
```

Bubblewrap will ask you several questions. Use these answers:

| Question | Your Answer |
|---|---|
| Domain / Origin | `abcdcampus.in` |
| App name | `ABCD Coaching & Library` |
| Short name | `ABCD Campus` |
| Package name | `in.abcdcampus.app` |
| Version code | `1` |
| Version name | `1.0.0` |
| Display mode | `standalone` |
| Status bar color | `#e09fd5` |
| Nav bar color | `#854c7a` |
| Splash screen color | `#854c7a` |
| Splash screen icon | *(path to your 512×512 icon)* |
| Enable notifications | **Yes** |
| Notification delegation | **Yes** |

> [!NOTE]
> When asked about signing key, say **"Create new"** if you don't have one. Bubblewrap will generate it and ask for a password — save that password safely.

---

## STEP 4 — Set Up Digital Asset Links (CRITICAL for TWA)

TWA requires your website to "prove" it owns the app. This is done via the `/.well-known/assetlinks.json` endpoint.

**Your Django project already has this set up at:**
```
https://abcdcampus.in/.well-known/assetlinks.json
```

After generating the APK, Bubblewrap will show you a **SHA-256 fingerprint** of your signing key. You need to put that in your Django view.

Find `assetlinks_json_view` in your `views.py` and update the SHA-256 fingerprint:

```python
def assetlinks_json_view(request):
    return JsonResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "in.abcdcampus.app",
            "sha256_cert_fingerprints": [
                "AA:BB:CC:DD:..."   # ← Replace with YOUR keystore SHA-256 from bubblewrap
            ]
        }
    }], safe=False)
```

**To get your SHA-256 fingerprint:**
```bash
# If you used bubblewrap, the keystore is in android/keystore.jks
keytool -list -v -keystore android/keystore.jks -alias android
```

Copy the `SHA256:` line and replace the `AA:BB:CC:DD:...` above.

---

## STEP 5 — Enable HIGH Importance Notifications in TWA

This is the key to getting **heads-up popups like WhatsApp/Telegram**.

After `bubblewrap init`, open `android/app/src/main/AndroidManifest.xml` and add inside `<application>`:

```xml
<!-- HIGH importance notification channel for campus alerts -->
<meta-data
    android:name="com.google.firebase.messaging.default_notification_channel_id"
    android:value="abcd_alerts" />
```

Then create a file `android/app/src/main/java/in/abcdcampus/app/AbcdApplication.java`:

```java
package in.abcdcampus.app;

import android.app.Application;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.os.Build;

public class AbcdApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // HIGH importance = heads-up popup like WhatsApp
            NotificationChannel channel = new NotificationChannel(
                "abcd_alerts",
                "ABCD Campus Alerts",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Library seat, fee, and Guidy message alerts");
            channel.enableVibration(true);
            channel.setShowBadge(true);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(channel);
        }
    }
}
```

And update `AndroidManifest.xml` to use this Application class:
```xml
<application
    android:name=".AbcdApplication"
    ...>
```

> [!IMPORTANT]
> Without this step, Android assigns Chrome's default "low importance" channel to your notifications and they WON'T pop up.

---

## STEP 6 — Build the APK/AAB

```bash
# Build debug APK (for testing)
bubblewrap build

# The output is at: android/app/build/outputs/apk/release/app-release.apk
```

For Play Store you need an **AAB (Android App Bundle)** — Bubblewrap builds this too:
```bash
bubblewrap build --skipPwaValidation
```

---

## STEP 7 — Test on Real Device Before Upload

```bash
# Install directly to connected Android device
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

**Test checklist:**
- [ ] App opens `abcdcampus.in` correctly in full-screen standalone mode
- [ ] Login works
- [ ] Push notification permission prompt appears
- [ ] Send a test notification from teacher dashboard
- [ ] Notification shows YOUR app icon (not Chrome's)
- [ ] Notification pops up on screen (heads-up) ← this is the big test
- [ ] Tapping notification opens the right page in the app

---

## STEP 8 — Publish to Play Store

1. Go to [play.google.com/console](https://play.google.com/console)
2. Create new app → package name: `in.abcdcampus.app`
3. Upload the `.aab` file from step 6
4. Fill in store listing:
   - **Title**: ABCD Coaching & Library
   - **Short description**: Smart campus platform for library seat management, courses & mentorship
   - **Category**: Education
   - **Screenshots**: Take from your phone (at least 2 phone screenshots required)
5. Set content rating (complete the questionnaire)
6. Set pricing: Free
7. Submit for review → usually 1–3 days for first submission

---

## STEP 9 — Update `assetlinks.json` in Django & Redeploy

After getting your SHA-256 from Step 4, update the view and push:

```bash
git add users/views.py
git commit -m "Update assetlinks.json with Play Store TWA SHA-256 fingerprint"
git push origin main
```

Then verify it works:
```
https://abcdcampus.in/.well-known/assetlinks.json
```

Also verify using Google's tool:
```
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://abcdcampus.in&relation=delegate_permission/common.handle_all_urls
```

---

## Summary of What Changes After Play Store

| | Before (Browser PWA) | After (Play Store TWA) |
|---|---|---|
| Notification icon | Chrome 🔵 | ABCD 💡📖 |
| Badge in status bar | White square → now fixed ✅ | ABCD monochrome ✅ |
| Heads-up popup | ❌ | ✅ HIGH importance |
| Guidy popup like WhatsApp | ❌ | ✅ |
| Sound on notification | ✅ | ✅ |
| Install from Play Store | ❌ | ✅ |
| App icon on home screen | Generic | ABCD icon |

---

> [!TIP]
> For future updates: just push your code to GitHub → deploy to Render → the TWA app automatically uses the new website. **You don't need to republish to Play Store for content changes.** Only republish if you change the Android manifest, icons, or app package settings.
