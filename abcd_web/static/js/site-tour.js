/**
 * ABCD Interactive Site Tour Engine
 * Provides guided step-by-step walkthroughs across all 37 website pages.
 * Fully isolated & non-disruptive:
 * - Never blocks clicks or disables <a> tags after tour closing.
 * - Strictly preserves Guidy & complex chat layouts without altering panel states.
 * - Comprehensive multi-feature tour for Guest Page, Dashboards, and Portals.
 */

(function () {
  'use strict';

  // Master Tour Definitions for ALL 37 Website Pages
  const TOUR_CONFIGS = {
    // 1. Home Page
    'home_page': [
      {
        target: '[data-tour="navbar-logo"], .brand, .logo, .nav-logo',
        title: 'Welcome to ABCD Coaching & Library!',
        description: 'Explore our features, courses, seat availability, and student achievements from here.',
        position: 'bottom'
      },
      {
        target: '[data-tour="nav-hamburger"], #hamburgerBtn, .hamburger-icon, .hamburger',
        title: 'Quick Navigation Menu',
        description: 'Click here anytime to open the navigation drawer for quick access to all pages and services.',
        position: 'bottom'
      },
      {
        target: '[data-tour="add-yours-btn"], .add-yours-btn, a[href*="achievement"], a[href*="add"]',
        title: 'Add Yours – Share Your Story!',
        description: 'Have an achievement, fee query, or story to share? Use "Add Yours" to send your details directly to us.',
        position: 'bottom'
      },
      {
        target: '[data-tour="home-action-cards"], .action-cards, .grid-container, .features-grid',
        title: 'Explore Services & Booking',
        description: 'Check available library seats, coaching classes, fees, and resolved student complaints.',
        position: 'top'
      },
      {
        target: '[data-tour="home-hall-fame"], .hall-fame-section, .marquee-section',
        title: 'ABCD Hall of Fame',
        description: 'See our top achieving students, top rankers, and inspirational success stories.',
        position: 'top'
      },
      {
        target: 'footer, .footer, .site-footer',
        title: 'Footer & Quick Links',
        description: 'Access quick navigation links, platform services directory, contact numbers, address, and official details.',
        position: 'top'
      }
    ],

    // 2. Teacher Dashboard (Ordered Walkthrough)
    'teacher_dashboard': [
      // 1. Search & Filter
      {
        target: '[data-tour="teacher-search"], .nav-search-form, .nav-search-wrapper, #desktopSearchInput',
        title: 'Search & Filter Students',
        description: 'Search student names, mobile numbers, or filter by coaching batch or library seat instantly.',
        position: 'bottom'
      },
      // 2. Notifications Badge
      {
        target: '[data-tour="teacher-notif-bell"], #notificationBell, .abcd-notif-btn',
        title: 'Notifications & Alert Center',
        description: 'View real-time alerts and notifications for new student registrations, seat hold requests, and complaints.',
        position: 'bottom'
      },
      // 3. Sidebar items one by one (excluding Dashboard Home & Notifications)
      {
        target: '[data-tour="teacher-nav-seats"], a[href*="seat"]',
        title: 'Manage Library Seats',
        description: 'View and manage 2D live library seat availability, student seat allocations, and floor maps.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-courses"], a[href*="courses"]',
        title: 'Manage Courses & Subjects',
        description: 'Create, edit, and organize coaching subjects, upload study chapters, and manage video lectures.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-progress"], a[href*="progress"]',
        title: 'Student Progress Reports',
        description: 'Track test scores, batch performance analytics, and overall student learning growth.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-halloffame"], a[href*="hall_of_fame"]',
        title: 'ABCD\'s Hall Of Fame',
        description: 'View and feature top rankers, competitive exam achievers, and inspirational student success stories.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-broadcast"], a[onclick*="Broadcast"]',
        title: 'Broadcasts & Advertisements',
        description: 'Send instant notice alerts, SMS messages, and emails to all enrolled students or specific batches in one click.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-insights"], a[href*="visitor_insights"]',
        title: 'Visitor Insights & Traffic',
        description: 'Analyze prospective student visits, web traffic, landing page inquiries, and registration trends.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-todo"], a[href*="todo"]',
        title: 'Teacher To-Do & Task Manager',
        description: 'Organize daily teaching tasks, student fee alerts, breakdown checklists, notebooks, and study schedule reminders.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-feesrecord"], a[href*="fees_record"]',
        title: 'Complete Fees Record Directory',
        description: 'Access master fee payment ledgers, historical payment transactions, and batch-wise fee collection reports.',
        position: 'right'
      },
      {
        target: '[data-tour="teacher-nav-guidy"], a[href*="guidy"]',
        title: 'Guidy Chatting Platform',
        description: 'Connect directly with students, teachers, and alumni on Guidy, ABCD\'s encrypted private messaging platform.',
        position: 'right'
      },
      // 4. Stat Cards
      {
        target: '[data-tour="teacher-stats-overview"], .stats-grid, .stat-cards',
        title: 'Institute Overview & Stat Cards',
        description: 'Real-time summary counts of total active students, pending admission applications, achiever stories, seat hold requests, and complaints.',
        position: 'bottom'
      },
      // 5. Tabs & Tab Actions
      {
        target: '#requests-tab, [data-tab-name="requests"], .request-item, .batch-section',
        title: 'Admission Requests & Approval Actions',
        description: 'Review pending registration applications. Click "✅ Approve" to enroll the student into Coaching/Library, or "🗑 Delete" to reject the application.',
        position: 'top'
      },
      {
        target: '#achievements-tab, [data-tab-name="achievements"], .achieve-requests-list',
        title: 'Alumni Achievement Approvals',
        description: 'Review submitted alumni competitive exam selections and rank records. Click "✅ Approve" to feature them on the Hall of Fame wall!',
        position: 'top'
      },
      {
        target: '#holds-tab, [data-tab-name="holds"], .hold-requests-list',
        title: 'Hold / Switch Requests',
        description: 'Manage seat hold applications, seat switch requests, and end hold requests. Click "✅ Approve" to grant a seat hold or switch request, or "❌ Deny" to decline.',
        position: 'top'
      },
      {
        target: '.student-name-id, .student-name, .student-card',
        title: 'Student Profile & Details Edit',
        description: 'Click on any student name (e.g. Nitin Dangi) to open their complete student details page and edit information like Full Name, Mobile Number, Coaching Batch, Gender, etc.',
        position: 'top'
      },
      {
        target: '.student-actions a[href*="fee_calendar"], a.btn-success[href*="fee_calendar"]',
        title: 'Student Fees Management',
        description: 'Click the "💰 Fees" button next to any student to open their personal Fee Calendar, view historical receipts, clear pending dues, and record monthly fee payments.',
        position: 'top'
      },
      {
        target: '#complaints-tab, [data-tab-name="complaints"], .complaints-container, .complaint-card',
        title: 'Student Complaints & Resolution Desk',
        description: 'Track student facility issues or course doubt tickets. Mark them as Resolved or In Progress with official resolution notes.',
        position: 'top'
      }
    ],

    // 3. Student Dashboard
    'student_dashboard': [
      {
        target: '[data-tour="student-header"], .student-header, header',
        title: 'Student Portal Overview',
        description: 'View your profile, seat allocation, active courses, and personalized updates here.',
        position: 'bottom'
      },
      {
        target: '[data-tour="student-nav-guidy"], a[href*="guidy"]',
        title: 'Guidy Chatting Platform',
        description: 'Chat on Guidy, ABCD\'s encrypted private messaging platform, to discuss study doubts, guidance, and updates.',
        position: 'bottom'
      },
      {
        target: '[data-tour="student-nav-todo"], a[href*="todo"]',
        title: 'To-Do Hub',
        description: 'Organize your daily study goals, track assignments, and view fee reminders.',
        position: 'bottom'
      },
      {
        target: '[data-tour="student-seat-status"], .seat-card, .card, footer, .footer',
        title: 'Your Seat Status',
        description: 'Check your current reserved library seat, shift timing, and expiry details.',
        position: 'top'
      }
    ],

    // 4. Alumni Dashboard
    'alumni_dashboard': [
      {
        target: '[data-tour="alumni-header"], .alumni-header, header',
        title: 'Alumni Network Hub',
        description: 'Welcome back! Stay connected with current students, showcase your career success, and inspire others.',
        position: 'bottom'
      },
      {
        target: '[data-tour="alumni-profile-card"], .profile-card, .card, footer, .footer',
        title: 'Your Alumni Profile',
        description: 'Update your current designation, company, or higher study accomplishments.',
        position: 'bottom'
      }
    ],

    // 5. Guest Page (Expanded Detailed Tour)
    'guest_page': [
      {
        target: '[data-tour="guest-header"], .guest-header, header, .nav-brand',
        title: 'Welcome to ABCD Guest Explorer Portal',
        description: 'Discover coaching programs, silent study library halls, Guidy Chatting Platform, and student features.',
        position: 'bottom'
      },
      {
        target: 'a[href*="guidy"], [data-tour="guest-guidy"], .icon-guidance, .icon-support',
        title: 'Guidy – ABCD Chatting Platform',
        description: 'ABCD\'s official end-to-end encrypted private chatting platform, just like WhatsApp. Connect with teachers and alumni.',
        position: 'bottom'
      },
      {
        target: 'a[href*="todo"], [data-tour="guest-todo"], .icon-innovative',
        title: 'To-Do Hub & Study Planner',
        description: 'Track daily revision goals, fee alerts, task breakdowns, and study notes.',
        position: 'bottom'
      },
      {
        target: 'a[href*="library-availability"], [data-tour="guest-seats"], .icon-seat',
        title: 'Live Library Seat Availability',
        description: 'Check real-time seat availability across Morning, Afternoon, Evening, and Full-Day shifts.',
        position: 'bottom'
      },
      {
        target: '[data-tour="guest-admission-btn"], a[href*="admission"], .btn-admission, .nav-link-admission',
        title: 'Apply for Online Admission',
        description: 'Fill out your online application form for coaching classes and library seat booking.',
        position: 'bottom'
      },
      {
        target: 'a[href*="achievement"], .see-all-link, .marquee-footer-buttons',
        title: 'Share Achievements & Ranks',
        description: 'Submit your competitive exam rank, job selections, or achievements to feature in the ABCD Hall of Fame.',
        position: 'top'
      },
      {
        target: '#notificationBell, .abcd-notif-btn, .notification-wrapper',
        title: 'Notifications Center',
        description: 'Receive real-time notifications on class notices, seat renewals, and exam updates.',
        position: 'bottom'
      },
      {
        target: 'a[href*="hall-of-fame"], .marquee-section, .hall-fame-section',
        title: 'ABCD Hall of Fame',
        description: 'Explore success stories, top rankers, and inspiring achievements of our students.',
        position: 'top'
      },
      {
        target: 'a[href*="resolved"], .icon-complaints',
        title: 'Public Resolved Complaints & Transparency',
        description: 'View resolved facility issues and transparency reports.',
        position: 'top'
      },
      {
        target: 'a[href*="profile"], #bnavProfile, .nav-link-profile',
        title: 'Guest Profile & Inquiry Tracking',
        description: 'Manage saved courses, view admission status, and track your inquiry details.',
        position: 'top'
      },
      {
        target: 'footer, .footer, .site-footer',
        title: 'Footer & Quick Links',
        description: 'Access quick navigation links, platform services directory, support contacts, and official institute details.',
        position: 'top'
      }
    ],

    // 6. Guidy Chatting Platform
    'guidy': [
      {
        target: '.g-side-body, #panelChats, .g-sidebar',
        title: 'Guidy Conversations & Contacts',
        description: 'ABCD\'s official end-to-end encrypted private chatting platform. View your active conversations, teachers, and student contacts here.',
        position: 'right'
      },
      {
        target: '#sideSearch, .g-sidebar-search-wrap',
        title: 'Search Chats & Contacts',
        description: 'Filter your contacts, active chats, alumni, and group channels by typing here.',
        position: 'bottom'
      },
      {
        target: '#gSidebarMenuBtn, .g-sidebar-menu-wrapper',
        title: 'Sidebar Options & Menu',
        description: 'Access your profile details, blocked contacts list, and session settings.',
        position: 'bottom'
      },
      {
        target: '.g-tabs',
        title: 'Chats, Requests & Groups',
        description: 'Switch between individual chats, mentorship guidance requests, and group channels.',
        position: 'bottom'
      },
      {
        target: '#sidebarFullscreenBtn, .g-floating-fullscreen-btn',
        title: 'Floating Fullscreen Mode',
        description: 'Click here to expand Guidy into full screen for distraction-free messaging.',
        position: 'top'
      },
      {
        target: '#sidebarFabBtn, .g-floating-add-btn',
        title: 'Start New Chat or Group',
        description: 'Click the "+" button to start a new chat, request guidance from alumni, or create a group.',
        position: 'top'
      },
      {
        target: '[data-tour="guidy-chat-area"], .g-hdr-info',
        title: 'Chat Workspace',
        description: 'Interactive chat workspace for communicating with teachers and peers with end-to-end encrypted messaging.',
        position: 'bottom'
      },
      {
        target: '[data-tour="guidy-header-actions"], .g-hdr-actions',
        title: 'In-Chat Search & Options',
        description: 'Search past message history inside this chat, view user profile, or clear chat history.',
        position: 'left'
      },
      {
        target: '[data-tour="guidy-attach-btn"], .g-attach-btn',
        title: 'Attach Photos, Videos & Files',
        description: 'Share homework photos, PDF documents, audio notes, or media files directly in chat.',
        position: 'top'
      },
      {
        target: '[data-tour="guidy-emoji-btn"], .g-emoji-btn',
        title: 'Emojis & Reactions',
        description: 'Insert emojis and quick message reactions.',
        position: 'top'
      },
      {
        target: '[data-tour="guidy-input-box"], #gInputBar',
        title: 'Rich Message Input Box',
        description: 'Type your message here when a chat is open. Supports formatting, file attachments, and instant messaging.',
        position: 'top'
      }
    ],

    // 7. To-Do Hub
    'todo': [
      {
        target: '[data-tour="todo-sidebar"], .todo-sidebar, #sidebar',
        title: 'To-Do Sidebar & Categories',
        description: 'Manage all your study tasks, fee reminders, task breakdowns, notebooks, and trash here.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-new-task-btn"], .btn-new-task, button[class*="add"]',
        title: 'Create New Item',
        description: 'Click "+ New" to add a new breakdown task, to-do item, reminder, or notebook entry.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-fees"], [data-tab="fees"]',
        title: 'To Add Fees Tab',
        description: 'Manage student fee tasks, add fee records, and track fee collection deadlines.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-breakdown"], [data-tab="breakdown"]',
        title: 'Breakdown Tasks Tab',
        description: 'Divide complex exam preparations into step-by-step milestones with deadlines and progress tracking.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-todos"], [data-tab="todos"]',
        title: 'TO-DOs Tab',
        description: 'Manage quick daily checklists and study goals.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-reminders"], [data-tab="reminders"]',
        title: 'Reminders Tab',
        description: 'Set up time-based alerts and notifications for revision schedules and tests.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-notebook"], [data-tab="notebook"]',
        title: 'Notebook Tab',
        description: 'Keep study notes, formulas, quick hints, and reference lists.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-tab-trash"], [data-tab="trash"]',
        title: 'Trash Bin',
        description: 'Deleted tasks are stored here safely. You can restore or permanently delete them.',
        position: 'right'
      },
      {
        target: '[data-tour="todo-add-btn"], #todoContextFab, .fab-btn',
        title: 'Quick Add Button',
        description: 'Use this floating button anytime for quick task creation from anywhere on the screen.',
        position: 'top'
      }
    ],

    // 8. Courses Catalogue
    'courses': [
      {
        target: '[data-tour="courses-header"], .courses-header, header',
        title: 'Coaching Courses & Programs',
        description: 'Browse all available coaching batches, foundation courses, and competitive exam preparation modules.',
        position: 'bottom'
      },
      {
        target: '[data-tour="courses-tabs"], .course-tabs, .tabs',
        title: 'Filter Courses by Tab',
        description: 'Switch between All Courses, your Favorite saved courses, and Archived courses.',
        position: 'bottom'
      },
      {
        target: '[data-tour="courses-grid"], .courses-grid, .grid, footer, .footer',
        title: 'Course Cards',
        description: 'Click on any course card to view detailed syllabus, video lectures, and study materials.',
        position: 'top'
      }
    ],

    // 9. Course Detail Page
    'course_detail': [
      {
        target: '.course-hero, .hero, header',
        title: 'Course Overview & Details',
        description: 'View full syllabus, batch timings, instructor notes, and enrolled student count.',
        position: 'bottom'
      },
      {
        target: '.enroll-btn, .action-btn, .btn-primary, footer, .footer',
        title: 'Enroll / Join Batch',
        description: 'Enroll in this course to access live classes, downloadable PDFs, and practice tests.',
        position: 'top'
      }
    ],

    // 10. Teacher Courses Management
    'teacher_courses': [
      {
        target: '[data-tour="tc-hero"], .hero, header',
        title: 'Course Management Center',
        description: 'Create, edit, and organize all coaching subjects and curriculum modules.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-create-btn"], .create-btn',
        title: 'Create New Course',
        description: 'Click here to publish a new course with custom thumbnail, description, and fee details.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-sync-yt-btn"]',
        title: 'Sync YouTube & Playlists',
        description: 'Sync YouTube videos or direct playlists to automatically generate and populate complete video courses.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-list-grid"], .courses-list, .tc-grid, footer, .footer',
        title: 'Course Directory & Chapters',
        description: 'Manage active courses, toggle student visibility, edit chapters, and upload study materials.',
        position: 'top'
      }
    ],

    // 11. Teacher Course Materials
    'teacher_course_materials': [
      {
        target: '[data-tour="material-hero"], .hero, header',
        title: 'Course Content Manager',
        description: 'Upload and organize lecture videos, PDF worksheets, and study notes for students.',
        position: 'bottom'
      },
      {
        target: '[data-tour="material-upload-card"], .upload-card, footer, .footer',
        title: 'Content Toolbar',
        description: 'Add new materials or re-order chapters using drag-and-drop.',
        position: 'bottom'
      }
    ],

    // 12. Teacher Course Preview
    'teacher_course_preview': [
      {
        target: '.preview-container, .hero, header, footer, .footer',
        title: 'Student View Preview',
        description: 'This is how your course and chapters will appear to enrolled students.',
        position: 'bottom'
      }
    ],

    // 13. Teacher Broadcast Center
    'teacher_broadcast': [
      {
        target: '[data-tour="broadcast-compose"], form, .card',
        title: 'Compose Broadcast Notice',
        description: 'Draft announcements or urgent updates for your students.',
        position: 'bottom'
      },
      {
        target: '[data-tour="broadcast-send-btn"], button[type="submit"], footer, .footer',
        title: 'Send Notice',
      }
    ],

    // 14. Teacher Seat Status Manager
    'teacher_seat_status': [
      {
        target: '.hub-mobile-header, .search-container, .hub-layout',
        title: 'Library Seat Management Hub',
        description: 'Manage live seat availability, student seating assignments, and floor layouts in real time.',
        position: 'bottom'
      },
      {
        target: '#seatSearchInput, #hubSearchWrapper, .search-input-wrapper',
        title: 'Search Students & Seats',
        description: 'Type any student name, seat number, or phone number to instantly highlight their seat in the grid.',
        position: 'bottom'
      },
      {
        target: '[data-tour="floor-dropdown"], .floor-navigation, .abcd-select-wrapper',
        title: 'Floor Navigation Dropdown',
        description: 'Switch between Ground Floor, 1st Floor, or 2nd Floor layout to manage different levels.',
        position: 'bottom'
      },
      {
        target: '.legend, .legend-item',
        title: 'Seat Status Legend',
        description: 'View color indicators for Available, Occupied, Pending Admission, Shift Occupied, On Hold, or Temporary Occupied seats.',
        position: 'right'
      },
      {
        target: '[data-tour="seat-grid-container"], .layout-container',
        title: 'Interactive Seat Layout Grid',
        description: 'Click on any seat node in the live grid to assign students, set holds, or view seat status.',
        position: 'top'
      }
    ],

    // 15. Admission Form (Field-by-Field Detailed Walkthrough)
    'admission_form': [
      {
        target: '#id_first_name, [name="first_name"]',
        title: 'First Name & Last Name',
        description: 'Enter your official first name and last name as per your school or government ID records.',
        position: 'bottom'
      },
      {
        target: '#id_sex, [name="sex"]',
        title: 'Gender Selection',
        description: 'Select your gender from the dropdown. If "Other" is chosen, a text field will appear to specify.',
        position: 'bottom'
      },
      {
        target: '#id_dob, [name="dob"]',
        title: 'Date of Birth (Wheel Picker)',
        description: 'Click here to open our interactive wheel picker modal and select your exact date of birth.',
        position: 'bottom'
      },
      {
        target: '#id_service_type, [name="service_type"]',
        title: 'Select Service (Coaching / Library)',
        description: 'Select one service at a time: choose English Coaching Classes or Library Study Hall for this admission application.',
        position: 'bottom'
      },
      {
        target: '#id_is_new_registration, [name="is_new_registration"]',
        title: 'Registration Type (Compulsory Field)',
        description: 'Compulsory Field! Select "Already Admitted" if you are already attending coaching classes or currently hold a library seat. Select "New Admission" if you are taking a coaching admission or reserving a new library seat for the first time.',
        position: 'bottom'
      },
      {
        target: '#coaching-options, #id_batch, [name="batch"]',
        title: 'Coaching Batch Selection',
        description: 'When Coaching is selected, choose your preferred class batch timing from the dropdown list.',
        position: 'bottom'
      },
      {
        target: '#library-options, #library-floor-label, .radio-button-group',
        title: 'Library Floor & Live Seat Booking',
        description: 'Select Ground Floor or 1st Floor, then click "Select Your Seat" to pick your exact desk node on the live 2D grid!',
        position: 'top'
      },
      {
        target: '#id_mobile_number, [name="mobile_number"]',
        title: 'Primary Mobile Number',
        description: 'Provide your 10-digit mobile number for official administrative contact and SMS alerts.',
        position: 'bottom'
      },
      {
        target: '#id_whatsapp_number, [name="whatsapp_number"]',
        title: 'WhatsApp Contact Number',
        description: 'Provide your active WhatsApp number for instant batch updates and notices. Tick "Same as mobile" if identical.',
        position: 'bottom'
      },
      {
        target: '#photoPreviewContainerCustom, [for="id_photo"]',
        title: 'Profile Photo Upload (Optional)',
        description: 'Click the camera icon to upload a passport-size photo for your digital student ID card.',
        position: 'top'
      },
      {
        target: '#id_email, [name="email"]',
        title: 'Email Address (Optional)',
        description: 'Enter your email address to receive digital fee receipts and online confirmation copies.',
        position: 'bottom'
      },
      {
        target: '#id_confirmation, [name="confirmation"]',
        title: 'Terms & Information Confirmation',
        description: 'Tick this box to confirm all provided information is accurate and agree to campus rules.',
        position: 'top'
      },
      {
        target: '#submitBtn, .submit-btn',
        title: 'Submit Application',
        description: 'Click Submit Application to complete your registration! You will receive instant confirmation.',
        position: 'top'
      }
    ],

    // 16. Student Complaints
    'student_complaints': [
      {
        target: '.complaint-container, .card, form, footer, .footer',
        title: 'Submit & Track Complaints',
        description: 'Lodge issues or request assistance regarding facilities, fees, or study environment.',
        position: 'bottom'
      }
    ],

    'student_complaint_rate': [
      {
        target: 'form, .card, footer, .footer',
        title: 'Rate Complaint Resolution',
        description: 'Give feedback on how quickly and satisfactorily your issue was resolved.',
        position: 'bottom'
      }
    ],

    'student_complaint_success': [
      {
        target: '.success-card, .card, footer, .footer',
        title: 'Complaint Submitted Successfully',
        description: 'Your complaint token has been registered. You will receive notifications on progress.',
        position: 'bottom'
      }
    ],

    'resolved_complaints_public': [
      {
        target: '.complaints-list, .grid, .card, footer, .footer',
        title: 'Public Resolved Complaints',
        description: 'Browse past resolved student complaints and transparency reports.',
        position: 'bottom'
      }
    ],

    // 17. Fee Calendar & Fee Record
    'fee_calendar': [
      {
        target: '.calendar-container, .fee-calendar, .card, footer, .footer',
        title: 'Fee Due Calendar',
        description: 'Visual calendar highlighting payment due dates, upcoming renewals, and paid months.',
        position: 'bottom'
      }
    ],

    'fees_record': [
      {
        target: '.record-header-section, .fees-record-container',
        title: 'Fee Record & Accounting Log',
        description: 'View, track, and manage all digitally generated fee receipts and historical student payment logs.',
        position: 'bottom'
      },
      {
        target: '#feesSearch, .search-input-container',
        title: 'Live Receipt & Student Search',
        description: 'Type here to search receipt numbers, student names, mobile numbers, or dates instantly.',
        position: 'bottom'
      },
      {
        target: '#toggleSelectBtn, .selection-controls',
        title: 'Select & Bulk Actions',
        description: 'Toggle selection mode to select multiple fee records for bulk management or deletion.',
        position: 'bottom'
      },
      {
        target: '.dashboard-table-card, .fees-table-layout',
        title: 'Receipts History & Details',
        description: 'Inspect verified transactions, payment methods, student details, and download official fee receipts.',
        position: 'top'
      }
    ],

    // 18. Hall of Fame & Achievements
    'hall_of_fame': [
      {
        target: '.hall-of-fame-container, .achievements-section, .hero, footer, .footer',
        title: 'ABCD Hall of Fame',
        description: 'Celebrating top rankers, competitive exam toppers, and student success achievements.',
        position: 'bottom'
      }
    ],

    // 18. Achievement Form (Field-by-Field Detailed Walkthrough)
    'achievement_form': [
      {
        target: '#id_first_name, [name="first_name"]',
        title: 'First Name & Last Name',
        description: 'Enter your first name and last name for official credit on our ABCD Hall of Fame wall.',
        position: 'bottom'
      },
      {
        target: '#id_gender, [name="gender"]',
        title: 'Gender & Birth Date',
        description: 'Select your gender and tap Date of Birth to launch our smooth wheel picker modal.',
        position: 'bottom'
      },
      {
        target: '#id_about_yourself, [name="about_yourself"]',
        title: 'Personal Bio & Positive Qualities',
        description: 'Share a short inspiring quote or personal strength that kept you motivated during your preparation.',
        position: 'bottom'
      },
      {
        target: '#id_current_post, [name="current_post"]',
        title: 'Current Post / Designation',
        description: 'Specify your current job post or designation (e.g., Inspector, Sub-Inspector, Bank PO, Officer).',
        position: 'bottom'
      },
      {
        target: '#id_short_achievement, [name="short_achievement"]',
        title: 'Brief Achievement Title',
        description: 'Enter a short summary title for your achievement (e.g., Selected in SSC CGL 2023).',
        position: 'bottom'
      },
      {
        target: '#id_selection_year, [name="selection_year"]',
        title: 'Selection Year & Working City',
        description: 'Click Selection Year to open the year picker, and enter the city where you are currently posted.',
        position: 'bottom'
      },
      {
        target: '#id_services_used, [name="services_used"]',
        title: 'ABCD Services Used',
        description: 'Select which services you utilized during your study period at ABCD (Coaching / Library / Both).',
        position: 'bottom'
      },
      {
        target: '#duration_display, #id_duration_years',
        title: 'Time Spent at ABCD',
        description: 'Click here to record the total duration (months/years) you spent preparing at ABCD.',
        position: 'bottom'
      },
      {
        target: '#id_experience_feedback, [name="experience_feedback"]',
        title: 'How ABCD Helped You',
        description: 'Describe how ABCD guidance, faculty, library discipline, or peer environment helped in your journey.',
        position: 'bottom'
      },
      {
        target: '#otherAchievementsList, .add-btn',
        title: 'Other Achievements (Optional)',
        description: 'Click "+ Add Another Achievement" to list any additional awards, college medals, or clearing other exams.',
        position: 'top'
      },
      {
        target: '#id_mobile_number, [name="mobile_number"]',
        title: 'Administrative Contact Details',
        description: 'Provide your mobile number, WhatsApp number, and email address for official verification.',
        position: 'bottom'
      },
      {
        target: '#photoPreviewContainerCustom, [for="id_photo"]',
        title: 'Upload Profile Photo',
        description: 'Upload a clear professional photo to be featured alongside your success story on the Hall of Fame wall!',
        position: 'top'
      },
      {
        target: '#starRating, #id_abcd_feedback, [name="abcd_feedback"]',
        title: 'Star Rating & Public Review',
        description: 'Give ABCD a star rating out of 5 and write your feedback review for future aspirants.',
        position: 'top'
      },
      {
        target: '#submitBtn, .submit-btn',
        title: 'Submit Your Story 🚀',
        description: 'Click "Submit Your Story" to publish your achievement to the ABCD Hall of Fame and inspire generations of students!',
        position: 'top'
      }
    ],

    'achievement_detail': [
      {
        target: '.achievement-card, .card, footer, .footer',
        title: 'Student Achievement Detail',
        description: 'Read the full story, rank, and exam score of this featured student.',
        position: 'bottom'
      }
    ],

    // 19. Library Availability & Seat Status
    'library_availability': [
      {
        target: '.library-container, .seat-grid, .card, footer, .footer',
        title: 'Live Library Seat Availability',
        description: 'Check real-time seat layout across Morning, Afternoon, Evening, and Full-Day shifts.',
        position: 'bottom'
      }
    ],

    'your_seat_status': [
      {
        target: '.seat-card, .card, footer, .footer',
        title: 'Your Allocated Seat Details',
        description: 'View your current reserved seat number, shift timing, and renewal information.',
        position: 'bottom'
      }
    ],

    // 20. Student Details & Profiles
    'student_details': [
      {
        target: '.student-profile-card, .card, .profile-header, footer, .footer',
        title: 'Student Profile & Academic Records',
        description: 'Inspect enrolled courses, attendance, library seat shift, and fee history.',
        position: 'bottom'
      }
    ],

    'student_details_S': [
      {
        target: '.student-card, .card, footer, .footer',
        title: 'Student Summary Details',
        description: 'Quick student overview and contact profile.',
        position: 'bottom'
      }
    ],

    'edit_student': [
      {
        target: 'form, .edit-form-container, .card, footer, .footer',
        title: 'Edit Student Information',
        description: 'Update student contact details, batch assignment, or profile photo.',
        position: 'bottom'
      }
    ],

    'edit_alumni': [
      {
        target: 'form, .edit-form-container, .card, footer, .footer',
        title: 'Edit Alumni Profile',
        description: 'Update current job title, company, exam rank, or higher education status.',
        position: 'bottom'
      }
    ],

    'student_progress': [
      {
        target: '.hero-card, .progress-wrapper',
        title: 'Student Progress Hub',
        description: 'Performance tracking, score logs, and achievement recognition system across coaching, library, and alumni.',
        position: 'bottom'
      },
      {
        target: '.filter-bar, .filter-form',
        title: 'Filter Services & Batches',
        description: 'Filter student lists by Coaching Batches, Library Floors, or Alumni Network.',
        position: 'bottom'
      },
      {
        target: 'button[onclick*="openUpdateModal"], .btn-light',
        title: 'New Performance Record',
        description: 'Publish new test scores, topic marks, and rank leaderboards for coaching batches.',
        position: 'bottom'
      },
      {
        target: '#leaderboardWrapper, .leaderboard-section',
        title: 'Interactive Test Leaderboards',
        description: 'View top scoring students, topic percentages, and slide between recent test results.',
        position: 'top'
      },
      {
        target: '#studentList, .student-list-hub',
        title: 'Student Directory & Records',
        description: 'View full student rosters, fee expiry alerts, edit student profiles, and manage progress records.',
        position: 'top'
      }
    ],

    'visitor_insights': [
      {
        target: '.insights-header-section, .visitor-insights-container',
        title: 'Visitor Analytics & Intent Hub',
        description: 'Track visitor traffic, website browsing engagement, and admission inquiries in real time.',
        position: 'bottom'
      },
      {
        target: '#insightsSearch, .search-input-container',
        title: 'Filter Visitor Activity',
        description: 'Search by visitor email, intent type, scope (general/specific seat), or resolution status.',
        position: 'bottom'
      },
      {
        target: '.btn-clear',
        title: 'Clear Old Activity Logs',
        description: 'Clean up outdated visitor logs and historical inquiry intents with one click.',
        position: 'bottom'
      },
      {
        target: '#insightsTable, .dashboard-table-card',
        title: 'Detailed Engagement Logs',
        description: 'Inspect user emails, targeted seats/floors, timestamps, and inquiry resolution status.',
        position: 'top'
      }
    ],

    'guest_profile_details': [
      {
        target: '.profile-container, .card, footer, .footer',
        title: 'Guest Profile Overview',
        description: 'View saved inquiries, bookmark courses, and check admission status.',
        position: 'bottom'
      }
    ],

    'register': [
      {
        target: 'form, .register-card, .card, footer, .footer',
        title: 'Create an Account',
        description: 'Register for a new student or guest account to access coaching and library booking.',
        position: 'bottom'
      }
    ],

    // 21. Services, About Us & Contact
    'contact': [
      {
        target: '.contact-container, form, .card, footer, .footer',
        title: 'Get in Touch',
        description: 'Contact us via phone, WhatsApp, email, or send us a quick inquiry message.',
        position: 'bottom'
      }
    ]
  };

  class ABCDTourEngine {
    constructor() {
      this.currentTourKey = null;
      this.steps = [];
      this.currentIndex = 0;
      this.overlay = null;
      this.spotlight = null;
      this.popover = null;
      this.activeTarget = null;
      this.isStarted = false;

      this.boundResizeHandler = this.updatePosition.bind(this);
    }

    init() {
      const pageKey = this.detectPageKey();
      if (!pageKey || !TOUR_CONFIGS[pageKey]) {
        const launcher = document.querySelector('.abcd-tour-launcher');
        if (launcher) launcher.remove();
        return;
      }

      this.currentTourKey = pageKey;
      this.steps = TOUR_CONFIGS[pageKey];

      // Inject floating launcher button
      this.createLauncher();

      // Auto start tour cards after 5 seconds ONLY if user has NEVER completed or dismissed them
      const userIdent = document.body.dataset.username || 'user';
      const userKey = this.getUserStorageKey(pageKey);

      const isCompleted = (localStorage.getItem(userKey) === 'true') ||
                          (localStorage.getItem(`abcd_tour_done_${pageKey}`) === 'true') ||
                          (localStorage.getItem(`abcd_tour_done_global_${pageKey}_${userIdent}`) === 'true') ||
                          (localStorage.getItem(`abcd_tour_dismissed_${pageKey}_${userIdent}`) === 'true') ||
                          (localStorage.getItem(`abcd_tour_seen_${pageKey}`) === 'true');

      if (isCompleted) {
        return;
      }

      setTimeout(() => {
        this.start(false);
      }, 5000);
    }

    detectPageKey() {
      const path = window.location.pathname.toLowerCase();

      // Explicitly suppress site tour and launcher button on Contact & Profile pages
      if (path.includes('/contact') || path.includes('/profile') || path.includes('/my-details') || path.includes('/student/details')) return null;
      if (path.includes('/services') || path.includes('/about')) return null;

      if (path.includes('/alumni/dashboard')) return 'alumni_dashboard';
      if (path.includes('/alumni/edit')) return 'edit_alumni';
      if (path.includes('/guest-home')) return 'guest_page';
      if (path.includes('/guest/profile')) return 'guest_profile_details';

      if (path.includes('/teacher/courses/') && path.includes('/materials')) return 'teacher_course_materials';
      if (path.includes('/teacher/courses/') && path.includes('/preview')) return 'teacher_course_preview';
      if (path.includes('/teacher/courses')) return 'teacher_courses';
      if (path.includes('/teacher/broadcast')) return 'teacher_broadcast';
      if (path.includes('/teacher/seat-status') || path.includes('/teacher/seat-manager')) return 'teacher_seat_status';
      if (path.includes('/teacher/fees-record')) return 'fees_record';
      if (path.includes('/teacher/progress')) return 'student_progress';
      if (path.includes('/teacher/visitor-insights')) return 'visitor_insights';
      if (path.includes('/teacher/student/edit')) return 'edit_student';
      if (path.includes('/teacher/student/')) return 'student_details';
      if (path.includes('/teacher')) return 'teacher_dashboard';

      if (path === '/' || path.endsWith('/home/') || path.includes('home_page')) return 'home_page';
      if (path.includes('/dashboard')) return 'student_dashboard';

      if (path.includes('/guidy')) return 'guidy';
      if (path.includes('/todo')) return 'todo';
      if (path.includes('/admission-form')) return 'admission_form';
      if (path.includes('/complaints/resolved')) return 'resolved_complaints_public';
      if (path.includes('/complaints/rate')) return 'student_complaint_rate';
      if (path.includes('/complaints/success')) return 'student_complaint_success';
      if (path.includes('/complaints')) return 'student_complaints';
      if (path.includes('/fee/calendar') || path.includes('/fees/')) return 'fee_calendar';
      if (path.includes('/hall-of-fame')) return 'hall_of_fame';
      if (path.includes('/achievement/add') || path.includes('/achievement/create')) return 'achievement_form';
      if (path.includes('/achievement/')) return 'achievement_detail';
      if (path.includes('/achievement')) return 'achievement_form';
      if (path.includes('/courses/') && !path.endsWith('/courses/')) return 'course_detail';
      if (path.includes('/courses')) return 'courses';
      if (path.includes('/contact') || path.includes('/profile') || path.includes('/my-details')) return null;
      if (path.includes('/library-availability')) return 'library_availability';
      if (path.includes('/my-seat')) return 'your_seat_status';
      if (path.includes('/student/details-s')) return null;
      if (path.includes('/student/details')) return null;
      if (path.includes('/register')) return 'register';

      if (document.body.dataset.pageKey) {
        return document.body.dataset.pageKey;
      }

      return null;
    }

    getUserStorageKey(pageKey) {
      const userIdent = document.body.dataset.username || 'user';
      return `abcd_tour_card_seen_v20_${pageKey}_${userIdent}`;
    }

    start(force = false) {
      if (this.isStarted) return;
      if (!this.steps || this.steps.length === 0) return;

      let stepsToUse = [...this.steps];

      // Dynamic filtering for admission_form based on selected service
      if (this.currentTourKey === 'admission_form') {
        const serviceSelect = document.getElementById('id_service_type') || document.querySelector('[name="service_type"]');
        const selectedVal = (serviceSelect ? serviceSelect.value : '').toLowerCase().trim();

        if (selectedVal === 'coaching') {
          stepsToUse = stepsToUse.filter(s => !s.target.includes('#library-options'));
        } else if (selectedVal === 'library') {
          stepsToUse = stepsToUse.filter(s => !s.target.includes('#coaching-options'));
        }
      }

      const validSteps = [];
      for (const s of stepsToUse) {
        let tempShown = null;
        if (this.currentTourKey === 'admission_form') {
          if (s.target.includes('#coaching-options')) {
            const coachingElem = document.getElementById('coaching-options');
            if (coachingElem && window.getComputedStyle(coachingElem).display === 'none') {
              coachingElem.style.display = 'block';
              tempShown = coachingElem;
            }
          } else if (s.target.includes('#library-options')) {
            const libraryElem = document.getElementById('library-options');
            if (libraryElem && window.getComputedStyle(libraryElem).display === 'none') {
              libraryElem.style.display = 'block';
              tempShown = libraryElem;
            }
          }
        }

        const target = this.resolveTarget(s);

        if (tempShown) {
          tempShown.style.display = '';
        }

        if (target) {
          validSteps.push(s);
        }
      }

      if (validSteps.length === 0) {
        console.log('[ABCDTour] No target elements present on screen for tour.');
        return;
      }

      this.validSteps = validSteps;
      this.currentIndex = 0;
      this.isStarted = true;

      this.buildUI();
      window.addEventListener('resize', this.boundResizeHandler);
      window.addEventListener('scroll', this.boundResizeHandler, { passive: true });

      this.showStep(0);
    }

    buildUI() {
      if (!this.overlay) {
        this.overlay = document.createElement('div');
        this.overlay.className = 'abcd-tour-overlay';
        document.body.appendChild(this.overlay);
      }

      if (!this.spotlight) {
        this.spotlight = document.createElement('div');
        this.spotlight.className = 'abcd-tour-spotlight';
        document.body.appendChild(this.spotlight);
      }

      if (!this.popover) {
        this.popover = document.createElement('div');
        this.popover.className = 'abcd-tour-popover';
        this.popover.innerHTML = `
          <div class="abcd-tour-arrow"></div>
          <div class="abcd-tour-header">
            <span class="abcd-tour-badge"><i class="bx bx-compass"></i> Feature Tour</span>
            <button class="abcd-tour-close-icon" title="Close Tour">&times;</button>
          </div>
          <h4 class="abcd-tour-title"></h4>
          <p class="abcd-tour-description"></p>
          <div class="abcd-tour-footer">
            <span class="abcd-tour-steps-count">Step 1 of 5</span>
            <div class="abcd-tour-controls">
              <button class="abcd-tour-btn abcd-tour-btn-skip">Skip</button>
              <button class="abcd-tour-btn abcd-tour-btn-prev"><i class="bx bx-chevron-left"></i> Back</button>
              <button class="abcd-tour-btn abcd-tour-btn-next">Next <i class="bx bx-chevron-right"></i></button>
            </div>
          </div>
        `;
        document.body.appendChild(this.popover);

        this.popover.querySelector('.abcd-tour-close-icon').addEventListener('click', () => this.stop(true));
        this.popover.querySelector('.abcd-tour-btn-skip').addEventListener('click', () => this.stop(true));
        this.popover.querySelector('.abcd-tour-btn-prev').addEventListener('click', () => this.prev());
        this.popover.querySelector('.abcd-tour-btn-next').addEventListener('click', () => this.next());
      }
    }

    resolveTarget(step) {
      if (!step || !step.target) return null;

      const selectors = step.target.split(',').map(s => s.trim());

      for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          const style = window.getComputedStyle(el);
          const isVisible = style.display !== 'none' && style.visibility !== 'hidden';
          const rect = el.getBoundingClientRect();
          const isInsideDrawer = !!el.closest('.hub-sidebar, #hubSidebar, .sidebar-wrapper, #sidebar, #mobileNav, #guestMobileNav');
          if (isVisible && (rect.width > 0 || rect.height > 0 || isInsideDrawer)) {
            return el;
          }
          // Handle custom select dropdowns where native <select> or <input> is hidden by JS
          if (!isVisible && (el.tagName === 'SELECT' || el.tagName === 'INPUT')) {
            const customWrap = el.nextElementSibling && el.nextElementSibling.classList.contains('abcd-select-wrapper')
              ? el.nextElementSibling
              : el.closest('.abcd-select-wrapper, .form-group');
            if (customWrap) {
              const wrapStyle = window.getComputedStyle(customWrap);
              if (wrapStyle.display !== 'none' && wrapStyle.visibility !== 'hidden') {
                return customWrap;
              }
            }
          }
        }
      }

      for (const sel of selectors) {
        const candidates = document.querySelectorAll(
          `.mobile-nav ${sel}, #guestMobileNav ${sel}, #mobileNav ${sel}, .sidebar-wrapper ${sel}, .nav-sidebar ${sel}, .bottom-nav-menu ${sel}, .guest-bottom-nav ${sel}, ${sel}`
        );
        for (const cand of candidates) {
          if (cand) {
            return cand;
          }
        }
      }

      return document.querySelector(step.target);
    }

    async handleDrawerState(targetElem) {
      if (!targetElem) return;

      // DO NOT mess with Guidy chat panels or layout on /guidy/ page!
      const path = window.location.pathname.toLowerCase();
      if (path.includes('/guidy') || targetElem.closest('.g-layout, .g-side-body, .g-sidebar, .g-chat-area')) {
        return;
      }

      // Strictly check for true navigation drawer containers
      const sidebarContainer = targetElem.closest(
        '.sidebar-wrapper, #sidebarWrapper, #sidebar, .nav-sidebar, #mobileNav, #guestMobileNav, #hubSidebar, .hub-sidebar'
      );
      const isInsideSidebar = !!sidebarContainer;

      const sidebar = document.getElementById('hubSidebar') ||
                      document.getElementById('sidebar') ||
                      document.getElementById('mobileNav') ||
                      document.getElementById('guestMobileNav') ||
                      document.querySelector('.nav-sidebar, .sidebar-wrapper, #sidebarWrapper, .hub-sidebar');

      const overlay = document.getElementById('sidebarOverlay') ||
                      document.getElementById('mobileNavOverlay') ||
                      document.querySelector('.sidebar-overlay');

      const hamburgerBtn = document.getElementById('sidebarToggleBtn') ||
                           document.getElementById('hamburgerBtn') ||
                           document.querySelector('[data-tour="nav-hamburger"], .hamburger-icon, #mobileNavToggle, .sidebar-toggle-btn');

      if (isInsideSidebar) {
        const hubSidebar = document.getElementById('hubSidebar') || document.querySelector('.hub-sidebar');
        if (hubSidebar) hubSidebar.classList.add('active');
        if (sidebarContainer) sidebarContainer.classList.add('active', 'open');
        if (sidebar) sidebar.classList.add('active', 'open');
        if (overlay) overlay.classList.add('active', 'open');
        if (hamburgerBtn) {
          hamburgerBtn.classList.add('open', 'active');
        }
        await new Promise(resolve => setTimeout(resolve, 450));
      } else {
        const hubSidebar = document.getElementById('hubSidebar') || document.querySelector('.hub-sidebar');
        if (hubSidebar) hubSidebar.classList.remove('active');
        const isSidebarOpen = (sidebar && (sidebar.classList.contains('active') || sidebar.classList.contains('open'))) ||
                              (sidebarContainer && (sidebarContainer.classList.contains('active') || sidebarContainer.classList.contains('open')));

        if (isSidebarOpen) {
          if (sidebar) sidebar.classList.remove('active', 'open');
          if (sidebarContainer) sidebarContainer.classList.remove('active', 'open');
          if (overlay) overlay.classList.remove('active', 'open');
          if (hamburgerBtn) {
            hamburgerBtn.classList.remove('open', 'active');
          }
          await new Promise(resolve => setTimeout(resolve, 250));
        }
      }
    }

    async showStep(index) {
      if (index < 0 || index >= this.validSteps.length) {
        this.stop(true);
        return;
      }

      this.currentIndex = index;
      const step = this.validSteps[index];

      // Reset temporary display overrides from previous steps for admission_form
      if (this.currentTourKey === 'admission_form') {
        const coachingElem = document.getElementById('coaching-options');
        const libraryElem = document.getElementById('library-options');
        if (coachingElem && !coachingElem.classList.contains('show')) coachingElem.style.display = '';
        if (libraryElem && !libraryElem.classList.contains('show')) libraryElem.style.display = '';

        if (step.target.includes('#coaching-options') && coachingElem) {
          coachingElem.style.display = 'block';
        } else if (step.target.includes('#library-options') && libraryElem) {
          libraryElem.style.display = 'block';
        }
      }
      // Dynamic tab activation for teacher_dashboard
      if (this.currentTourKey === 'teacher_dashboard') {
        let tabToClick = null;
        if (step.target.includes('requests') && !step.target.includes('achievements') && !step.target.includes('holds')) {
          tabToClick = document.querySelector('[data-tab-name="requests"]');
        } else if (step.target.includes('achievements')) {
          tabToClick = document.querySelector('[data-tab-name="achievements"]');
        } else if (step.target.includes('holds')) {
          tabToClick = document.querySelector('[data-tab-name="holds"]');
        } else if (step.target.includes('complaints')) {
          tabToClick = document.querySelector('[data-tab-name="complaints"]');
        } else if (step.target.includes('student-name') || step.target.includes('fee_calendar')) {
          const activeTabContent = document.querySelector('.tab-content.active');
          if (!activeTabContent || (!activeTabContent.id.includes('coaching') && !activeTabContent.id.includes('library'))) {
            tabToClick = document.querySelector('[data-tab-name="coaching"]') || document.querySelector('[data-tab-name="library"]');
          }
        }
        if (tabToClick) {
          tabToClick.click();
        }
      }

      const targetElem = this.resolveTarget(step);

      if (!targetElem) {
        this.next();
        return;
      }

      await this.handleDrawerState(targetElem);

      targetElem.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      await new Promise(resolve => setTimeout(resolve, 400));

      const style = window.getComputedStyle(targetElem);
      const rect = targetElem.getBoundingClientRect();

      if (style.display === 'none' || style.visibility === 'hidden') {
        console.warn('[ABCDTour] Skipping unrendered target:', step.target);
        this.next();
        return;
      }

      if (this.activeTarget) {
        this.activeTarget.classList.remove('abcd-tour-target-active');
      }
      this.activeTarget = targetElem;
      this.activeTarget.classList.add('abcd-tour-target-active');

      this.popover.querySelector('.abcd-tour-title').textContent = step.title;
      this.popover.querySelector('.abcd-tour-description').textContent = step.description;
      this.popover.querySelector('.abcd-tour-steps-count').textContent = `Step ${index + 1} of ${this.validSteps.length}`;

      const prevBtn = this.popover.querySelector('.abcd-tour-btn-prev');
      const nextBtn = this.popover.querySelector('.abcd-tour-btn-next');

      prevBtn.disabled = (index === 0);

      if (index === this.validSteps.length - 1) {
        nextBtn.textContent = 'Finish ✓';
        nextBtn.className = 'abcd-tour-btn abcd-tour-btn-finish';
      } else {
        nextBtn.innerHTML = 'Next <i class="bx bx-chevron-right"></i>';
        nextBtn.className = 'abcd-tour-btn abcd-tour-btn-next';
      }

      setTimeout(() => {
        this.updatePosition();
        this.popover.classList.add('abcd-tour-visible');
      }, 100);
    }

    updatePosition() {
      if (!this.isStarted || !this.activeTarget) return;

      const rect = this.activeTarget.getBoundingClientRect();

      if (rect.width === 0 || rect.height === 0 || rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight) {
        this.spotlight.style.opacity = '0';
        return;
      } else {
        this.spotlight.style.opacity = '1';
      }

      const padding = 6;

      this.spotlight.style.top = `${rect.top - padding}px`;
      this.spotlight.style.left = `${rect.left - padding}px`;
      this.spotlight.style.width = `${rect.width + (padding * 2)}px`;
      this.spotlight.style.height = `${rect.height + (padding * 2)}px`;

      const popoverRect = this.popover.getBoundingClientRect();
      const step = this.validSteps[this.currentIndex];
      let pos = step.position || 'bottom';

      let top = 0;
      let left = 0;

      const spaceBottom = window.innerHeight - rect.bottom;
      const spaceTop = rect.top;
      const spaceRight = window.innerWidth - rect.right;
      const spaceLeft = rect.left;

      const isInsideSidebarDrawer = !!this.activeTarget.closest('#sidebar, #mobileNav, #guestMobileNav, .sidebar-wrapper, .nav-sidebar, #hubSidebar, .hub-sidebar');

      if (isInsideSidebarDrawer || window.innerWidth <= 768) {
        if (spaceBottom < popoverRect.height + 15 && spaceTop > popoverRect.height + 15) {
          pos = 'top';
        } else {
          pos = 'bottom';
        }
      } else {
        if (pos === 'bottom' && spaceBottom < popoverRect.height + 15 && spaceTop > popoverRect.height + 15) {
          pos = 'top';
        } else if (pos === 'top' && spaceTop < popoverRect.height + 15 && spaceBottom > popoverRect.height + 15) {
          pos = 'bottom';
        } else if ((pos === 'right' || pos === 'left') && spaceRight < popoverRect.width + 15 && spaceLeft > popoverRect.width + 15) {
          pos = 'left';
        } else if ((pos === 'right' || pos === 'left') && spaceLeft < popoverRect.width + 15 && spaceRight > popoverRect.width + 15) {
          pos = 'right';
        }
      }

      if (pos === 'top') {
        top = rect.top - popoverRect.height - 12;
        left = rect.left + (rect.width / 2) - (popoverRect.width / 2);
      } else if (pos === 'bottom') {
        top = rect.bottom + 12;
        left = rect.left + (rect.width / 2) - (popoverRect.width / 2);
      } else if (pos === 'left') {
        top = rect.top + (rect.height / 2) - (popoverRect.height / 2);
        left = rect.left - popoverRect.width - 12;
      } else if (pos === 'right') {
        top = rect.top + (rect.height / 2) - (popoverRect.height / 2);
        left = rect.right + 12;
      }

      left = Math.max(16, Math.min(left, window.innerWidth - popoverRect.width - 16));
      top = Math.max(16, Math.min(top, window.innerHeight - popoverRect.height - 16));

      this.popover.setAttribute('data-position', pos);
      this.popover.style.top = `${top}px`;
      this.popover.style.left = `${left}px`;
    }

    next() {
      if (this.currentIndex < this.validSteps.length - 1) {
        this.showStep(this.currentIndex + 1);
      } else {
        this.stop(true);
      }
    }

    prev() {
      if (this.currentIndex > 0) {
        this.showStep(this.currentIndex - 1);
      }
    }

    stop(markCompleted = true) {
      if (!this.isStarted) return;

      this.isStarted = false;

      // Clean up target active classes & position overrides across document
      document.querySelectorAll('.abcd-tour-target-active').forEach(el => {
        el.classList.remove('abcd-tour-target-active');
        if (el._originalPositionWasStatic) {
          el.style.position = '';
          delete el._originalPositionWasStatic;
        }
      });

      if (this.currentTourKey === 'admission_form') {
        const coachingElem = document.getElementById('coaching-options');
        const libraryElem = document.getElementById('library-options');
        if (coachingElem && !coachingElem.classList.contains('show')) coachingElem.style.display = '';
        if (libraryElem && !libraryElem.classList.contains('show')) libraryElem.style.display = '';
      }

      if (this.popover) {
        this.popover.classList.remove('abcd-tour-visible');
        this.popover.remove();
        this.popover = null;
      }

      if (this.overlay) {
        this.overlay.remove();
        this.overlay = null;
      }

      if (this.spotlight) {
        this.spotlight.remove();
        this.spotlight = null;
      }

      this.activeTarget = null;

      window.removeEventListener('resize', this.boundResizeHandler);
      window.removeEventListener('scroll', this.boundResizeHandler);

      if (markCompleted && this.currentTourKey) {
        const userIdent = document.body.dataset.username || 'user';
        const userKey = this.getUserStorageKey(this.currentTourKey);
        localStorage.setItem(userKey, 'true');
        localStorage.setItem(`abcd_tour_done_${this.currentTourKey}`, 'true');
        localStorage.setItem(`abcd_tour_done_global_${this.currentTourKey}_${userIdent}`, 'true');
        localStorage.setItem(`abcd_tour_dismissed_${this.currentTourKey}_${userIdent}`, 'true');
        localStorage.setItem(`abcd_tour_seen_${this.currentTourKey}`, 'true');
      }
    }

    createLauncher() {
      // 1. Check if tour launcher link already exists in sidebar
      const existingBtns = document.querySelectorAll('.sidebar-tour-btn, [data-action="start-tour"], #sidebarTourBtn');
      if (existingBtns.length > 0) {
        existingBtns.forEach(btn => {
          if (!btn._hasTourListener) {
            btn._hasTourListener = true;
            btn.addEventListener('click', (e) => {
              e.preventDefault();
              const sidebar = document.getElementById('sidebar') || document.querySelector('.nav-sidebar');
              if (sidebar && sidebar.classList.contains('active') && typeof toggleSidebar === 'function') {
                toggleSidebar();
              }
              this.start(true);
            });
          }
        });
        return;
      }

      // 2. If not yet in DOM, check for sidebar and dynamically insert before logout/signin button
      const sidebar = document.getElementById('sidebar') || document.querySelector('.nav-sidebar');
      if (sidebar) {
        if (sidebar.querySelector('.sidebar-tour-item, .sidebar-tour-btn')) return;

        const tourLi = document.createElement('li');
        tourLi.className = 'sidebar-tour-item';
        tourLi.innerHTML = `
          <a href="javascript:void(0)" class="sidebar-tour-btn">
            <i class='bx bx-compass' style="color:#0284c7;"></i>
            <span>Take Tour</span>
          </a>
        `;
        const link = tourLi.querySelector('a');
        link.addEventListener('click', (e) => {
          e.preventDefault();
          if (sidebar.classList.contains('active') && typeof toggleSidebar === 'function') {
            toggleSidebar();
          }
          this.start(true);
        });

        const logoutItem = sidebar.querySelector('.sidebar-logout-item, .sidebar-signin-item');
        if (logoutItem) {
          sidebar.insertBefore(tourLi, logoutItem);
        } else {
          sidebar.appendChild(tourLi);
        }
      }
    }
  }

  // Global instance exposure
  window.ABCDTour = new ABCDTourEngine();

  // Helper trigger function
  window.startABCDTour = function (force = true) {
    if (window.ABCDTour) {
      window.ABCDTour.start(force);
    }
  };

  // Auto initialize on DOMReady
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.ABCDTour.init());
  } else {
    window.ABCDTour.init();
  }
})();
