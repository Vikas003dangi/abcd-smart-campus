# 🧪 ABCD Smart Campus — Complete Pre-Launch Testing Guide
> One-Man Army Edition | Every feature, every role, best-to-worst test cases

---

## 🗺️ WHO DOES WHAT (Roles Overview)

| Role | Access |
|---|---|
| **Public / Guest** | Home, About, Services, Contact, Library Availability, Hall of Fame, Courses (public), Admission Form |
| **Student (Library/Coaching)** | Student Dashboard, My Seat, Complaints, Courses, Guidy (student side), Notifications, Profile, Todo, Alumni Dashboard (if alumni too) |
| **Alumni** | Alumni Dashboard, Hall of Fame, Achievement Form, Guidy (guide side) |
| **Teacher / Staff** | Teacher Dashboard (all tabs), Seat Manager, Fee Manager, Courses Manager, Broadcast, Progress, Visitor Insights, Todo, Guidy (teacher side) |
| **Django Admin** | `/admin/` — full DB access |

---

## ✅ TEST PRIORITY KEY

- 🔴 **CRITICAL** — Must work perfectly or app is broken
- 🟡 **IMPORTANT** — Core UX, must work
- 🟢 **NICE TO HAVE** — Edge case, polish

---

---

# SECTION 1 — PUBLIC / GUEST (No Login)

## 1.1 — Home Page
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 1 | Home page loads without error | 🔴 | Open `/` as logged out | Open while DB is down |
| 2 | Theme toggle (dark/light) works | 🟡 | Click toggle, refresh — stays remembered | Toggle rapidly |
| 3 | All nav links work (About, Services, Contact) | 🟡 | Click each link | Click with slow network |
| 4 | Library availability button works | 🟡 | Click → see available seats | Click when no seats exist |
| 5 | Visitor intent tracking fires | 🟢 | Express interest in seat → intent recorded | Do it without login |

## 1.2 — Registration
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 6 | Register with valid new email | 🔴 | Fill all fields, submit → account created | Submit with existing email |
| 7 | Password mismatch shows error | 🔴 | Enter mismatching passwords | Submit form via direct POST |
| 8 | Email already registered shows error | 🔴 | Try to re-register same email | Same email, different username |
| 9 | Google OAuth registration works | 🟡 | Click "Continue with Google" → redirected properly | Google OAuth token expired |
| 10 | Register with weak password rejected | 🟡 | Type short password → error shown | 1-char password submitted |

## 1.3 — Login / Logout
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 11 | Normal email/password login works | 🔴 | Login with valid creds → dashboard redirect | Wrong password 5 times |
| 12 | Mobile number login works | 🔴 | Login with mobile number | Login with partial mobile |
| 13 | Google OAuth login works | 🟡 | Login via Google → correct dashboard | Google popup blocked |
| 14 | Wrong password shows error | 🔴 | Wrong password → error, no crash | SQL-injection style input |
| 15 | Post-login router goes to right dashboard | 🔴 | Student → student dash, Teacher → teacher dash | User with no profile |
| 16 | Logout clears session | 🔴 | Click logout → redirect to home, back button shows no private data | Logout via direct URL |

## 1.4 — Forgot Password (OTP Flow)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 17 | Enter registered email → OTP sent | 🔴 | Valid email → email received with OTP | Unregistered email |
| 18 | OTP verification works | 🔴 | Enter correct OTP → proceed to reset | Enter wrong OTP |
| 19 | OTP expiry — expired OTP rejected | 🟡 | Wait > 10 min, try OTP → rejected | Use OTP twice |
| 20 | Reset password page works | 🔴 | Enter new password → login with new pass | Paste password with spaces |

