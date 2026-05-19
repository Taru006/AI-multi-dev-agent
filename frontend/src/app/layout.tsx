import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "react-hot-toast";
import { QueryProvider } from "@/lib/query-provider";

export const metadata: Metadata = {
  title: "AI Dev Agency — Multi-Agent Software Engineering Platform",
  description:
    "Autonomous AI software engineering company: PM, Architect, Developer, QA, Security, DevOps agents collaborating to build your product.",
  keywords: ["AI agents", "software development", "multi-agent", "autonomous coding"],
  openGraph: {
    title: "AI Dev Agency",
    description: "Your autonomous AI software engineering team",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <QueryProvider>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: "#111827",
                color: "#f1f5f9",
                border: "1px solid rgba(99,117,189,0.25)",
                fontFamily: "Inter, sans-serif",
              },
              success: { iconTheme: { primary: "#10b981", secondary: "#fff" } },
              error: { iconTheme: { primary: "#f43f5e", secondary: "#fff" } },
            }}
          />
        </QueryProvider>
      </body>
    </html>
  );
}
