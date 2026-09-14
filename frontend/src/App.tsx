import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { useSetupStatus } from "./hooks/useSetupStatus";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import PersonalPage from "./pages/PersonalPage";
import AgentDetailPage from "./pages/AgentDetailPage";
import HistoryPage from "./pages/HistoryPage";
import AdminPage from "./pages/AdminPage";
import RulesPage from "./pages/RulesPage";
import SetupGuidePage from "./pages/SetupGuidePage";
import AboutPage from "./pages/AboutPage";

export default function App() {
  const { user, loading } = useAuth();
  const { configured, checked } = useSetupStatus(Boolean(user));

  if (loading) {
    return (
      <div className="grid h-full place-items-center text-slate-500 dark:text-slate-400">
        Loading…
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  // First run: send admins straight to Settings (where the wizard opens itself)
  // until a service principal is configured. Non-admins carry on to the
  // dashboards and see the usual empty states.
  const needsSetup = checked && !configured && user.role === "admin";

  // Organisation-wide pages are a server-side decision; this only stops the UI
  // from parking someone on a page that will answer 403.
  const org = (el: JSX.Element) =>
    user.can_view_org ? el : <Navigate to="/" replace />;

  // People signing in with a work account land on their own agents. Everyone
  // else (the password admin, and anyone without a directory identity) lands on
  // the organisation overview as before. A local account with neither is rare
  // but must not bounce between redirects, so it gets a plain explanation.
  const landing = user.has_personal_view ? (
    <PersonalPage />
  ) : user.can_view_org ? (
    <OverviewPage />
  ) : (
    <div className="card p-6 text-sm text-slate-500 dark:text-slate-400">
      Organisation-wide reporting is limited to an approved group, and this account has no
      personal view. Ask your administrator if you need access.
    </div>
  );

  return (
    <Layout>
      <Routes>
        <Route
          path="/"
          element={needsSetup ? <Navigate to="/settings" replace /> : landing}
        />
        <Route path="/me" element={<PersonalPage />} />
        <Route path="/org" element={org(<OverviewPage />)} />
        <Route path="/agents/:botId" element={<AgentDetailPage />} />
        <Route path="/history" element={org(<HistoryPage />)} />
        <Route path="/help" element={<SetupGuidePage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route
          path="/settings"
          element={user.role === "admin" ? <AdminPage /> : <Navigate to="/" replace />}
        />
        <Route
          path="/rules"
          element={user.role === "admin" ? <RulesPage /> : <Navigate to="/" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
