# React Frontend — Development Guide

## Overview

The Mental Health Platform frontend is a React Single Page Application (SPA) built with:

- **React 18** with Hooks and Context API
- **React Router v6** for client-side routing
- **Axios** for HTTP API calls
- **Tailwind CSS** for styling
- **Vite** as the build tool

## Architecture

```
frontend/
├── src/
│   ├── main.jsx                  # Entry point with AuthProvider
│   ├── App.jsx                   # Route configuration
│   ├── index.css                 # Tailwind styles
│   ├── api/
│   │   └── client.js             # Axios instance + interceptors
│   ├── hooks/
│   │   ├── useAuth.js            # Auth context & user state
│   │   └── useWebSocket.js       # WebSocket connection manager
│   ├── components/
│   │   ├── GlobalErrorBoundary.jsx
│   │   ├── NavBar.jsx
│   │   ├── SessionTimeoutWarning.jsx
│   │   ├── LoadingSpinner.jsx
│   │   └── PlaceholderPage.jsx
│   ├── context/
│   │   └── AuthContext.jsx       # Auth state provider
│   └── pages/
│       ├── Landing.jsx           # Public landing page
│       ├── auth/
│       │   ├── SSOCallback.jsx
│       │   └── ConsentModal.jsx
│       ├── student/              # Student portal (7 pages)
│       ├── peer/                 # Peer portal (4 pages)
│       ├── professional/         # Professional portal (4 pages)
│       └── admin/                # Admin portal (1 page)
```

## Key Components

### Authentication Flow

```
Landing Page (SSO Start)
    ↓
University SSO Login
    ↓
/sso/callback (Exchange code for JWT)
    ↓
ConsentModal (Accept terms)
    ↓
Role-Based Dashboard Redirect
    ├─ /student/dashboard
    ├─ /peer/dashboard
    ├─ /professional/schedule
    └─ /admin/dashboard
```

### API Client (`api/client.js`)

**Features**:

- JWT token management (localStorage + HttpOnly cookie)
- Automatic retry on 5xx errors (exponential backoff: 1s, 2s, 4s)
- Request/response interceptors
- 401 → Redirect to login
- 403 → Check for CONSENT_REQUIRED
- Error formatting utility

**Usage**:

```javascript
import { apiClient } from "../api/client";

const response = await apiClient.get("/peer/dashboard");
const error = getErrorMessage(err);
```

### useAuth Hook

**Provides**:

- `user` — Current user object (profile_id, role, account_status)
- `loading` — Initial auth check in progress
- `isAuthenticated` — Boolean auth state
- `logout()` — Clear auth and redirect to login

**Usage**:

```javascript
const { user, isAuthenticated, logout } = useAuth();

if (!user) return <Navigate to="/" />;
if (user.role !== "student") return <Navigate to="/" />;
```

### Protected Route Pattern

```javascript
<Route
  path="/student/dashboard"
  element={
    <ProtectedRoute requiredRole={["student"]}>
      <StudentDashboard />
    </ProtectedRoute>
  }
/>
```

## Portals & Pages

### 1. Student Portal

**Routes**:

- `/student/dashboard` — Main hub (assessment status, appointments, resources)
- `/student/assessment` — Needs questionnaire (stress 1-5, support type, urgency)
- `/student/matching` — Peer counselor matching queue
- `/student/chat/:sessionId` — Real-time chat (WebSocket)
- `/student/appointments` — Professional appointment booking
- `/student/resources` — Mental health resource library
- `/student/feedback/:sessionId` — Post-session feedback

**Key Features**:

- ✅ SSO login with university credentials
- ✅ Consent modal (RULE-11)
- ✅ Assessment questionnaire
- ✅ Matching queue with wait time
- ✅ Real-time chat with encryption
- ✅ Appointment booking UI
- ✅ Resource search and filtering

### 2. Peer Counselor Portal

**Routes**:

- `/peer/dashboard` — **CRITICAL**: Burnout indicator (green/yellow/red)
- `/peer/availability` — Toggle availability and manage schedule
- `/peer/sessions` — View session history with feedback
- `/peer/wellness` — Detailed wellness check with recommendations
- `/peer/badges` — View earned badges (10/25/50/100 sessions)

**Key Features**:

- ✅ Burnout warning system (visual indicator)
- ✅ Session statistics dashboard
- ✅ Availability toggle for matching
- ✅ Badge tracking and gamification
- ✅ Wellness recommendations

**Burnout Indicator Algorithm**:

