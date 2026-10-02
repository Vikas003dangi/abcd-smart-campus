"""
Runnable self-check verifying forensic audit fix contracts across Android Native & Web PWA layers.
Following Ponytail senior dev mode: zero frameworks, pure asserts, self-contained runnable check.
"""

import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read_file(rel_path):
    full_path = os.path.join(BASE_DIR, rel_path)
    assert os.path.exists(full_path), f"File not found: {full_path}"
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def test_android_manifest():
    content = read_file("abcd-twa/app/src/main/AndroidManifest.xml")
    assert "android.permission.FOREGROUND_SERVICE" in content, "Missing FOREGROUND_SERVICE permission"
    assert "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" in content, "Missing FOREGROUND_SERVICE_MEDIA_PLAYBACK permission"
    assert "AlarmPlaybackService" in content, "Missing AlarmPlaybackService declaration"
    assert 'android:foregroundServiceType="mediaPlayback"' in content, "Missing mediaPlayback service type"
    assert "AlarmReceiver" in content, "Missing AlarmReceiver declaration"
    assert "ActionReceiver" in content, "Missing ActionReceiver declaration"
    print("PASS: AndroidManifest permissions and services verified")

def test_alarm_playback_service():
    content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/AlarmPlaybackService.java")
    assert "public class AlarmPlaybackService extends Service" in content, "AlarmPlaybackService must extend Service"
    assert "startForeground" in content, "AlarmPlaybackService must startForeground"
    assert "FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK" in content, "Must declare mediaPlayback foreground service type"
    assert "AudioAttributes.USAGE_ALARM" in content, "Must use USAGE_ALARM for reliable ring volume"
    assert "public static void stopPlayback(Context context)" in content, "Must provide static stopPlayback helper"
    assert "stopForeground(STOP_FOREGROUND_DETACH)" in content or "stopForeground(false)" in content, "Must detach notification"
    print("PASS: AlarmPlaybackService implementation contracts verified")

def test_alarm_receiver_delegation():
    content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/AlarmReceiver.java")
    assert "AlarmPlaybackService.class" in content, "AlarmReceiver must delegate to AlarmPlaybackService"
    assert "context.startForegroundService(serviceIntent)" in content, "Must start foreground service"
    assert "MediaPlayer" not in content, "AlarmReceiver must NOT instantiate inline MediaPlayer without foreground service"
    print("PASS: AlarmReceiver service delegation verified")

def test_action_receiver_silencing():
    content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/ActionReceiver.java")
    assert "AlarmPlaybackService.stopPlayback(context)" in content, "ActionReceiver must stop AlarmPlaybackService on user action"
    print("PASS: ActionReceiver stopPlayback verified")

def test_alarm_sync_activity_cancel():
    content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/AlarmSyncActivity.java")
    assert "AlarmPlaybackService.stopPlayback(this)" in content, "AlarmSyncActivity must stop AlarmPlaybackService on cancel command"
    print("PASS: AlarmSyncActivity cancel handling verified")

def test_sw_push_suppression_and_persistence():
    content = read_file("abcd_web/static/sw.js")
    assert "getPersistedTwaMode" in content, "sw.js must implement getPersistedTwaMode for IndexedDB persistence"
    assert "setPersistedTwaMode" in content, "sw.js must implement setPersistedTwaMode for IndexedDB persistence"
    assert "isTaskNativelyScheduled" in content, "sw.js must implement isTaskNativelyScheduled for per-task native check"
    assert "isAudioAlert && !isGuidy && isNativelyScheduledHere" in content, "sw.js must suppress audio alert notification ONLY when isNativelyScheduledHere"
    print("PASS: sw.js per-task native confirmation and notification suppression verified")

def test_abcd_sound_contracts():
    content = read_file("abcd_web/static/js/abcd-sound.js")
    assert re.search(r"function\s+startABCDAlarm\([^)]*skipAudio\)", content), "startABCDAlarm must accept skipAudio parameter"
    assert "if (!skipAudio)" in content, "tryPlayAlarmAudio must be guarded by !skipAudio"
    assert "isNativeAlarmTwaActive()" in content, "checkUrlAlarmTrigger must check isNativeAlarmTwaActive()"
    assert "!rem.is_alarm && rem.source !== 'course'" in content, "syncRemindersToNativeTwa must sync course reminders"
    assert "rem.is_alarm ? 1 : 0" in content, "syncRemindersToNativeTwa must dynamically compute is_alarm"
    assert "&is_alarm=${isAlarmVal}" in content, "syncRemindersToNativeTwa must pass dynamic isAlarmVal in URI"
    assert "&is_alarm=1" not in content, "syncRemindersToNativeTwa must NEVER hardcode &is_alarm=1"
    assert "tasks: scheduledTasks" in content, "syncRemindersToNativeTwa must sync scheduledTasks to Service Worker"
    print("PASS: abcd-sound.js replay prevention, dynamic course reminder channel, and task sync verified")

if __name__ == "__main__":
    print("Running Alarm Architecture Fix Verification Checks...")
    test_android_manifest()
    test_alarm_playback_service()
    test_alarm_receiver_delegation()
    test_action_receiver_silencing()
    test_alarm_sync_activity_cancel()
    test_sw_push_suppression_and_persistence()
    test_abcd_sound_contracts()
    print("\nALL 7 VERIFICATION CHECKS PASSED SUCCESSFULLY.")
