/**
 * The Copilot Studio product mark, shipped at `public/app-logo.svg`.
 *
 * This used to probe for the asset with an Image() and fall back to a
 * hand-drawn gradient "ribbon" when the probe failed. That made sense when the
 * file was something an operator might supply; the real mark is now committed,
 * so the probe only bought a second render and a wasted request, and the
 * fallback only bought the risk of shipping the wrong logo without anyone
 * noticing. Sizing comes from the caller's classes, so the suite's two
 * treatments — `h-9 w-9` in the sidebar, `h-14 w-14` on login — are stated at
 * the call site rather than hidden behind a number.
 */
export default function CopilotStudioLogo({
  className = "",
}: {
  className?: string;
}) {
  return (
    <img
      src="/app-logo.svg"
      alt="Copilot Studio"
      className={`rounded-lg object-contain ${className}`}
    />
  );
}
