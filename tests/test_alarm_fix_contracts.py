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
    assert "rem.is_alarm ? 1 : 0" in content, "syncRemindersToNativeTwa must dynamically compute is_alarm"
    assert "&is_alarm=${isAlarmVal}" in content, "syncRemindersToNativeTwa must pass dynamic isAlarmVal in URI"
    assert "&is_alarm=1" not in content, "syncRemindersToNativeTwa must NEVER hardcode &is_alarm=1"
    assert "CONFIRM_NATIVE_TASK" in content, "abcd-sound.js must send CONFIRM_NATIVE_TASK to sw"
    assert "schedule_ack" in content, "abcd-sound.js must listen for schedule_ack"
    assert "abcdalarm://reconcile" in content, "abcd-sound.js must dispatch abcdalarm://reconcile"
    print("PASS: abcd-sound.js replay prevention, dynamic course reminder channel, and task sync verified")

def test_phase1_expiry_bug_fixed():
    sched_content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/NativeAlarmScheduler.java")
    recv_content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/AlarmReceiver.java")
    assert "STALE_MISSED_GRACE_MILLIS = 6 * 60 * 60 * 1000L" in sched_content, "Must define 6-hour missed alarm grace period"
    assert "OFFLINE_EXPIRY_GRACE_MILLIS" not in sched_content, "Must eliminate 14-day expiry rule"
    assert "14 * 24 * 60 * 60" not in sched_content, "Must eliminate 14-day expiry calculation"
    assert "reconcileWithActiveServerIds" in sched_content, "Must implement reconcileWithActiveServerIds"
    assert "STALE_MISSED_GRACE_MILLIS" in recv_content, "AlarmReceiver must use STALE_MISSED_GRACE_MILLIS"
    print("PASS: Phase 1 Expiry bug fix & reconciliation purge verified")

def test_phase1_recurrence_engine_and_test_hook():
    sched_content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/NativeAlarmScheduler.java")
    gradle_content = read_file("abcd-twa/app/build.gradle")
    assert "calculateNextTrigger" in sched_content, "Must implement calculateNextTrigger"
    assert "every_n_days" in sched_content, "Must support every_n_days"
    assert "monthly" in sched_content, "Must support monthly"
    assert "weekly" in sched_content, "Must support weekly"
    assert "until_date" in sched_content, "Must support until_date"
    assert "test_short_" in sched_content, "Must support test_short_ debug hook"
    assert "ENABLE_TEST_ALARM_SHORT_TIMING" in gradle_content, "app/build.gradle must define ENABLE_TEST_ALARM_SHORT_TIMING BuildConfig flag"
    print("PASS: Phase 1 Recurrence engine and test hook verified")

def test_phase2_bidirectional_ack_and_exact_fallback():
    sync_content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/AlarmSyncActivity.java")
    launcher_content = read_file("abcd-twa/app/src/main/java/in/abcdcampus/app/LauncherActivity.java")
    sw_content = read_file("abcd_web/static/sw.js")
    course_content = read_file("abcd_web/users/templates/users/course_detail.html")

    assert "sendPostMessageToPage" in launcher_content, "LauncherActivity must have sendPostMessageToPage"
    assert "schedule_ack" in sync_content, "AlarmSyncActivity must dispatch schedule_ack"
    assert "task.exact !== true" in sw_content, "sw.js must require confirmed task.exact === true before suppressing push"
    assert "checkGlobalDueAlarms" in course_content, "course_detail.html must trigger checkGlobalDueAlarms immediately on save"
    print("PASS: Phase 2 Bidirectional ACK, exact fallback, and course detail immediate sync verified")

if __name__ == "__main__":
    print("Running Alarm Architecture Fix Verification Checks...")
    test_android_manifest()
    test_alarm_playback_service()
    test_alarm_receiver_delegation()
    test_action_receiver_silencing()
    test_alarm_sync_activity_cancel()
    test_sw_push_suppression_and_persistence()
    test_abcd_sound_contracts()
    test_phase1_expiry_bug_fixed()
    test_phase1_recurrence_engine_and_test_hook()
    test_phase2_bidirectional_ack_and_exact_fallback()
    print("\nALL 10 VERIFICATION CHECKS PASSED SUCCESSFULLY.")