## 1.5 — Admission Form
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 21 | Form loads for non-logged user (redirects to register) | 🟡 | Open admission form without login → asked to register/login | |
| 22 | Logged in student can submit admission form | 🔴 | All fields filled correctly → submitted | Empty required fields |
| 23 | Profile photo upload works | 🔴 | Select photo → preview shown | Upload 20MB file |
| 24 | If photo exists, old photo shown in preview | 🔴 | User who already has photo → sees it in preview | |
| 25 | Photo replacement replaces across all profiles | 🔴 | Change photo in form → appears in dashboard & guidy | Save without confirming |
| 26 | Seat selector shows real-time availability | 🔴 | Select floor → available seats shown correctly | All seats occupied |
| 27 | Shift-enabled seats (40-53 Ground Floor) show shift option | 🟡 | Select seat 42 → morning/evening option appears | Select seat 1 → no shift shown |
| 28 | Duplicate service type form submission blocked | 🟡 | Already library student tries to resubmit library form | Submit same form in 2 tabs |
| 29 | Form submission creates StudentProfile with `pending` status | 🔴 | Submit → admin sees new pending student | DB error mid-submission |

## 1.6 — Public Pages
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 30 | `/library-availability/` shows correct seat map | 🟡 | Open → accurate available count | Open during seat update |
| 31 | `/resolved-complaints/` loads without login | 🟡 | Open page → see resolved complaints | No resolved complaints |
| 32 | `/hall-of-fame/` loads and shows achievements | 🟡 | Approved achievements displayed | No approved achievements |
| 33 | `/courses/` shows public-targeted courses | 🟡 | Guest sees public courses | No public courses |
| 34 | Contact form submission works | 🟢 | Fill form → success message | Missing email field |

---

# SECTION 2 — STUDENT DASHBOARD

## 2.1 — Student Dashboard (Main)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 35 | Dashboard loads correctly for admitted student | 🔴 | Login as admitted student → dashboard with all widgets | Pending/on-hold student |
| 36 | Dashboard shows pending/on-hold status message correctly | 🔴 | Login as pending student → see correct status badge | |
| 37 | Broadcast banners appear and dismiss works | 🟡 | Active broadcast → banner shown, X dismisses it | Banner dismissal fails silently |
| 38 | Notification bell shows unread count | 🟡 | Unread notifications → bell badge correct | 100+ notifications |
| 39 | Theme switch persists across page refresh | 🟢 | Toggle dark → refresh → still dark | |

## 2.2 — Profile
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 40 | Profile page loads with all correct info | 🟡 | Open `/profile/` → all fields shown | Profile with missing fields |
| 41 | Change password works | 🔴 | Enter old + new password → success, can login with new | Wrong old password entered |
| 42 | OTP login toggle (enable/disable) works | 🟢 | Toggle OTP status → saved correctly | Toggle with no email set |
| 43 | Profile photo change updates across the app | 🔴 | Change photo in profile → seen in dashboard/guidy | Upload corrupted file |
| 44 | Guest profile details shows correct data | 🟢 | Open `/profile/guest/` → correct info | User with no student profile |

## 2.3 — My Seat
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 45 | Seat status shown correctly (occupied / on hold / none) | 🔴 | Open `/my-seat/` → correct info | Student with no seat |
| 46 | Request Seat Hold — valid duration submitted | 🔴 | Select date range → request submitted → appears in teacher dashboard | Select past date |
| 47 | Request Seat Hold — duplicate request rejected | 🟡 | Already has pending hold → can't request again | Submit twice rapidly |
| 48 | Cancel seat hold request works | 🟡 | Active hold → request cancel → teacher sees cancel request | Cancel already ended hold |
| 49 | Request Seat Switch — works with valid target seat | 🔴 | Select available seat → request submitted | Select occupied seat |
| 50 | Cancel seat switch request works | 🟡 | Pending switch → cancel button → cancelled | Cancel after approval |
| 51 | Seat map shows correct floor/shift availability | 🟡 | Interactive seat map loads, colors match status | Map with all seats occupied |

## 2.4 — Complaints
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 52 | Submit complaint with subject + message | 🔴 | Fill form → submit → success page shown | Empty message submitted |
| 53 | Custom subject works | 🟡 | Select "Other" → type custom subject → saves | Too-long subject text |
| 54 | Complaint success page shows submitted complaint | 🟡 | After submission → success page with details | Go back after submission |
| 55 | Rate resolved complaint (1–5 stars) | 🟡 | Resolved complaint → rate it → saved | Rate already rated complaint |
| 56 | Cannot rate pending/in-progress complaint | 🟡 | Try to rate pending → blocked | Direct POST to rating URL |

