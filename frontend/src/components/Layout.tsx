import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import CopilotStudioLogo from "./CopilotStudioLogo";

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-brand-600 text-white"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white",
  ].join(" ");
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
      {children}
    </div>
  );
}

/** An organisation link the signed-in person is not allowed to follow. Shown
 *  disabled rather than removed, so the absence is explained rather than
 *  mysterious. */
function LockedNavItem({ label }: { label: string }) {
  return (
    <div
      title="Organisation-wide reporting is limited to an approved group."
      className="flex cursor-not-allowed items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-slate-400 dark:text-slate-500"
    >
      <span>{label}</span>
      <span aria-hidden>🔒</span>
    </div>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const isAdmin = user?.role === "admin";
  const personal = Boolean(user?.has_personal_view);
  const canViewOrg = Boolean(user?.can_view_org);

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-3 px-5 py-5">
          <CopilotStudioLogo size={32} className="shrink-0" />
          <div>
            <div className="text-sm font-semibold text-brand-600 dark:text-brand-500">
              Copilot Studio
            </div>
            <div className="text-lg font-bold leading-tight text-slate-900 dark:text-white">
              Agent Quality
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {/* Two sections: what is yours, and what belongs to the organisation.
              The organisation links stay visible but locked when the person is
              outside the approved group — hiding them looks like a bug, and
              says nothing about who to ask. */}
          {personal && (
            <>
              <SectionLabel>You</SectionLabel>
              <NavLink to="/" className={navClass} end>
                Your agents
              </NavLink>
            </>
          )}

          <SectionLabel>Organisation</SectionLabel>
          {canViewOrg ? (
            <>
              <NavLink to={personal ? "/org" : "/"} className={navClass} end>
                Overview
              </NavLink>
              <NavLink to="/history" className={navClass}>
                History
              </NavLink>
            </>
          ) : (
            <>
              <LockedNavItem label="Overview" />
              <LockedNavItem label="History" />
              <p className="px-3 pb-1 pt-1 text-xs text-slate-400 dark:text-slate-500">
                Limited to an approved group — ask your administrator.
              </p>
            </>
          )}

          {isAdmin && (
            <NavLink to="/rules" className={navClass}>
              Rules
            </NavLink>
          )}
          {isAdmin && (
            <NavLink to="/settings" className={navClass}>
              Settings
            </NavLink>
          )}
          <NavLink to="/help" className={navClass}>
            Setup guide
          </NavLink>
          <NavLink to="/about" className={navClass}>
            About
          </NavLink>
        </nav>
        <div className="space-y-3 border-t border-slate-200 px-4 py-4 text-sm dark:border-slate-700">
          <button
            onClick={toggle}
            className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <span>{theme === "dark" ? "Dark" : "Light"} mode</span>
            <span aria-hidden>{theme === "dark" ? "🌙" : "☀️"}</span>
          </button>
          <div>
            <div className="truncate font-medium text-slate-800 dark:text-slate-100" title={user?.username}>
              {user?.username}
            </div>
            <div className="mb-3 text-xs uppercase tracking-wide text-slate-400">
              {user?.role}
            </div>
            <button
              onClick={logout}
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-[1600px] px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