```
Risk Levels:
  GREEN (< 0.5):   "You're doing great!"
  YELLOW (0.5-0.8): "Consider taking a break"
  RED (≥ 0.8):      "BURNOUT WARNING"

Calculated from:
  - Sessions completed (threshold: 20)
  - Daily sessions (limit: 3)
  - Reports in 7 days (limit: 3)
```

### 3. Professional Counselor Portal

**Routes**:

- `/professional/schedule` — Schedule overview with metrics
- `/professional/availability` — Add/remove availability slots
- `/professional/appointments` — View upcoming appointments
- `/professional/metrics` — Performance stats (ratings, feedback)

**Key Features**:

- ✅ Calendar-based schedule view
- ✅ Slot management with conflict detection
- ✅ Appointment status tracking
- ✅ Performance metrics dashboard

### 4. Admin Portal

**Routes**:

- `/admin/dashboard` — Platform KPIs and management

**Planned Features**:

- Resource management (CRUD)
- Peer counselor management (stats, suspension)
- Professional counselor provisioning
- System metrics and analytics

## Styling

**Tailwind CSS** is the primary styling approach. Key utilities used:

```jsx
// Colors
className = "bg-blue-600 text-white";
className = "bg-gradient-to-br from-blue-600 to-purple-600";

// Layout
className = "grid grid-cols-1 md:grid-cols-3 gap-6";
className = "flex items-center justify-between";

// Responsive
className = "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8";

// States
className = "hover:bg-blue-700 disabled:opacity-50 transition";
```

## Error Handling

**Global Error Boundary** (`GlobalErrorBoundary.jsx`):

- Catches React component errors
- Displays fallback UI
- Logs to console

**API Error Handling**:

```javascript
try {
  const response = await apiClient.get("/endpoint");
} catch (err) {
  const message = getErrorMessage(err);
  setError(message);
  // Handle based on status
  // 401: redirect to login
  // 403: check for CONSENT_REQUIRED
  // 400-499: user error
  // 500+: server error (will retry)
}
```

## Session Management

**Session Timeout Warning**:

- Displays warning modal at 25min (before 30min server timeout)
- Auto-logout after 30min inactivity
- User can click "Stay Logged In" to refresh

## Development Workflow

### Setup

```bash
cd frontend
npm install
npm run dev
```

### Environment Variables (`.env`)

```
VITE_API_URL=http://localhost:8000/api/v1
VITE_APP_NAME=MindBridge
```

### Build

```bash
npm run build      # Production build
npm run preview    # Preview production build locally
```

### Development Server

```bash
npm run dev        # Hot reload on http://localhost:5173
```

## Testing Recommendations

### Unit Tests (Jest + React Testing Library)

```javascript
test("StudentDashboard loads user data", async () => {
  render(<StudentDashboard />);
  await waitFor(() => {
    expect(screen.getByText(/Assessment/)).toBeInTheDocument();
  });
});
```

### E2E Tests (Playwright/Cypress)

```javascript
test("Complete student login flow", async ({ page }) => {
  await page.goto("/");
  await page.click('button:has-text("Login with University SSO")');
  // Complete SSO, consent
  await expect(page).toHaveURL("/student/dashboard");
});
```

## Performance Optimization

1. **Code Splitting**: Route-based chunks via React.lazy()
2. **Image Optimization**: Lazy loading for resources
3. **Caching**: Service workers for offline support
4. **API Caching**: Axios retry + local state
5. **Bundle Analysis**: `npm run build -- --visualize`

## Accessibility

- Semantic HTML elements
- ARIA labels for interactive components
- Keyboard navigation support
- Color contrast compliance (WCAG AA)
- Screen reader friendly error messages

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile: iOS 12+, Android 9+

## Future Enhancements

- [ ] Offline mode with Service Workers
- [ ] Dark mode toggle
- [ ] PWA app manifest
- [ ] Real-time notifications (Web Push)
- [ ] Video call integration
- [ ] Appointment calendar sync (Google/Outlook)
- [ ] Accessibility audit and improvements
- [ ] i18n (Spanish, French, etc.)

## Troubleshooting

**Issue: "Failed to load dashboard"**

- Check network tab in DevTools
- Verify backend is running on 8000
- Check CORS headers in response

**Issue: "Redirected to login after SSO callback"**

- Check that JWT token is being stored
- Verify cookie settings (HttpOnly, SameSite)
- Check browser Storage/Cookies in DevTools

**Issue: WebSocket connection fails**

- Ensure backend WebSocket service running
- Check browser WebSocket support
- Verify ws:// or wss:// protocol

---

**Status**: Frontend structure complete with placeholder pages | Ready for incremental feature implementation