## 2.5 — Courses (Student Side)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 57 | Course list shows relevant courses | 🔴 | Library student sees library-targeted courses | No courses assigned |
| 58 | Course detail page opens with videos + materials | 🔴 | Open course → playlist loads, materials listed | YouTube API down |
| 59 | Download study material works | 🔴 | Click download → file downloads correctly | Private material for guest |
| 60 | Submit course review (rating + comment) | 🟡 | Submit 5-star review → appears in course | Submit duplicate review |
| 61 | Submit course question works | 🟡 | Type question → submitted → shown in Q&A | Submit empty question |
| 62 | Upvote question/answer works | 🟢 | Click upvote → count increases | Upvote own question |
| 63 | Set learning reminder works | 🟢 | Set reminder for course → reminder appears in todo | Set reminder with past time |
| 64 | Like/Bookmark course (toggle interaction) | 🟢 | Click like → icon fills → click again → unfilled | |

## 2.6 — Notifications
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 65 | Notifications list loads | 🟡 | Open notification panel → all notifications shown | 100+ notifications |
| 66 | Mark individual notification as read | 🟡 | Click notification → marked read, unread count drops | Click on already-read one |
| 67 | Mark all as read works | 🟡 | Click "mark all read" → all cleared | No notifications to mark |
| 68 | Delete individual notification | 🟡 | Delete → removed from list | Delete non-existent ID |
| 69 | Bulk delete notifications | 🟢 | Select multiple → delete → all removed | Select 0 then bulk delete |
| 70 | Mark notification as unread | 🟢 | Mark read → mark back unread → badge reappears | |

---

# SECTION 3 — ALUMNI DASHBOARD

## 3.1 — Alumni Access & Dashboard
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 71 | Alumni dashboard loads for approved alumni | 🔴 | Login as alumni → `/alumni/dashboard/` loads | Non-alumni user accessing URL |
| 72 | Dual-role user (student + alumni) sidebar switching works | 🔴 | Student link → student dash, Alumni link → alumni dash | Switch rapidly |
| 73 | Alumni sees their submitted achievements | 🟡 | Dashboard shows achievement status (pending/approved) | No achievements submitted |

## 3.2 — Achievement Form
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 74 | Submit achievement form with all fields | 🔴 | Fill all fields + upload photo → submitted | Missing required fields |
| 75 | Achievement photo upload works | 🔴 | Upload image → preview shown → saved | Upload PDF instead of image |
| 76 | Edit existing achievement (before approval) | 🟡 | Open edit form → change data → saved | Edit after teacher approval |
| 77 | Delete achievement works | 🟡 | Delete pending achievement → gone from list | Delete already-approved one |

## 3.3 — Hall of Fame (Public + Alumni)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 78 | Hall of Fame shows only approved achievements | 🔴 | Open `/hall-of-fame/` → only approved shown | Pending achievements not visible |
| 79 | Achievement detail page works | 🟡 | Click on achievement → detail page with full info | Achievement with missing fields |
| 80 | Rating display (stars) shows correctly | 🟢 | Approved achievement with rating → correct star count | Rating of 0 |

---

# SECTION 4 — GUIDY (Mentorship & Chat)

## 4.1 — Guidy Home (Merged View)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 81 | Guidy home loads correctly from student dashboard | 🔴 | Open `/guidy/` as student → see alumni list + chats | No alumni in system |
| 82 | Guidy home loads correctly from alumni dashboard | 🔴 | Open `/guidy/` as alumni → see guidance requests | No pending requests |
| 83 | Dual-role user sees merged view (student+alumni conversations) | 🔴 | Login as both → all conversations visible in one guidy | |
| 84 | Role subtitle shows correctly (Student vs Alumni Guide) | 🟡 | When viewed as student → "Student" shown, not "Alumni Guide" | |

