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

  // Strict Home Base Pages Set - ONLY these 5 pages are permitted to introduce the Footer
  const HOME_BASE_PAGES = new Set([
    'home_page',
    'guest_page',
    'student_dashboard',
    'teacher_dashboard',
    'alumni_dashboard'
  ]);

  // Master Tour Definitions for ALL 37 Website Pages
  const TOUR_CONFIGS = {
    // 1. Home Page (Home Base Page - Includes Footer)
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

    // 2. Teacher Dashboard (Home Base Page - Includes Footer)
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
      },
      // 19. Footer (Home Base Page)
      {
        target: 'footer, .footer, .site-footer',
        title: 'Footer & Quick Links',
        description: 'Access quick navigation links, platform services directory, contact numbers, address, and official details.',
        position: 'top'
      }
    ],

    // 3. Student Dashboard (Home Base Page - Includes Footer)
    'student_dashboard': [
      {
        target: '[data-tour="student-header"], .welcome-card, header',
        title: 'Student Portal Overview',
        description: 'Welcome to your student dashboard! Track your admission status, profile details, active courses, and personalized announcements.',
        position: 'bottom'
      },
      {
        target: '.info-grid, .info-card',
        title: 'Student Profile & Service Details',
        description: 'Inspect your registered contact details, student ID, and enrolled coaching batch or library seat information.',
        position: 'bottom'
      },
      {
        target: '[data-tour="student-quick-actions"], .quick-actions-title, .app-icons-grid',
        title: 'Quick Actions Hub',
        description: 'One-tap access to your Coaching Courses, To-Do Hub, Guidy Chat, Complaint Box, and the Hall of Fame.',
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
        title: 'To-Do Hub & Study Planner',
        description: 'Organize your daily study goals, break down complex topics, track assignments, and view fee reminders.',
        position: 'bottom'
      },
      {
        target: '[data-tour="student-seat-status"], #seatStatusCard, .student-seat-card, .seat-card',
        title: 'Your Seat & Study Status',
        description: 'Check your current reserved library seat, shift timing, and expiry or renewal details.',
        position: 'top'
      },
      {
        target: '[data-tour="student-notif-bell"], #notificationBell, .abcd-notif-btn',
        title: 'Notifications & Alerts Center',
        description: 'Receive real-time notifications for class announcements, seat renewals, test notices, and admin messages.',
        position: 'bottom'
      },
      {
        target: 'footer, .footer, .site-footer',
        title: 'Footer & Quick Links',
        description: 'Access campus contact details, official addresses, help desk, and student services links.',
        position: 'top'
      }
    ],

    // 4. Alumni Dashboard (Home Base Page - Includes Footer)
    'alumni_dashboard': [
      {
        target: '[data-tour="alumni-header"], .welcome-card, header',
        title: 'Alumni Network Hub',
        description: 'Welcome back! Stay connected with current students, showcase your career success, and inspire junior aspirants.',
        position: 'bottom'
      },
      {
        target: '[data-tour="alumni-profile-card"], .alumni-profile-card, .info-grid, .profile-card',
        title: 'Your Career & Profile Details',
        description: 'View and update your current designation, department, selection year, and verified alumni status.',
        position: 'bottom'
      },
      {
        target: '#achievementChart, .chart-container, .achievements-list, .other-ach-list',
        title: 'Milestones & Achievement Graph',
        description: 'Interactive visual chart highlighting your career achievements, competitive selections, and journey progress.',
        position: 'top'
      },
      {
        target: 'a[href*="achievement"], .marquee-footer-buttons, .add-yours-btn',
        title: 'Share New Achievements',
        description: 'Got promoted or cleared a new exam? Submit your latest success story to be featured on the ABCD Hall of Fame wall!',
        position: 'top'
      },
      {
        target: 'a[href*="guidy"], [data-tour="alumni-guidy"]',
        title: 'Guidy Mentorship Chat',
        description: 'Connect directly with aspiring students, answer guidance questions, and mentor the next generation on Guidy.',
        position: 'bottom'
      },
      {
        target: '.app-icons-grid, .quick-actions-title',
        title: 'Quick Actions',
        description: 'Access study courses, your personal study hub, and campus resources anytime.',
        position: 'top'
      },
      {
        target: 'footer, .footer, .site-footer',
        title: 'Footer & Quick Links',
        description: 'Access quick navigation links, platform services directory, contact numbers, address, and official details.',
        position: 'top'
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

    // 8. Courses Catalogue (Content Page - NO Footer)
    'courses': [
      {
        target: '[data-tour="courses-header"], .courses-page-header, header',
        title: 'Coaching Courses & Programs',
        description: 'Browse all available coaching batches, foundation courses, and competitive exam preparation modules.',
        position: 'bottom'
      },
      {
        target: '[data-tour="courses-tabs"], .courses-tabs, .course-tabs',
        title: 'Filter Courses by Tab',
        description: 'Switch between All Courses, your Favorite saved courses, and Archived courses.',
        position: 'bottom'
      },
      {
        target: '[data-tour="courses-grid"], .courses-grid',
        title: 'Course Directory & Modules',
        description: 'Browse all active course cards with full curriculum details, subject previews, and video lecture series.',
        position: 'top'
      },
      {
        target: '.course-info-card:first-child, .course-info-card',
        title: 'Course Card & Progress Tracker',
        description: 'Track your personal completion percentage, check average student ratings, or click anywhere on the card to open the course streaming portal.',
        position: 'top'
      },
      {
        target: '.leave-rating-link, .live-rating-badge',
        title: 'Student Ratings & Feedback',
        description: 'View verified ratings from peers or click "Leave a rating" to submit your review for this course.',
        position: 'top'
      },
      {
        target: '.card-more-btn, .ud-dropdown',
        title: 'Bookmark & Share Menu',
        description: 'Click the three dots to bookmark this course to your favorites, archive it, or copy and share the link with study peers.',
        position: 'left'
      }
    ],

    // 9. Course Detail Page (Content Page - NO Footer)
    'course_detail': [
      {
        target: '[data-tour="course-stream-header"], .course-streaming-header, header',
        title: 'Course Header & Learning Progress',
        description: 'Navigate back to your courses, check your trophy completion percentage, leave a star rating, or share with friends.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-player-screen"], #playerWrapper, .main-player-container',
        title: 'Interactive Video Player & Screen',
        description: 'Watch lecture lessons, control video playback, switch between previous/next materials, or toggle distraction-free zoom fullscreen mode.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-curriculum-sidebar"], aside.sidebar-column, .curriculum-scroll, #curriculumList',
        title: 'Curriculum & Lecture Outline',
        description: 'Browse all video lectures, study PDFs, and notes. Search lessons by title and track completed topics with verified checkmarks.',
        position: 'left'
      },
      {
        target: '[data-target="overview"], #overviewPane, [data-tour="course-info-tabs"], .content-details',
        title: 'Course Overview & Resources',
        description: 'Read detailed course descriptions, instructor notes, and download supplementary lesson worksheets and PDFs.',
        position: 'top'
      },
      {
        target: '[data-target="qa"], #qaPane, .qa-thread',
        title: 'Student Q&A & Doubts Desk',
        description: 'Ask questions regarding specific lessons or the entire course, engage in discussions, and receive verified answers from faculty.',
        position: 'top'
      },
      {
        target: '[data-target="reviews"], #reviewsPane, #starIconInHeader, .rating-badge',
        title: 'Student Reviews & Star Ratings',
        description: 'Read verified student feedback, view rating score distributions, and share your own learning experience.',
        position: 'top'
      },
      {
        target: '[data-target="learning-tools"], #learning-toolsPane, .reminder-item',
        title: 'Study Reminders & Scheduling',
        description: 'Schedule personal push notifications and revision reminders to maintain disciplined study habits.',
        position: 'top'
      }
    ],

    // 10. Teacher Courses Management (Management Page - NO Footer)
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
        description: 'Click here to publish a new course with custom thumbnail, description, and batch accessibility settings.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-sync-yt-btn"]',
        title: 'Sync YouTube & Playlists',
        description: 'Sync YouTube videos or direct playlists to automatically generate and populate complete video courses.',
        position: 'bottom'
      },
      {
        target: '[data-tour="course-list-grid"], .courses-list, .tc-grid',
        title: 'Course Directory & Cards',
        description: 'Browse all active and draft courses with video counts, study material counts, and review statistics.',
        position: 'top'
      },
      {
        target: '.tc-card .tc-card-actions, .tc-card:first-child',
        title: 'Course Content & Edit Actions',
        description: 'Click "Materials" to upload lectures, "Edit" to modify metadata and batch visibility, or "Preview" to see the student view.',
        position: 'top'
      },
      {
        target: '.tc-card .tc-card-admin-actions, .tc-status-badge',
        title: 'Active Status & Course Controls',
        description: 'Toggle student accessibility on or off with one click, or delete outdated course modules.',
        position: 'top'
      }
    ],

    // 11. Teacher Course Materials (Management Page - NO Footer)
    'teacher_course_materials': [
      {
        target: '[data-tour="material-hero"], .tcm-hero, .hero, header',
        title: 'Course Content Manager',
        description: 'Upload and organize lecture videos, PDF worksheets, and study notes for students with live thumbnail preview.',
        position: 'bottom'
      },
      {
        target: '[data-tour="material-add-btn"], .btn-primary[onclick*="MaterialModal"]',
        title: 'Add Lecture / Material',
        description: 'Upload MP4 video lectures, YouTube video links, or downloadable PDF study notes for this course.',
        position: 'bottom'
      },
      {
        target: '[data-tour="material-save-order-btn"], .studio-btn[onclick*="saveNewOrdering"]',
        title: 'Save Reordered Curriculum',
        description: 'After dragging and re-ordering lessons into sequence, click "Save Ordering" to persist the curriculum.',
        position: 'bottom'
      },
      {
        target: '.studio-table, #materialBody, .studio-layout',
        title: 'Interactive Curriculum Table',
        description: 'Use the drag handles on the left to reorder lessons, toggle visibility for students, or edit and delete individual materials.',
        position: 'top'
      }
    ],

    // 12. Teacher Course Preview (Preview Page - NO Footer)
    'teacher_course_preview': [
      {
        target: '.tp-header, .course-streaming-header, header',
        title: 'Teacher Preview Bar',
        description: 'This preview reproduces the exact student learning view. Use the back button to return to Course Management anytime.',
        position: 'bottom'
      },
      {
        target: '#playerWrapper, .main-player-container',
        title: 'Student Video Player Screen',
        description: 'Inspect lecture video streaming quality, player controls, and fullscreen mode as students experience it.',
        position: 'bottom'
      },
      {
        target: '.tp-info-area, .content-details',
        title: 'Course Details & Insights Tab',
        description: 'Review course description, enrolled student questions, feedback reviews, and performance insights.',
        position: 'top'
      },
      {
        target: '.tp-sidebar, aside.sidebar-column',
        title: 'Curriculum & Lecture Outline',
        description: 'Verify your chapter ordering, material titles, and instant search functionality.',
        position: 'left'
      }
    ],

    // 13. Teacher Broadcast Center (Management Page - NO Footer)
    'teacher_broadcast': [
      {
        target: '.broadcast-tabs, #tabBtnBroadcast',
        title: 'Broadcast vs Ads Banner Switcher',
        description: 'Switch between sending instant alert notifications or configuring promotional website popup banners.',
        position: 'bottom'
      },
      {
        target: '#draftSelector, .draft-selector-container',
        title: 'Saved Broadcast Drafts',
        description: 'Quickly load, reuse, or manage previously saved announcement drafts.',
        position: 'bottom'
      },
      {
        target: '#broadcastDetailsGroup, [data-tour="broadcast-compose"], form',
        title: 'Compose Announcement & Attachments',
        description: 'Draft the subject and body text, and attach photos, video clips, or PDF documents (up to 10MB each).',
        position: 'bottom'
      },
      {
        target: '#audienceGroup, .audience-section, [data-tour="broadcast-audience"], #broadcastForm',
        title: 'Target Audience Selection',
        description: 'Direct your announcement to specific coaching batches, library floor students, verified alumni, or all users.',
        position: 'top'
      },
      {
        target: '#sendBroadcastBtn, [data-tour="broadcast-send-btn"], button[type="submit"]',
        title: 'Send or Schedule Notice',
        description: 'Publish your announcement immediately or schedule it for automated delivery.',
        position: 'top'
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

    // 16. Student Complaints (Form & Tracker - NO Footer)
    'student_complaints': [
      {
        target: '.complaints-welcome-card, .welcome-card, header',
        title: 'Student Complaint Box & Help Desk',
        description: 'Lodge issues or request assistance regarding facilities, study environment, coaching doubts, or fees.',
        position: 'bottom'
      },
      {
        target: '.complaint-form-card, form',
        title: 'Lodge a Complaint Ticket',
        description: 'Select the service category (Library / Coaching / General), describe your issue in detail, and attach supporting photos.',
        position: 'top'
      },
      {
        target: 'button[type="submit"], .btn-primary-animated, .submit-btn',
        title: 'Submit Ticket',
        description: 'Submit your ticket for immediate administrative review. You will receive real-time notifications on resolution progress.',
        position: 'top'
      },
      {
        target: '.complaint-history, .complaint-table',
        title: 'Your Complaint Tracker',
        description: 'Track your submitted tickets, official response from administration, and rate the resolution once closed.',
        position: 'top'
      }
    ],

    'student_complaint_rate': [
      {
        target: '.rating-container, form, .card',
        title: 'Rate Complaint Resolution',
        description: 'Give feedback on how quickly and satisfactorily your issue was resolved by the administration.',
        position: 'bottom'
      }
    ],

    'student_complaint_success': [
      {
        target: '.success-card, .card',
        title: 'Complaint Submitted Successfully',
        description: 'Your complaint token has been registered. You will receive notifications on resolution progress.',
        position: 'bottom'
      }
    ],

    'resolved_complaints_public': [
      {
        target: '.hero-card, .page-container header',
        title: 'Public Resolved Complaints & Transparency',
        description: 'Browse campus resolution transparency reports showing resolved student feedback, facilities maintenance, and actions taken.',
        position: 'bottom'
      },
      {
        target: '.complaint-card:first-child, .complaint-card',
        title: 'Complaint Case & Official Resolution',
        description: 'Inspect the reported issue, student feedback rating, and the official administration resolution note.',
        position: 'top'
      }
    ],

    // 17. Fee Calendar & Fee Record (Financial Hub - NO Footer)
    'fee_calendar': [
      {
        target: '.container .header, .header',
        title: 'Student Fee Due Calendar',
        description: 'Visual calendar highlighting payment due dates, upcoming renewals, paid months, and pending dues.',
        position: 'bottom'
      },
      {
        target: '.year-picker-trigger, .year-selector-form',
        title: 'Select Academic Year',
        description: 'Switch between academic years to inspect historical payments or current fee schedules.',
        position: 'bottom'
      },
      {
        target: '.calendar-grid, .month-card',
        title: '12-Month Payment Ledger',
        description: 'Click on any month card to view verified payment dates, recorded receipts, or clear pending monthly dues.',
        position: 'top'
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

    // 18. Hall of Fame & Achievements (NO Footer)
    'hall_of_fame': [
      {
        target: '.hall-header-section, header',
        title: 'ABCD Hall of Fame',
        description: 'Celebrating top rankers, competitive exam toppers, and inspirational student success achievements.',
        position: 'bottom'
      },
      {
        target: '.marquee-section, .marquee-container',
        title: 'Top Rankers Showcase',
        description: 'Continuous spotlight marquee highlighting selected students, job designations, and competitive scores.',
        position: 'bottom'
      },
      {
        target: '.hall-actions-bar, .hall-back-btn, .hall-edit-btn, a[href*="achievement"]',
        title: 'Share Your Success Story',
        description: 'Submit your own exam selection or competitive rank to be featured permanently on the Hall of Fame wall.',
        position: 'bottom'
      },
      {
        target: '.hall-cards-grid, .achievement-card:first-child, .achievement-card',
        title: 'Achiever Profiles & Testimonials',
        description: 'Read the full preparation journey, motivation quotes, and study experience of each featured student.',
        position: 'top'
      }
    ],

    // 18. Achievement Form (Field-by-Field Detailed Walkthrough - NO Footer)
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
        target: '.back-btn-container, .hall-back-btn',
        title: 'Hall of Fame Navigation',
        description: 'Return to the main Hall of Fame wall or view other top rankers.',
        position: 'bottom'
      },
      {
        target: '.cv-header, .cv-name',
        title: 'Officer Name & Selection Post',
        description: 'View the achiever\'s current designation, competitive exam selection, and posting city.',
        position: 'bottom'
      },
      {
        target: '.cv-photo-wrapper, .cv-photo',
        title: 'Verified Student Portrait',
        description: 'Official verified photo of the student from their study tenure at ABCD.',
        position: 'right'
      },
      {
        target: '.experience-box, .cv-content',
        title: 'Success Journey & Study Experience',
        description: 'Read the detailed preparation journey, challenges overcome, and how ABCD faculty guided them to success.',
        position: 'top'
      },
      {
        target: 'button[onclick*="openGuidyModal"], .guidy-btn, .seek-guidance-btn, .hall-back-btn',
        title: 'Seek Guidance via Guidy',
        description: 'Connect directly with this alumni mentor through Guidy 1-to-1 chat for preparation tips and guidance.',
        position: 'top'
      }
    ],

    // 19. Library Availability & Seat Status (NO Footer)
    'library_availability': [
      {
        target: '.hub-navbar, .header, header',
        title: 'Live Library Seat Availability',
        description: 'Check real-time seat availability across Ground Floor and 1st Floor silent study halls.',
        position: 'bottom'
      },
      {
        target: '.floor-selector, .floor-tabs, [data-tour="floor-dropdown"]',
        title: 'Select Floor & Level',
        description: 'Toggle between Ground Floor and 1st Floor study halls to inspect seat layouts.',
        position: 'bottom'
      },
      {
        target: '.shift-selector, .shift-tabs, .shift-filter',
        title: 'Shift Availability Filter',
        description: 'Filter seats by Morning, Afternoon, Evening, or Full-Day shift to find an open desk.',
        position: 'bottom'
      },
      {
        target: '.legend, .legend-item',
        title: 'Seat Status Legend',
        description: 'Color-coded indicators for Available, Occupied, On Hold, or Shift-Occupied desks.',
        position: 'bottom'
      },
      {
        target: '.layout-container, .seat-grid, .seat-layout-wrapper',
        title: 'Interactive 2D Seat Layout Grid',
        description: 'Explore desk locations, charging points, and quiet zones on the real-time library floor map.',
        position: 'top'
      }
    ],

    'your_seat_status': [
      {
        target: '.hub-navbar, .header, header',
        title: 'Your Allocated Seat Status',
        description: 'View real-time information on your reserved study desk, shift timings, and seat holding privileges.',
        position: 'bottom'
      },
      {
        target: '.seat-info-card, .seat-card, .card',
        title: 'Seat Allocation & Desk Number',
        description: 'Check your assigned seat number, floor level, shift hours, and fee renewal deadline.',
        position: 'bottom'
      },
      {
        target: '.seat-actions, .hold-seat-btn, .switch-seat-btn',
        title: 'Seat Hold & Switch Options',
        description: 'Submit a seat hold request if taking leave, or request a seat switch to another desk.',
        position: 'top'
      }
    ],

    // 20. Student Details & Profiles (NO Footer)
    'student_details': [
      {
        target: '.photo-container, #profile-img-main',
        title: 'Student Profile Photo',
        description: 'Click the photo to view it in high resolution, or click the pencil icon to crop and update the student photo.',
        position: 'bottom'
      },
      {
        target: '.student-name',
        title: 'Student Identity & Full Name',
        description: 'Full name and admission identity of the enrolled student.',
        position: 'bottom'
      },
      {
        target: '.details-list',
        title: 'Academic & Seating Records',
        description: 'Check active status, service type, coaching batch, allocated library seat, and verified mobile/WhatsApp numbers.',
        position: 'bottom'
      },
      {
        target: '.footer-actions',
        title: 'Teacher Management Controls',
        description: 'Quickly edit student profile information, reassign batches/desks, or manage administrative records.',
        position: 'top'
      }
    ],

    'student_details_S': [
      {
        target: '.photo-container, #profile-img-main',
        title: 'Your Profile Photo',
        description: 'Click your photo to preview it, or tap the pencil icon to crop and upload a new profile picture.',
        position: 'bottom'
      },
      {
        target: '.student-name',
        title: 'Your Student Profile',
        description: 'Your registered name and verified membership in ABCD Smart Campus.',
        position: 'bottom'
      },
      {
        target: '.details-list',
        title: 'Service & Enrollment Details',
        description: 'View your admission status, coaching batch or library seat allocation, and registered contact information.',
        position: 'bottom'
      },
      {
        target: '.footer-actions, button[onclick*="openChgPwdModal"]',
        title: 'Account Security & Actions',
        description: 'Change your account password securely or manage your personal settings.',
        position: 'top'
      }
    ],

    'edit_student': [
      {
        target: '#photoPreviewContainerCustom, .form-group:first-child',
        title: 'Student Profile Photo',
        description: 'Upload, crop, and adjust the student\'s official profile photo (JPG/PNG up to 2MB).',
        position: 'bottom'
      },
      {
        target: 'input[name="full_name"]',
        title: 'Personal Information',
        description: 'Update the student\'s full name, registered email address, date of birth, and gender.',
        position: 'bottom'
      },
      {
        target: 'select[name="status"], select[name="service_type"]',
        title: 'Enrollment Status & Services',
        description: 'Manage admission status (Active / On Hold / Pending) and assign coaching batches or library services.',
        position: 'bottom'
      },
      {
        target: 'input[name="mobile_number"], input[name="whatsapp_number"]',
        title: 'Contact Information',
        description: 'Update primary mobile number and WhatsApp number for instant campus notices and fee alerts.',
        position: 'bottom'
      },
      {
        target: '.btn-save, button[type="submit"]',
        title: 'Save Student Changes',
        description: 'Save and persist the updated student record to the central database.',
        position: 'top'
      }
    ],

    'edit_alumni': [
      {
        target: '#photoPreviewContainerCustom, .photo-frame, .form-group:first-child',
        title: 'Alumni Portrait',
        description: 'Upload and crop your official portrait photo for the Hall of Fame wall.',
        position: 'bottom'
      },
      {
        target: 'input[name="first_name"], input[name="last_name"]',
        title: 'Personal Information',
        description: 'Update your first name, last name, gender, and inspiring personal bio quote.',
        position: 'bottom'
      },
      {
        target: 'input[name="current_post"], input[name="short_achievement"]',
        title: 'Career & Designation',
        description: 'Update your current post, designation, selection exam, and selection year.',
        position: 'bottom'
      },
      {
        target: 'textarea[name="experience_feedback"], textarea[name="abcd_feedback"]',
        title: 'Experience & Public Review',
        description: 'Share your preparation story at ABCD and advice for junior aspirants.',
        position: 'top'
      },
      {
        target: '.btn-save, button[type="submit"]',
        title: 'Save Alumni Profile',
        description: 'Click to publish your updated career details to the ABCD Hall of Fame.',
        position: 'top'
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
        target: '.profile-pic-container, .profile-title',
        title: 'Guest Account Profile',
        description: 'Your guest learner profile on ABCD Smart Campus.',
        position: 'bottom'
      },
      {
        target: '.detail-grid',
        title: 'Registered Contact Details',
        description: 'View your registered mobile number, email, and guest account status.',
        position: 'bottom'
      },
      {
        target: '.action-btn, a[href*="admission-form"], .profile-details-card',
        title: 'Apply for Admission',
        description: 'Ready to join? Submit your admission form to enroll in coaching batches or reserve a library desk.',
        position: 'top'
      }
    ],

    'register': [
      {
        target: 'form, .register-card, .card',
        title: 'Create an Account',
        description: 'Register for a new student or guest account to access coaching and library booking.',
        position: 'bottom'
      }
    ],

    // 21. About Us (NO Footer)
    'about_us': [
      {
        target: '.hero-card',
        title: 'About ABCD Coaching & Library',
        description: 'Learn about ABCD\'s journey since 2013: focused English coaching, serious exam discipline, and full-day library study halls.',
        position: 'bottom'
      },
      {
        target: '.about-layout > div:first-child .card:first-child, .card',
        title: 'Our Story & Philosophy',
        description: '"Any Body Can Do" — concept-based grammar teaching combined with a quiet, disciplined environment for serious self-study.',
        position: 'bottom'
      },
      {
        target: '.story-list, .split-columns',
        title: 'Coaching & Library Dual Wings',
        description: 'Explore our comprehensive offerings: grammar foundation batches and peaceful 8:00 AM - 8:30 PM library reading halls.',
        position: 'top'
      },
      {
        target: '.founder-photo-wrapper, .about-layout > div:last-child .card:first-child',
        title: 'Meet the Founder: Sandeep Raghuwanshi',
        description: 'Head Faculty with 10+ years of teaching expertise in English grammar, spoken fluency, and competitive guidance.',
        position: 'left'
      },
      {
        target: '.contact-list, .about-layout > div:last-child .card:last-child',
        title: 'Campus Location & Timings',
        description: 'Located in Basoda, Madhya Pradesh. Open daily from 8:00 AM to 8:30 PM for students.',
        position: 'top'
      }
    ],

    // 22. Platform Services (NO Footer)
    'services': [
      {
        target: '.hero-card',
        title: 'Campus Services & Digital Platform',
        description: 'Comprehensive overview of all educational facilities and smart digital tools offered at ABCD Smart Campus.',
        position: 'bottom'
      },
      {
        target: '#coaching',
        title: 'English Coaching Wing',
        description: 'Concept-first teaching covering English grammar, voice, narration, spoken fluency, and competitive exam preparation.',
        position: 'bottom'
      },
      {
        target: '#library',
        title: 'Dedicated Quiet Library',
        description: 'Peaceful air-ventilated study hall with filtered water, high-speed connectivity, and daily 8:00 AM to 8:30 PM study hours.',
        position: 'bottom'
      },
      {
        target: '#seats',
        title: 'Digital Seat Management',
        description: 'Live seat vacancy floor maps, reservation shifts (Morning/Afternoon/Evening/Full Day), and seat hold privileges.',
        position: 'top'
      },
      {
        target: '#helpdesk',
        title: 'Student Helpdesk & Grievances',
        description: 'Instant student ticket submission, transparent resolution tracking, and administrative feedback ratings.',
        position: 'top'
      },
      {
        target: '#todo',
        title: 'Master To-Do & Learning Hub',
        description: 'Smart personal task planner with exam milestones, breakdown checklists, revision reminders, and fee alerts.',
        position: 'top'
      },
      {
        target: '#guidy',
        title: 'Guidy Mentorship Network',
        description: 'Private 1-to-1 encrypted chat connecting students directly with verified alumni officers and faculty mentors.',
        position: 'top'
      },
      {
        target: '#courses',
        title: 'Digital Courses & Video Lectures',
        description: 'Online video lessons, downloadable chapter PDF worksheets, interactive Q&A doubts, and student feedback reviews.',
        position: 'top'
      }
    ],

    // 23. Contact Us (NO Footer)
    'contact': [
      {
        target: '.contact-header',
        title: 'Reach Out to ABCD',
        description: 'We are always here to help you grow. Connect with our admissions and guidance team anytime.',
        position: 'bottom'
      },
      {
        target: '.card-phone',
        title: 'Direct Phone Call',
        description: 'Speak directly with our counseling team for immediate course or library seat assistance (+91 98276 62450).',
        position: 'bottom'
      },
      {
        target: '.card-whatsapp',
        title: 'WhatsApp Help Desk',
        description: 'Instant support, fee inquiries, and live seat reservation updates directly on WhatsApp.',
        position: 'bottom'
      },
      {
        target: '.card-email',
        title: 'Official Email Support',
        description: 'Send formal inquiries or document submissions to abcd2013baq@gmail.com.',
        position: 'top'
      },
      {
        target: '.social-section',
        title: 'Connect on Social Media',
        description: 'Follow our Instagram for daily campus updates, and subscribe to our official YouTube channel for lessons.',
        position: 'top'
      },
      {
        target: '.map-container',
        title: 'Visit Our Campus',
        description: 'Interactive map directions to our campus infront of Block Office, Bareth Road, Ganj Basoda, Madhya Pradesh.',
        position: 'top'
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

      // Listen for seat layout modals to dismiss tour and hide launcher when seat layout opens
      this.setupSeatModalListener();

      // Auto start tour cards after 10 seconds ONLY if user has NEVER completed or dismissed them
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
        if (!this.isSeatModalOpen()) {
          this.start(false);
        }
      }, 10000);
    }

    isSeatModalOpen() {
      const seatModal = document.getElementById('seatModalOverlay');
      if (seatModal) {
        const isVisible = (seatModal.style.display && seatModal.style.display !== 'none') ||
                          seatModal.classList.contains('visible') ||
                          (window.getComputedStyle && window.getComputedStyle(seatModal).display !== 'none');
        if (isVisible) return true;
      }
      const seatContainer = document.getElementById('seatModalContainer');
      if (seatContainer) {
        const isVisible = (seatContainer.style.display && seatContainer.style.display !== 'none') ||
                          seatContainer.classList.contains('visible') ||
                          (window.getComputedStyle && window.getComputedStyle(seatContainer).display !== 'none');
        if (isVisible) return true;
      }
      const seatInterest = document.getElementById('seatInterestOverlay');
      if (seatInterest && !seatInterest.classList.contains('hidden') && (window.getComputedStyle && window.getComputedStyle(seatInterest).display !== 'none')) {
        return true;
      }
      return false;
    }

    setupSeatModalListener() {
      const handleModalChange = () => {
        if (this.isSeatModalOpen()) {
          if (this.isStarted) {
            this.stop(false);
          }
          if (this.launcher) {
            this.launcher.style.display = 'none';
          }
        } else {
          if (this.launcher) {
            this.launcher.style.display = '';
          }
        }
      };

      const seatModal = document.getElementById('seatModalOverlay');
      if (seatModal) {
        const observer = new MutationObserver(handleModalChange);
        observer.observe(seatModal, { attributes: true, attributeFilter: ['style', 'class'] });
      }

      const seatContainer = document.getElementById('seatModalContainer');
      if (seatContainer) {
        const observer = new MutationObserver(handleModalChange);
        observer.observe(seatContainer, { attributes: true, attributeFilter: ['style', 'class'] });
      }

      const seatInterest = document.getElementById('seatInterestOverlay');
      if (seatInterest) {
        const observer = new MutationObserver(handleModalChange);
        observer.observe(seatInterest, { attributes: true, attributeFilter: ['style', 'class'] });
      }

      // Also listen on click triggers that open the seat modal in admission form
      document.addEventListener('click', (e) => {
        const trigger = e.target.closest('#openSeatModalBtn, .select-seat-btn, #selectedSeatPreview, [name="floor_radio"]');
        if (trigger) {
          setTimeout(handleModalChange, 50);
          setTimeout(handleModalChange, 250);
        }
      }, true);
    }

    detectPageKey() {
      const path = window.location.pathname.toLowerCase();

      // Explicitly suppressed pages as requested by user
      if (
        path.includes('/teacher/seat-status') ||
        path.includes('/teacher/seat-manager') ||
        path.includes('/about') ||
        path.includes('/services') ||
        path.includes('/library-availability') ||
        path.includes('/my-seat') ||
        path.includes('/your-seat-status')
      ) {
        return null;
      }

      // Home & Core Hubs
      if (path === '/' || path.endsWith('/home/') || path.includes('home_page')) return 'home_page';
      if (path.includes('/guest-home')) return 'guest_page';
      if (path.includes('/alumni/dashboard')) return 'alumni_dashboard';
      if (path.includes('/alumni/edit')) return 'edit_alumni';
      if (path.includes('/dashboard')) return 'student_dashboard';

      // Teacher Management Pages
      if (path.includes('/teacher/courses/') && path.includes('/materials')) return 'teacher_course_materials';
      if (path.includes('/teacher/courses/') && path.includes('/preview')) return 'teacher_course_preview';
      if (path.includes('/teacher/courses')) return 'teacher_courses';
      if (path.includes('/teacher/broadcast')) return 'teacher_broadcast';
      if (path.includes('/teacher/fees-record')) return 'fees_record';
      if (path.includes('/teacher/progress')) return 'student_progress';
      if (path.includes('/teacher/visitor-insights')) return 'visitor_insights';
      if (path.includes('/teacher/student/') && path.includes('/fees')) return 'fee_calendar';
      if (path.includes('/teacher/student/') && path.includes('/edit')) return 'edit_student';
      if (path.includes('/teacher/student/')) return 'student_details';
      if (path.includes('/teacher')) return 'teacher_dashboard';

      // Academic, Mentorship, and Student Tools
      if (path.includes('/guidy')) return 'guidy';
      if (path.includes('/todo')) return 'todo';
      if (path.includes('/admission-form')) return 'admission_form';
      if (path.includes('/complaints/resolved') || path.includes('/resolved-complaints')) return 'resolved_complaints_public';
      if (path.includes('/complaints/rate')) return 'student_complaint_rate';
      if (path.includes('/complaints/success')) return 'student_complaint_success';
      if (path.includes('/complaints')) return 'student_complaints';
      if (path.includes('/fee/calendar') || path.includes('/fees/')) return 'fee_calendar';
      if (path.includes('/hall-of-fame')) return 'hall_of_fame';
      if (path.includes('/achievement-form') || path.includes('/achievement/add') || path.includes('/achievement/create')) return 'achievement_form';
      if (path.includes('/achievement/')) return 'achievement_detail';
      if (path.includes('/achievement')) return 'achievement_form';
      if (path.includes('/courses/') && !path.endsWith('/courses/')) return 'course_detail';
      if (path.includes('/courses')) return 'courses';

      // Profiles & Informational Pages
      if (path.includes('/profile/guest')) return 'guest_profile_details';
      if (path.includes('/my-details') || path.includes('/student/details-s') || path.includes('/profile')) return 'student_details_S';
      if (path.includes('/contact')) return 'contact';
      if (path.includes('/register')) return 'register';

      if (document.body.dataset.pageKey) {
        const pk = document.body.dataset.pageKey;
        if (
          pk === 'teacher_seat_status' ||
          pk === 'about_us' ||
          pk === 'services' ||
          pk === 'library_availability' ||
          pk === 'your_seat_status'
        ) {
          return null;
        }
        return pk;
      }

      return null;
    }

    getUserStorageKey(pageKey) {
      const userIdent = document.body.dataset.username || 'user';
      return `abcd_tour_card_seen_v20_${pageKey}_${userIdent}`;
    }

    closeAllDrawers() {
      const sidebars = document.querySelectorAll(
        '#sidebar, .nav-sidebar, #sidebarWrapper, .sidebar-wrapper, #hubSidebar, .hub-sidebar, #mobileNav, #guestMobileNav'
      );
      sidebars.forEach(s => s.classList.remove('active', 'open'));

      const overlays = document.querySelectorAll(
        '#sidebarOverlay, .sidebar-overlay, #mobileNavOverlay, .mobile-search-overlay'
      );
      overlays.forEach(o => o.classList.remove('active', 'open'));

      const hamburgerBtns = document.querySelectorAll(
        '#hamburgerBtn, .hamburger-icon, #sidebarToggleBtn, .sidebar-toggle-btn, #mobileNavToggle'
      );
      hamburgerBtns.forEach(h => h.classList.remove('open', 'active'));
    }

    async start(force = false) {
      if (this.isStarted) return;
      if (!this.steps || this.steps.length === 0) return;

      // Never start tour if a seat modal or seat layout is currently open
      if (this.isSeatModalOpen()) return;

      // Autoclose any open navigation sidebars before starting tour
      this.closeAllDrawers();
      await new Promise(resolve => setTimeout(resolve, 200));

      let stepsToUse = [...this.steps];

      // Strict Home Base Footer rule: Only home base pages may EVER introduce the footer!
      if (!HOME_BASE_PAGES.has(this.currentTourKey)) {
        stepsToUse = stepsToUse.filter(s => {
          const t = (s.target || '').toLowerCase().trim();
          return !(
            t === 'footer' ||
            t === '.footer' ||
            t === '.site-footer' ||
            t.includes('footer, .footer') ||
            t.includes('.site-footer')
          );
        });
      }

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
        } else if (this.currentTourKey === 'course_detail') {
          // In course_detail, tab panes are dynamically activated during showStep
          if (s.target.includes('#qaPane') || s.target.includes('#reviewsPane') || s.target.includes('#learning-toolsPane') || s.target.includes('#overviewPane')) {
            const paneId = s.target.includes('#qaPane') ? 'qaPane' : (s.target.includes('#reviewsPane') ? 'reviewsPane' : (s.target.includes('#learning-toolsPane') ? 'learning-toolsPane' : 'overviewPane'));
            const paneEl = document.getElementById(paneId);
            if (paneEl) {
              validSteps.push(s);
              continue;
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
            <button type="button" class="abcd-tour-close-icon" title="Close Tour">&times;</button>
          </div>
          <h4 class="abcd-tour-title"></h4>
          <p class="abcd-tour-description"></p>
          <div class="abcd-tour-footer">
            <span class="abcd-tour-steps-count">Step 1 of 1</span>
            <div class="abcd-tour-controls">
              <button type="button" class="abcd-tour-btn abcd-tour-btn-skip">Skip</button>
              <button type="button" class="abcd-tour-btn abcd-tour-btn-prev"><i class="bx bx-chevron-left"></i> Back</button>
              <button type="button" class="abcd-tour-btn abcd-tour-btn-next">Next <i class="bx bx-chevron-right"></i></button>
            </div>
          </div>
        `;
        document.body.appendChild(this.popover);

        const closeBtn = this.popover.querySelector('.abcd-tour-close-icon, .abcd-tour-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.stop(true));

        const skipBtn = this.popover.querySelector('.abcd-tour-btn-skip, .abcd-tour-skip');
        if (skipBtn) skipBtn.addEventListener('click', () => this.stop(true));

        const prevBtn = this.popover.querySelector('.abcd-tour-btn-prev, .abcd-tour-prev');
        if (prevBtn) prevBtn.addEventListener('click', () => this.prev());

        const nextBtn = this.popover.querySelector('.abcd-tour-btn-next, .abcd-tour-next');
        if (nextBtn) nextBtn.addEventListener('click', () => this.next());
      }
    }

    resolveTarget(step) {
      if (!step || !step.target) return null;

      const isHomeBase = HOME_BASE_PAGES.has(this.currentTourKey);
      const selectors = step.target
        .split(',')
        .map(s => s.trim())
        .filter(s => {
          if (!isHomeBase) {
            const sLower = s.toLowerCase();
            if (sLower === 'footer' || sLower.startsWith('.footer') || sLower.startsWith('.site-footer')) {
              return false;
            }
          }
          return true;
        });

      if (selectors.length === 0) return null;

      for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          const style = window.getComputedStyle(el);
          const isVisible = style.display !== 'none' && style.visibility !== 'hidden';
          const rect = el.getBoundingClientRect();
          const isInsideDrawer = !!el.closest('.hub-sidebar, #hubSidebar, .sidebar-wrapper, #sidebar, #mobileNav, #guestMobileNav');

          // Never target elements inside seat layout modals
          if (el.closest('#seatModalOverlay, #seatModalContainer, #seatModalBody, #seatInterestOverlay')) {
            continue;
          }

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
          if (cand && !cand.closest('#seatModalOverlay, #seatModalContainer, #seatModalBody, #seatInterestOverlay')) {
            return cand;
          }
        }
      }

      const finalCandidate = document.querySelector(step.target);
      if (finalCandidate && !finalCandidate.closest('#seatModalOverlay, #seatModalContainer, #seatModalBody, #seatInterestOverlay')) {
        return finalCandidate;
      }
      return null;
    }

    async handleDrawerState(targetElem) {
      if (!targetElem) return;

      // Check if target element is explicitly inside a navigation drawer container (NOT Guidy chat panels)
      const sidebarContainer = targetElem.closest(
        '.sidebar-wrapper, #sidebarWrapper, #sidebar, .nav-sidebar, #mobileNav, #guestMobileNav, #hubSidebar, .hub-sidebar'
      );
      const isInsideSidebar = !!sidebarContainer && !targetElem.closest('.g-layout, .g-side-body, .g-sidebar, .g-chat-area');

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
        const isAlreadyOpen = (hubSidebar && hubSidebar.classList.contains('active')) ||
                              (sidebarContainer && sidebarContainer.classList.contains('active')) ||
                              (sidebar && sidebar.classList.contains('active'));
        if (!isAlreadyOpen) {
          if (hubSidebar) hubSidebar.classList.add('active');
          if (sidebarContainer) sidebarContainer.classList.add('active', 'open');
          if (sidebar) sidebar.classList.add('active', 'open');
          if (overlay) overlay.classList.add('active', 'open');
          if (hamburgerBtn) hamburgerBtn.classList.add('open', 'active');
          await new Promise(resolve => setTimeout(resolve, 150));
        }
      } else {
        // Target is outside navigation drawers - only close if any drawer is currently open!
        const openDrawer = document.querySelector(
          '#hubSidebar.active, .hub-sidebar.active, #sidebar.active, #sidebar.open, ' +
          '#mobileNav.active, #mobileNav.open, #guestMobileNav.active, #guestMobileNav.open, ' +
          '.sidebar-wrapper.active, #sidebarWrapper.active, .sidebar-overlay.active'
        );
        if (openDrawer) {
          this.closeAllDrawers();
          await new Promise(resolve => setTimeout(resolve, 100));
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

      // 1. Immediate, synchronous UI text & control update (instant user feedback on click)
      const titleEl = this.popover.querySelector('.abcd-tour-title');
      const descEl = this.popover.querySelector('.abcd-tour-description, .abcd-tour-content');
      const stepsCountEl = this.popover.querySelector('.abcd-tour-steps-count, .abcd-tour-steps');

      if (titleEl) titleEl.textContent = step.title;
      if (descEl) descEl.textContent = step.description;
      if (stepsCountEl) stepsCountEl.textContent = `Step ${index + 1} of ${this.validSteps.length}`;

      const prevBtn = this.popover.querySelector('.abcd-tour-btn-prev, .abcd-tour-prev');
      const nextBtn = this.popover.querySelector('.abcd-tour-btn-next, .abcd-tour-next');

      if (prevBtn) prevBtn.disabled = (index === 0);

      if (nextBtn) {
        if (index === this.validSteps.length - 1) {
          nextBtn.textContent = 'Finish ✓';
          nextBtn.className = 'abcd-tour-btn abcd-tour-btn-finish';
        } else {
          nextBtn.innerHTML = 'Next <i class="bx bx-chevron-right"></i>';
          nextBtn.className = 'abcd-tour-btn abcd-tour-btn-next';
        }
      }

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

      // Dynamic tab activation for course_detail
      if (this.currentTourKey === 'course_detail') {
        let tabToClick = null;
        if (step.target.includes('qa')) {
          tabToClick = document.querySelector('.tab-trigger[data-target="qa"]');
        } else if (step.target.includes('reviews')) {
          tabToClick = document.querySelector('.tab-trigger[data-target="reviews"]');
        } else if (step.target.includes('learning-tools')) {
          tabToClick = document.querySelector('.tab-trigger[data-target="learning-tools"]');
        } else if (step.target.includes('overview')) {
          tabToClick = document.querySelector('.tab-trigger[data-target="overview"]');
        }
        if (tabToClick && !tabToClick.classList.contains('active')) {
          tabToClick.click();
          await new Promise(resolve => setTimeout(resolve, 80));
        }
      }

      const targetElem = this.resolveTarget(step);

      if (!targetElem) {
        this.next();
        return;
      }

      await this.handleDrawerState(targetElem);

      const style = window.getComputedStyle(targetElem);
      if (style.display === 'none' || style.visibility === 'hidden') {
        console.warn('[ABCDTour] Skipping unrendered target:', step.target);
        this.next();
        return;
      }

      // Check if target is already comfortably within the screen viewport
      const rectBefore = targetElem.getBoundingClientRect();
      const isComfortablyInView = (
        rectBefore.top >= 60 &&
        rectBefore.bottom <= (window.innerHeight - 60) &&
        rectBefore.left >= 10 &&
        rectBefore.right <= (window.innerWidth - 10) &&
        rectBefore.width > 0 &&
        rectBefore.height > 0
      );

      // Only scroll if the target is off-screen!
      if (!isComfortablyInView) {
        targetElem.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        await new Promise(resolve => setTimeout(resolve, 140));
      }

      if (this.activeTarget) {
        this.activeTarget.classList.remove('abcd-tour-target-active');
      }
      this.activeTarget = targetElem;
      this.activeTarget.classList.add('abcd-tour-target-active');

      // Instant positioning without artificial setTimeout delays
      this.updatePosition();
      this.popover.classList.add('abcd-tour-visible');
      requestAnimationFrame(() => this.updatePosition());
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
              this.closeAllDrawers();
              setTimeout(() => {
                this.start(true);
              }, 150);
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
          this.closeAllDrawers();
          setTimeout(() => {
            this.start(true);
          }, 150);
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
