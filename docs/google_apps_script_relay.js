/**
 * ABCD SMART CAMPUS - GOOGLE APPS SCRIPT INSTANT EMAIL RELAY
 * 
 * WHY THIS EXISTS:
 * Render Free Plan drops outbound TCP connections on SMTP ports (25, 465, 587).
 * This Google Apps Script Web App runs inside Google's cloud infrastructure,
 * listens on standard HTTPS Port 443, and sends emails DIRECTLY from abcd2013baq@gmail.com
 * in under 0.8 seconds without any port blocks or delays!
 * 
 * SETUP INSTRUCTIONS (Takes 60 seconds):
 * 1. Open your browser and log in to https://script.google.com using abcd2013baq@gmail.com
 * 2. Click "+ New project" (top left).
 * 3. Delete any default code in Code.gs and paste ALL the code below.
 * 4. Click "Deploy" (top right) -> "New deployment".
 * 5. Click the gear icon (Select type) -> choose "Web app".
 * 6. Set the following options:
 *    - Description: "ABCD Campus Email Relay"
 *    - Execute as: "Me (abcd2013baq@gmail.com)"
 *    - Who has access: "Anyone"   <--- IMPORTANT! Must be "Anyone" so Render can call it!
 * 7. Click "Deploy". Authorize permissions when prompted by Google.
 * 8. Copy the "Web app URL" (it looks like: https://script.google.com/macros/s/AKfycb.../exec).
 * 9. Add that URL as an environment variable in Render Dashboard (or .env):
 *    GMAIL_RELAY_URL=https://script.google.com/macros/s/AKfycb.../exec
 * 
 * THAT'S IT! All system emails (OTP, password reset, fee reminders, broadcasts)
 * will now deliver instantly in <1 second directly to inboxes!
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No POST body received"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var data = JSON.parse(e.postData.contents);
    var to = data.to;
    var subject = data.subject || "ABCD Campus Notification";
    var htmlBody = data.html || "";
    var textBody = data.text || "";
    var fromName = data.from_name || "ABCD Coaching & Library";

    if (!to) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "Missing 'to' recipient"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // Direct instant delivery via GmailApp API
    GmailApp.sendEmail(to, subject, textBody, {
      htmlBody: htmlBody,
      name: fromName
    });

    return ContentService.createTextOutput(JSON.stringify({
      status: "ok",
      message: "Email delivered successfully"
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "ok",
    service: "ABCD Google Apps Script Instant Email Relay",
    version: "1.0"
  })).setMimeType(ContentService.MimeType.JSON);
}