## 4.2 — Guidance Requests (Student → Alumni)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 85 | Student sends guidance request to alumni | 🔴 | Click "Seek Guidance" → request sent → alumni notified | Request to blocked alumni |
| 86 | Check guidance status works | 🟡 | Open `/guidy/status/{alumni_pk}/` → correct status shown | Pending/rejected status |
| 87 | Alumni accepts guidance request | 🔴 | Alumni clicks accept → chat session opens | Accept already-accepted request |
| 88 | Alumni rejects guidance request | 🟡 | Click reject → student sees rejected status | |
| 89 | Alumni restricts student | 🟡 | Restrict → student can't send new requests | Try to request after restriction |

## 4.3 — 1-on-1 Chat (Guidance + Direct)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 90 | Send text message works | 🔴 | Type message → send → appears for both | Send empty message |
| 91 | Send image/file in chat | 🟡 | Attach file → sends → visible to other user | Upload 50MB file |
| 92 | Poll (real-time message fetch) works | 🔴 | Send message → other side sees it within 2s | Very slow network |
| 93 | Delete message works (own messages only) | 🟡 | Long-press/click delete → message removed | Delete other user's message |
| 94 | Pin message works | 🟢 | Pin a message → appears in pinned section | Pin already-pinned message |
| 95 | Star message works | 🟢 | Star → appears in starred list | Star then unstar |
| 96 | Search messages in chat | 🟢 | Search keyword → matching messages highlighted | Search with no results |
| 97 | Load older messages works | 🟡 | Scroll up → "Load Older" → older messages appear | At very beginning of chat |
| 98 | End session works | 🟡 | Click end session → chat locked | End already-ended session |
| 99 | Clear chat works | 🟢 | Clear → messages gone for this user | Clear in empty chat |
| 100 | Delete session permanently | 🟢 | Delete → session gone from guidy home | |
| 101 | Block user works | 🟡 | Block → blocked user can't send | Block same user twice |
| 102 | Unblock user works | 🟡 | Unblock → can chat again | Unblock non-blocked user |
| 103 | Back button goes to correct dashboard | 🔴 | From Alumni Guidy → back → Alumni Dashboard (not Student) | |

## 4.4 — Group Chat
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 104 | Create group chat with multiple members | 🟡 | Add 3 users → create → group appears | Create group with 1 member |
| 105 | Send message in group | 🟡 | Message sent → all members see it | Send in inactive group |
| 106 | Group settings update (name, description) | 🟢 | Update name → saved → shown to all members | Blank name submitted |
| 107 | Add/remove members from group | 🟢 | Add new member → they see group | Remove only remaining member |
| 108 | Delete group for user (not for others) | 🟢 | Delete → gone from your list, still visible to others | |
| 109 | Pin/Star messages in group | 🟢 | Same as 1-on-1 pin/star | |
| 110 | Search messages in group | 🟢 | Search keyword → results shown | |
| 111 | Clear group chat for self | 🟢 | Clear → only your view cleared | |

## 4.5 — Teacher in Guidy
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 112 | Teacher can initiate direct chat with any student | 🟡 | Teacher → select student → direct chat opens | Select non-existent student |
| 113 | Teacher direct chat send/receive works | 🟡 | Both can message | Message when user blocked |
| 114 | Teacher Guidy profile update works | 🟢 | Update display name/bio → saved | Blank display name |

## 4.6 — Profile Info Drawer in Guidy
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 115 | Click user name → profile drawer opens | 🟡 | Drawer shows correct photo, name, role | Drawer for deleted user |
| 116 | Alumni photo shows in drawer (achievement photo, not student photo) | 🟡 | View alumni profile → achievement photo shown | |
| 117 | Student photo shown correctly for student view | 🟡 | View student profile → student photo shown | |

---

# SECTION 5 — TEACHER DASHBOARD

## 5.1 — Dashboard Main
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 118 | Teacher dashboard loads all tabs correctly | 🔴 | Open `/teacher/` → all tabs load without error | Very large student count |
| 119 | Live stats API refreshes correctly | 🟡 | Stats update without page reload | API call with no data |
| 120 | Tab switching works smoothly | 🟡 | Click each tab → content loads, no duplicate JS | Click same tab twice |

