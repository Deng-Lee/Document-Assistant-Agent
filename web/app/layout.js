import "./globals.css";
import Link from "next/link";

export const metadata = {
  title: "Personal Document Assistant",
  description: "Next.js frontend for the Personal Document Assistant V1 runtime.",
};

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/chat", label: "Chat" },
  { href: "/traces", label: "Traces" },
  { href: "/evaluation", label: "Evaluation" },
];

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-chrome">
          <aside className="rail">
            <div>
              <p className="rail-kicker">Personal Document Assistant</p>
              <h1>Field Console</h1>
              <p className="rail-copy">
                Next.js operator frontend for ingest, chat orchestration, trace drill-down, and frozen evaluation.
              </p>
            </div>
            <nav className="rail-nav">
              {NAV_ITEMS.map((item) => (
                <Link key={item.href} href={item.href} className="rail-link">
                  {item.label}
                </Link>
              ))}
            </nav>
            <div className="rail-footnote">
              <span>Backend API</span>
              <strong>/api/* via Next rewrite</strong>
            </div>
          </aside>
          <main className="view-shell">{children}</main>
        </div>
      </body>
    </html>
  );
}
