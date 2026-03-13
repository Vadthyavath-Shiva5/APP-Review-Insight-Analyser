import "./globals.css";

export const metadata = {
  title: "GROWW Reviews - Analyser",
  description: "Weekly pulse dashboard for GROWW Play Store reviews",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