## 5.2 — Student Management
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 121 | View student details page | 🔴 | Click student name → detail page loads correctly | Student with incomplete data |
| 122 | Approve student (pending → admitted) | 🔴 | Click Approve → status changes, student notified | Approve already-approved |
| 123 | Edit student details (name, mobile, etc.) | 🔴 | Edit fields → save → changes reflected | Blank required field |
| 124 | Delete student works | 🔴 | Delete → student + user account removed | Delete student with active seat |
| 125 | Upload profile photo for student | 🟡 | Choose photo → upload → appears in student card | Upload corrupted image |
| 126 | Delete student profile photo | 🟡 | Delete → photo removed, default avatar shown | Delete when no photo exists |
| 127 | Admission requests tab shows pending students | 🔴 | Pending students listed → approve/deny works | No pending students |

## 5.3 — Holds Tab (Hold / Switch / Cancel-Hold)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 128 | Pending hold requests shown correctly | 🔴 | Hold requests visible with student info, seat, dates | No hold requests |
| 129 | Approve hold request → seat status changes to on_hold | 🔴 | Approve → seat locked, student notified | Approve same request twice |
| 130 | Deny hold request → seat stays occupied | 🔴 | Deny → seat stays, student notified | |
| 131 | Switch seat requests shown | 🔴 | Switch requests visible with current + target seat | No switch requests |
| 132 | Approve seat switch → seats reassigned | 🔴 | Approve → student moved to new seat | Target seat occupied |
| 133 | Reject seat switch → stays in current seat | 🟡 | Reject → no change, student notified | |
| 134 | Cancel-hold requests shown | 🔴 | Cancel hold requests visible | No cancel requests |
| 135 | Approve cancel-hold → seat returned to occupied | 🔴 | Approve → hold ended early, seat back | |
| 136 | Deny cancel-hold → hold continues | 🟡 | Deny → hold stays active | |

## 5.4 — Seat Manager
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 137 | Seat manager page loads with floor map | 🔴 | Open seat manager → both floors shown | No seats in DB |
| 138 | Assign seat to student manually | 🔴 | Select student + seat → assign → seat becomes occupied | Assign already-occupied seat |
| 139 | Remove student from seat | 🔴 | Click remove → seat freed | Remove from seat with hold |
| 140 | Lock/unlock specific seat (or shift) | 🟡 | Lock seat → appears locked in floor map | Lock already-locked seat |
| 141 | Teacher-initiated hold on seat | 🟡 | Teacher puts seat on hold → hold active | Hold on unoccupied seat |
| 142 | Export floor data (CSV/Excel) | 🟢 | Click export → file downloads correctly | Export empty floor |
| 143 | Real-time seat map updates | 🟡 | After action → map auto-refreshes correctly | Refresh with failed API |

## 5.5 — Fee Management
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 144 | Fee calendar view loads for a student | 🔴 | Open fee calendar → months shown with paid/unpaid status | Student with no payment history |
| 145 | Record a fee payment (month/year/amount) | 🔴 | Process fees → payment saved, expiry updated | Duplicate month payment |
| 146 | Delete a payment record | 🟡 | Delete payment → month shows unpaid again | Delete non-existent payment |
| 147 | Download fee receipt (PDF) | 🔴 | Click download → PDF generated and downloaded | Transaction with missing data |
| 148 | Fee expiry alerts appear in dashboard | 🟡 | Student with expired fee → alert shown | No expired fees |
| 149 | Dismiss fee expiry alert | 🟢 | Click dismiss → alert gone for this teacher | Dismiss same alert twice |
| 150 | Fees Record (accounting history) page loads | 🟡 | Open `/teacher/fees-record/` → all transactions listed | Thousands of transactions |
| 151 | Bulk delete fees records | 🟢 | Select multiple → delete → removed | Select 0 then bulk delete |

## 5.6 — Complaints Management
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 152 | Complaints tab shows all student complaints | 🔴 | All complaints listed with status, subject | No complaints |
| 153 | Update complaint status (pending → in progress → resolved) | 🔴 | Change status → student notified | Skip status (pending → resolved) |
| 154 | Delete complaint permanently | 🟡 | Delete → removed from list | Delete already-deleted ID |
| 155 | Complaint rating visible after student rates | 🟢 | Student rates → teacher sees star rating | Rating of 0 displayed |

## 5.7 — Courses Management
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 156 | Teacher courses list loads | 🔴 | Open `/teacher/courses/` → all courses listed | No courses |
| 157 | Add new course manually | 🔴 | Fill form → add → appears in list | Blank title submitted |
| 158 | Edit existing course | 🟡 | Edit description/thumbnail → save → updated | Edit with no changes |
| 159 | Toggle course active/inactive | 🟡 | Click toggle → status changes → students can/can't see | Toggle inactive already-inactive |
| 160 | Delete course | 🟡 | Delete → gone from list, students can't access | Delete course with active students |
| 161 | Sync courses from YouTube playlist | 🔴 | Enter playlist ID → fetch → import videos | Invalid playlist ID |
| 162 | YouTube fetch playlists API works | 🟡 | Connect YT account → playlists listed | No YouTube API key set |
| 163 | Import playlist creates course with videos | 🔴 | Import → course created with all video materials | Playlist with 100+ videos |
| 164 | Create custom course (non-YouTube) | 🟡 | Add course without playlist → materials added manually | |
| 165 | Add study material to course | 🔴 | Upload PDF/video/link → appears in course materials | Upload 50MB file |
| 166 | Edit study material | 🟡 | Change title/file → updated | Blank title |
| 167 | Delete study material | 🟡 | Delete → gone from course | Delete material students have downloaded |
| 168 | Toggle material privacy (public/private) | 🟡 | Toggle → guests can/can't download | Toggle repeatedly |
| 169 | Bulk update materials (order/visibility) | 🟢 | Reorder materials → saved correctly | |
| 170 | Course preview page works | 🟢 | Open preview → looks correct as student would see | |

## 5.8 — Broadcast Messages
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 171 | Send broadcast to all students | 🔴 | Write message → send → all students get notification | No students in system |
| 172 | Send broadcast with attachment | 🟡 | Attach file → sends → visible in banner | Large attachment file |
| 173 | Send broadcast to specific group (library/coaching) | 🟡 | Select group → send → only that group notified | Group with 0 students |
| 174 | Save broadcast as draft | 🟢 | Save draft → appears in drafts list | Save empty draft |
| 175 | Resend failed broadcast | 🟢 | Failed broadcast → resend → now delivered | Resend already-delivered |
| 176 | Delete individual broadcast | 🟡 | Delete → gone from history | |
| 177 | Bulk delete broadcasts | 🟢 | Select multiple → delete all | |
| 178 | Broadcast history page loads | 🟡 | Open `/teacher/broadcast/history/` → all history shown | |
| 179 | Student banner dismissal works (student side) | 🟡 | Student dismisses banner → doesn't reappear | Dismiss already-dismissed |

## 5.9 — Student Progress
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 180 | Student progress page loads | 🟡 | Open → batches, students, scores shown | No performance records |
| 181 | Add performance record (test result) | 🟡 | Add batch/topic/total marks → saved | Duplicate topic in same batch |
| 182 | Enter student scores for a record | 🟡 | Enter marks for each student → saved | Enter marks > total marks |
| 183 | Progress display correct (student view) | 🟢 | Student sees their own score history | No scores for student |

## 5.10 — Visitor Insights
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 184 | Visitor insights page loads | 🟢 | Open → visitor intent list shown | No visitor records |
| 185 | Delete selected visitor intents | 🟢 | Select → delete → removed | Delete 0 selected |
| 186 | Clear all visitor intents | 🟢 | Clear all → empty list | Clear already-empty list |

## 5.11 — Achievement Requests (Teacher Side)
| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 187 | Achievement requests tab shows pending achievements | 🔴 | Pending achievements listed with photo/details | No pending achievements |
| 188 | Approve achievement | 🔴 | Approve → appears on Hall of Fame, alumni notified | Approve already-approved |
| 189 | Reject achievement | 🟡 | Reject → removed from tab, alumni notified | |

---

# SECTION 6 — TODO HUB

| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 190 | Todo hub loads for teacher | 🔴 | Open `/todo/` → all tasks/notes/reminders visible | No tasks at all |
| 191 | Add a basic todo task | 🔴 | Click add → enter text → saved → appears in list | Empty task text |
| 192 | Add a note | 🟡 | Add note → saved with correct category | Very long note text |
| 193 | Add a fee reminder for a student | 🟡 | Search student → add reminder → appears in list | Student not found |
| 194 | Add a task breakdown (checklist) | 🟡 | Add breakdown with sub-items → shows checklist | Empty breakdown |
| 195 | Mark task as done | 🟡 | Click checkbox → task marked done | Mark already-done task |
| 196 | Pin/unpin task | 🟢 | Pin → appears at top | Pin max tasks |
| 197 | Trash task (soft delete) | 🟡 | Trash → moves to trash bin | Trash already-trashed task |
| 198 | Recover trashed task | 🟡 | Recover → back in active list | Recover non-existent task |
| 199 | Permanently delete task | 🟡 | Permanent delete → completely gone | Delete active (not trashed) task |
| 200 | Update task (edit text/priority) | 🟡 | Edit → save → updated | Blank text on save |
| 201 | Update task metadata (priority/label) | 🟢 | Change priority → reflected in UI | |
| 202 | Bulk action on tasks (mark all done, delete all) | 🟢 | Select multiple → bulk action → applied | Select 0 then action |
| 203 | Add reminder to task | 🟢 | Set reminder time → at that time → notification fires | Past time reminder |
| 204 | Update existing reminder on task | 🟢 | Change reminder time → saved | |
| 205 | Reminder action (dismiss/snooze) | 🟢 | Reminder pops → dismiss works | |
| 206 | Search students in todo (for fee reminders) | 🟡 | Type name → live search → results shown | Search empty string |
| 207 | Learning reminder integration (from courses) | 🟢 | Set reminder in course → appears in todo | |

---

# SECTION 7 — DJANGO ADMIN (`/admin/`)

| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 208 | Admin login works | 🔴 | Login as superuser → admin panel | Wrong password |
| 209 | StudentProfile list/search/filter works | 🔴 | Search student by name or mobile | Search with special characters |
| 210 | Inline status edit works (list_editable) | 🟡 | Change status inline → save → updated | Change 20 at once |
| 211 | Seat admin list shows occupants | 🟡 | Seat list → current_occupants column correct | Shift-enabled seat |
| 212 | CourseAdmin inline materials work | 🟡 | Open course → inline study materials shown | Course with 50+ materials |
| 213 | FeeTransaction receipt download from admin | 🟢 | Download receipt from admin record | |
| 214 | Complaint admin status edit inline | 🟢 | Change status in list → save | |
| 215 | GuidyBlock admin unblock action | 🟢 | Select pair → unblock → relationship removed | |
| 216 | BroadcastMessage list + filter works | 🟢 | Filter by message_type → correct results | |
| 217 | Delete student from admin also deletes User | 🔴 | Delete StudentProfile → User account gone too | |

---

# SECTION 8 — PUSH NOTIFICATIONS & PWA

| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 218 | VAPID public key endpoint responds | 🟡 | GET `/api/vapid-public-key/` → returns key | Key not configured |
| 219 | Subscribe to push notifications | 🟡 | Grant browser permission → subscription saved in DB | Permission denied |
| 220 | Receive push notification (after broadcast) | 🟡 | Teacher sends broadcast → student gets push notification | Browser not supporting push |
| 221 | PWA installs from browser (Add to Home Screen) | 🟢 | Chrome prompts install → app installs | |
| 222 | Service worker registered correctly | 🟢 | Check DevTools → sw.js active | sw.js 404 |

---

# SECTION 9 — SYSTEM / INFRASTRUCTURE

| # | Test | Priority | Best Case | Worst Case |
|---|---|---|---|---|
| 223 | Health check endpoint works | 🟡 | GET `/healthz` → `{"status":"ok"}` | Server under load |
| 224 | Cron maintenance webhook responds | 🟡 | POST to `/api/cron/maintenance/` → maintenance tasks run | Cron called twice simultaneously |
| 225 | Scheduler runs seat reminders (send reminders before hold ends) | 🔴 | Hold expiring tomorrow → email/notification sent | Scheduler not running |
| 226 | Media files served correctly (photos, PDFs) | 🔴 | Open uploaded photo URL → file loads | File moved/deleted from server |
| 227 | `robots.txt` and `sitemap.xml` return correct content | 🟢 | GET both → valid content | |
| 228 | Email sending works (registration, OTP, notifications) | 🔴 | Trigger email → received in inbox | Email backend misconfigured |
| 229 | Engagement tracking API records events | 🟢 | Interact with course → POST to track-engagement → DB entry saved | |
| 230 | Seat interest API records visitor interest | 🟢 | Click interested on seat → record saved in VisitorIntent | Duplicate interest by same user |

---

# 🎯 TESTING ORDER RECOMMENDATION (Best Approach for Solo Dev)

## Phase 1 — Core Auth & Onboarding (Do First)
> These unblock everything else. If auth breaks, nothing works.

1. Register → Login → Logout (Tests 6-16)
2. Forgot Password OTP flow (Tests 17-20)
3. Admission Form → submit (Tests 21-29)
4. Teacher: Approve the student you just submitted (Test 122)
5. Student Dashboard loads after approval (Test 35)

## Phase 2 — Core Student Flows
> Most used by real users daily

6. Profile & password change (Tests 40-44)
7. My Seat — view, request hold, request switch (Tests 45-51)
8. Complaints — submit, rate (Tests 52-56)
9. Courses — view, download material (Tests 57-64)
10. Notifications — read, delete (Tests 65-70)

## Phase 3 — Teacher Core Actions
> Teacher actions are critical path — they affect students

11. Teacher: All tabs load (Test 118-120)
12. Teacher: View/Edit/Delete student (Tests 121-126)
13. Teacher: Holds tab — approve/deny (Tests 128-136)
14. Teacher: Seat Manager — assign, remove, lock (Tests 137-143)
15. Teacher: Fee Management (Tests 144-151)
16. Teacher: Complaints management (Tests 152-155)

## Phase 4 — Secondary Features
17. Guidy — 1-on-1 chat, guidance flow (Tests 81-103)
18. Guidy — Group chat (Tests 104-111)
19. Alumni — Achievement form, Hall of Fame (Tests 74-80)
20. Todo Hub — all task types (Tests 190-207)
21. Broadcast messages (Tests 171-179)

## Phase 5 — Edge Cases & Infrastructure
22. Push notifications (Tests 218-222)
23. Admin panel (Tests 208-217)
24. Public pages, SEO, PWA (Tests 30-34, 221-222)
25. Health checks, cron (Tests 223-230)

---

# ⚠️ HIGH-RISK AREAS TO TEST VERY CAREFULLY

| Area | Why Risky |
|---|---|
| **Profile photo update** | Must replace in ALL profiles, not just one |
| **Seat hold/switch approval** | DB state changes must be atomic — no partial updates |
| **Fee payment recording** | Must not allow duplicate month entries |
| **Student delete in admin** | Must cascade-delete the User account too |
| **Guidy back button** | Must return to correct dashboard (alumni vs student) |
| **Dual-role user flows** | Switching between student/alumni must not mix up contexts |
| **Scheduler/cron reminders** | Silent failures — if broken, nobody knows until deadline |
| **YouTube sync import** | If API quota exceeded, must fail gracefully |
| **Push notification subscription** | VAPID key mismatch causes silent failures |
| **Email OTP expiry** | Old OTPs must be invalidated after use |

---

> **TIP**: Use two browsers (Chrome + Firefox) or Chrome + Incognito to simulate two users simultaneously for chat and dual-role testing.
> 
> **TIP**: Keep Django's `runserver` console open while testing — errors and 500s will show there even if the page shows a generic error.
